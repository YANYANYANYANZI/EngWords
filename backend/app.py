import json
import os
import re
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import difflib
from dotenv import load_dotenv

# 加载项目根目录 .env 文件
dotenv_path = Path(__file__).resolve().parent.parent / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)
    print(f"[TTS] Loaded .env: {dotenv_path}")
else:
    print(f"[TTS] .env not found at {dotenv_path}, TTS will use defaults")

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import and_, delete, func, select
from sqlalchemy.orm import selectinload

from .core.config import BASE_DIR
from .core.database import AsyncSessionLocal
from .models import (
    EnrichWordRequest,
    SwapExampleRequest,
    UnitInfo,
    UnitSummaryRequest,
    UpdateNoteRequest,
    UpdateWordRequest,
    WordEntry,
)
from .orm import Cluster, Example, Note, User, UserWordProgress, Word, WordCluster

app = FastAPI(title="VocabOS API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


DEFAULT_USER_NAME = "local"
UNIT_SUMMARY_DIR = BASE_DIR / "data" / "unit_summaries"
RELATIONS_FILE = BASE_DIR / "data" / "relations.json"
NAHIDA_CACHE_DIR = BASE_DIR / "media" / "audio" / "nahida"

UNIT_SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
NAHIDA_CACHE_DIR.mkdir(parents=True, exist_ok=True)



TTS_API_URL = os.getenv("VOCABOS_TTS_API_URL", "http://127.0.0.1:9880/tts")
TTS_REF_AUDIO_PATH = os.getenv(
    "VOCABOS_TTS_REF_AUDIO_PATH",
    str(BASE_DIR / "media" / "audio" / "nahida" / "nahida_ref.wav"),
)
TTS_PROMPT_TEXT = "快去避雨吧，小心头顶上长出蘑菇哦。"
TTS_PROMPT_LANG = "zh"
TTS_TEXT_LANG = "en"

TTS_SPLIT_METHOD = os.getenv("VOCABOS_TTS_SPLIT_METHOD", "cut0")
TTS_BATCH_SIZE = int(os.getenv("VOCABOS_TTS_BATCH_SIZE", "1"))
TTS_SPEED_FACTOR = float(os.getenv("VOCABOS_TTS_SPEED_FACTOR", "1.0"))
TTS_CACHE_NAMESPACE = os.getenv("VOCABOS_TTS_CACHE_NAMESPACE", "nahida")
TTS_TIMEOUT = httpx.Timeout(180.0, connect=10.0)




@app.get("/api/db_health")
async def get_db_health():
    try:
        async with AsyncSessionLocal() as session:
            return {
                "ok": True,
                "driver": "async_sqlalchemy",
                "fsrs_fields": ["state", "lapses", "stability", "difficulty", "retrievability"],
                "words": await session.scalar(select(func.count()).select_from(Word)) or 0,
                "clusters": await session.scalar(select(func.count()).select_from(Cluster)) or 0,
                "word_cluster_links": await session.scalar(select(func.count()).select_from(WordCluster)) or 0,
                "progress_rows": await session.scalar(select(func.count()).select_from(UserWordProgress)) or 0,
            }
    except Exception as ex:
        return {"ok": False, "error": str(ex)}


def _norm(text: str) -> str:
    return (text or "").strip().lower()


def _tokens(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z]+|[\u4e00-\u9fff]+", _norm(text))


def _search_score(query: str, item: Dict[str, Any]) -> float:
    q = _norm(query)
    word = _norm(item.get("word", ""))
    haystack = _entry_haystack(item)
    translation = _norm(item.get("translation", ""))
    if not q:
        return 0

    score = 0.0
    if q == word:
        score += 120
    if word.startswith(q):
        score += 80
    if q in word:
        score += 55
    if q in translation:
        score += 50
    if q in haystack:
        score += 35

    score += difflib.SequenceMatcher(None, q, word).ratio() * 45
    q_tokens = set(_tokens(q))
    h_tokens = set(_tokens(haystack))
    if q_tokens and h_tokens:
        score += len(q_tokens & h_tokens) / len(q_tokens) * 35
    return score


def _wordnet_lookup(word: str) -> List[Dict[str, Any]]:
    try:
        from nltk.corpus import wordnet as wn

        synsets = wn.synsets(word)
    except Exception:
        return []

    senses = []
    for synset in synsets[:4]:
        lemmas = synset.lemmas()
        synonyms = sorted({lemma.name().replace("_", " ") for lemma in lemmas if lemma.name().lower() != word.lower()})[:6]
        antonyms = sorted({ant.name().replace("_", " ") for lemma in lemmas for ant in lemma.antonyms()})[:6]
        senses.append({
            "pos": synset.pos(),
            "definition": synset.definition(),
            "examples": synset.examples(),
            "synonyms": synonyms,
            "antonyms": antonyms,
        })
    return senses


def _template_examples(word: str, translation: str) -> List[str]:
    clean_translation = re.sub(r"^[a-z]+\.", "", translation or "").strip(" ;，。") or "the concept"
    return [
        f"A measurable {word} often requires consistent effort, clear feedback, and the ability to revise one's strategy after failure.",
        f"In academic and professional settings, {word} is usually evaluated not only by the final result but also by the discipline and judgment behind it.",
        f"The discussion of {word} is closely connected with {clean_translation}, especially when people compare short-term gains with long-term development.",
    ]


def _is_low_quality_example(example: str, word: str) -> bool:
    text = _norm(example)
    return (
        "i want to understand the word" in text
        or "the meaning of" in text and "is related to" in text
        or len(text) < max(32, len(word) + 20)
    )


def _usable_examples(examples: List[str], word: str, translation: str) -> List[str]:
    cleaned = [example for example in (examples or []) if example and not _is_low_quality_example(example, word)]
    return cleaned[:3] if cleaned else _template_examples(word, translation)


def _default_example(word: str, translation: str) -> str:
    return _template_examples(word, translation)[0]


def _example_source_priority(source_type: str) -> int:
    priorities = {
        "pinned": -1,
        "tatoeba": 0,
        "ai": 1,
        "movie": 2,
        "subtitle": 3,
        "default": 4,
        "user": 9,
    }
    return priorities.get((source_type or "").strip().lower(), 5)


def _select_user_examples(examples: List[Example], word: str) -> List[str]:
    visible_examples: List[str] = []
    for example in examples or []:
        if not example.text or (example.source_type or "").lower() != "user":
            continue
        # Legacy JSON imported old generated examples as "user", but they were never
        # actual user-authored content and should not appear in the custom example UI.
        if (example.source_name or "").lower() == "legacy_json":
            continue
        visible_examples.append(example.text)
    return visible_examples


def _select_default_example_text(examples: List[Example], word: str, translation: str) -> str:
    system_examples = [
        example for example in (examples or [])
        if example.text and (example.source_type or "").lower() != "user"
    ]
    if system_examples:
        system_examples.sort(
            key=lambda example: (
                _example_source_priority(example.source_type),
                -(example.quality_score or 0),
                len(example.text or ""),
                example.id or 0,
            )
        )
        return system_examples[0].text
    return _default_example(word, translation)


def _with_default_example(entry: Dict[str, Any], default_example: str | None = None) -> Dict[str, Any]:
    item = entry.copy()
    item["default_example"] = default_example or _default_example(item.get("word", ""), item.get("translation", ""))
    return item


def _entry_haystack(item: Dict[str, Any]) -> str:
    return " ".join(filter(None, [
        _norm(item.get("word", "")),
        _norm(item.get("translation", "")),
        _norm(item.get("notes", "")),
        " ".join(_norm(example) for example in item.get("example_sentences") or []),
    ]))


def _dt_to_iso(value):
    return value.isoformat() + "Z" if value else None


def _summary_file(unit_id: str) -> Path:
    return UNIT_SUMMARY_DIR / f"{unit_id}.md"


def _safe_audio_stem(word: str) -> str:
    stem = re.sub(r"[^a-zA-Z0-9._-]+", "_", _norm(word))
    return stem or "word"


def _safe_cache_namespace(value: str) -> str:
    namespace = re.sub(r"[^a-zA-Z0-9._-]+", "_", (value or "").strip())
    return namespace or "default"


def _audio_cache_path(text: str, voice: str | None = None) -> Path:
    # GPT-SoVITS 输出强依赖模型/参考音频。把 voice/namespace 写进缓存路径，
    # 避免切换到纳西妲后仍命中之前默认模型生成的同名单词 wav。
    namespace = _safe_cache_namespace(voice or TTS_CACHE_NAMESPACE)
    digest = hashlib.sha1((text or "").strip().encode("utf-8")).hexdigest()[:12]
    stem = _safe_audio_stem(text)[:48]
    return NAHIDA_CACHE_DIR / namespace / f"{stem}_{digest}.wav"


def _tts_request_payload(word: str) -> Dict[str, Any]:
    if not TTS_REF_AUDIO_PATH:
        raise HTTPException(
            status_code=503,
            detail="VOCABOS_TTS_REF_AUDIO is not configured",
        )
    ref_audio_path = Path(TTS_REF_AUDIO_PATH).expanduser()
    if not ref_audio_path.exists():
        raise HTTPException(
            status_code=503,
            detail=f"TTS reference audio not found: {ref_audio_path}",
        )
    return {
        "text": word.strip(),
        "text_lang": TTS_TEXT_LANG,
        "ref_audio_path": str(ref_audio_path),
        "prompt_text": TTS_PROMPT_TEXT,
        "prompt_lang": TTS_PROMPT_LANG,
        "text_split_method": TTS_SPLIT_METHOD,
        "batch_size": TTS_BATCH_SIZE,
        "speed_factor": TTS_SPEED_FACTOR,
        "media_type": "wav",
        "streaming_mode": False,
    }


async def _get_default_user_id(session) -> int:
    user = await session.scalar(
        select(User).where((User.is_default.is_(True)) | (User.name == DEFAULT_USER_NAME)).limit(1)
    )
    if user:
        return user.id
    user = User(name=DEFAULT_USER_NAME, is_default=True)
    session.add(user)
    await session.flush()
    return user.id


def _word_to_frontend_entry(word: Word, unit_id: str, progress: UserWordProgress | None = None) -> Dict[str, Any]:
    user_examples = _select_user_examples(word.examples, word.word)
    default_example = _select_default_example_text(word.examples, word.word, word.translation or "")
    notes = [{
        "id": f"db_note_{note.id}",
        "text": note.text,
        "links": note.extra.get("links", []) if isinstance(note.extra, dict) else [],
        "created_at": _dt_to_iso(note.created_at),
        "updated_at": _dt_to_iso(note.updated_at),
    } for note in word.notes]
    status = {
        "memorized_past": bool(progress.memorized_past) if progress else False,
        "memorized_today": bool(progress.memorized_today) if progress else False,
        "last_reviewed": _dt_to_iso(progress.last_reviewed_at) if progress else None,
        "review_count": progress.review_count if progress else 0,
    }
    definitions = [line.strip() for line in (word.definition or "").splitlines() if line.strip()]
    return _with_default_example(
        {
            "word": word.word,
            "translation": word.translation or "",
            "unit": unit_id,
            "status": status,
            "notes": "\n".join(note["text"] for note in notes if note.get("text")),
            "notes_v2": notes,
            "phonetic": word.phonetic or "",
            "tags": word.tags or "",
            "pos": word.pos or "",
            "definitions": definitions,
            "example_sentences": user_examples,
            "chinese": word.translation or "",
        },
        default_example=default_example,
    )


async def _get_db_word_entry(session, unit_id: str, word_text: str) -> Dict[str, Any]:
    user_id = await _get_default_user_id(session)
    stmt = (
        select(Word, UserWordProgress)
        .join(WordCluster, WordCluster.word_id == Word.id)
        .join(Cluster, Cluster.id == WordCluster.cluster_id)
        .outerjoin(
            UserWordProgress,
            and_(UserWordProgress.word_id == Word.id, UserWordProgress.user_id == user_id),
        )
        .options(selectinload(Word.examples), selectinload(Word.notes))
        .where(Cluster.code == unit_id, Word.normalized == _norm(word_text))
        .limit(1)
    )
    row = (await session.execute(stmt)).first()
    if not row:
        raise HTTPException(status_code=404, detail="word not found")
    word, progress = row
    return _word_to_frontend_entry(word, unit_id, progress)


async def _list_all_word_entries(session) -> List[Dict[str, Any]]:
    user_id = await _get_default_user_id(session)
    stmt = (
        select(Word, Cluster.code, UserWordProgress)
        .join(WordCluster, WordCluster.word_id == Word.id)
        .join(Cluster, Cluster.id == WordCluster.cluster_id)
        .outerjoin(
            UserWordProgress,
            and_(UserWordProgress.word_id == Word.id, UserWordProgress.user_id == user_id),
        )
        .options(selectinload(Word.examples), selectinload(Word.notes))
        .order_by(Cluster.code, WordCluster.position, Word.word)
    )
    rows = (await session.execute(stmt)).all()
    return [_word_to_frontend_entry(word, unit_id, progress) for word, unit_id, progress in rows]


async def _update_word_audio_path(word_text: str, cache_path: Path) -> None:
    async with AsyncSessionLocal() as session:
        db_word = await session.scalar(select(Word).where(Word.normalized == _norm(word_text)).limit(1))
        if not db_word:
            return
        try:
            db_word.word_audio_path = str(cache_path.relative_to(BASE_DIR))
        except ValueError:
            db_word.word_audio_path = str(cache_path)
        await session.commit()


@app.get("/api/db/units", response_model=List[UnitInfo])
async def get_db_units():
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(Cluster, func.count(WordCluster.id).label("word_count"))
            .outerjoin(WordCluster, WordCluster.cluster_id == Cluster.id)
            .group_by(Cluster.id)
            .order_by(Cluster.code)
        )
        return [{
            "unit": cluster.code,
            "count": count,
            "updated_at": _dt_to_iso(cluster.updated_at),
            "title": cluster.name,
        } for cluster, count in rows]


@app.get("/api/db/words/{unit_id}", response_model=List[WordEntry])
async def get_db_unit_words(unit_id: str):
    async with AsyncSessionLocal() as session:
        user_id = await _get_default_user_id(session)
        stmt = (
            select(Word, UserWordProgress)
            .join(WordCluster, WordCluster.word_id == Word.id)
            .join(Cluster, Cluster.id == WordCluster.cluster_id)
            .outerjoin(
                UserWordProgress,
                and_(UserWordProgress.word_id == Word.id, UserWordProgress.user_id == user_id),
            )
            .options(selectinload(Word.examples), selectinload(Word.notes))
            .where(Cluster.code == unit_id)
            .order_by(WordCluster.position, Word.word)
        )
        rows = (await session.execute(stmt)).all()
        if not rows:
            raise HTTPException(status_code=404, detail="unit not found")
        return [_word_to_frontend_entry(word, unit_id, progress) for word, progress in rows]


@app.get("/api/db/all_words")
async def get_db_all_words():
    async with AsyncSessionLocal() as session:
        return await _list_all_word_entries(session)


@app.get("/api/db/dashboard")
async def get_db_dashboard():
    async with AsyncSessionLocal() as session:
        user_id = await _get_default_user_id(session)
        total_words = await session.scalar(select(func.count()).select_from(Word)) or 0
        progress_rows = (
            await session.execute(select(UserWordProgress).where(UserWordProgress.user_id == user_id))
        ).scalars().all()
        reviewed_today = sum(1 for row in progress_rows if row.memorized_today)
        total_reviews = sum(row.review_count for row in progress_rows)
        past_memorized = sum(1 for row in progress_rows if row.memorized_past)
        review_rate = (reviewed_today / total_words * 100) if total_words else 0
        today_goal = 50
        return {
            "total_words": total_words,
            "reviewed_today": reviewed_today,
            "total_reviews": total_reviews,
            "past_memorized": past_memorized,
            "review_rate": review_rate,
            "today_goal": today_goal,
            "progress": min(100, reviewed_today / today_goal * 100),
            "forget_curve": [1, 0.8, 0.6, 0.4, 0.2],
            "source": "async_sqlalchemy",
        }


@app.post("/api/db/update_word", response_model=WordEntry)
async def update_db_word(req: UpdateWordRequest):
    async with AsyncSessionLocal() as session:
        user_id = await _get_default_user_id(session)
        word = await session.scalar(select(Word).where(Word.normalized == _norm(req.word)).limit(1))
        if not word:
            raise HTTPException(status_code=404, detail="word not found")
        progress = await session.scalar(
            select(UserWordProgress).where(
                UserWordProgress.user_id == user_id,
                UserWordProgress.word_id == word.id,
            )
        )
        if not progress:
            progress = UserWordProgress(user_id=user_id, word_id=word.id)
            session.add(progress)
        if req.memorized_past is not None:
            progress.memorized_past = bool(req.memorized_past)
        if req.memorized_today is not None:
            was_reviewed_today = progress.memorized_today
            progress.memorized_today = bool(req.memorized_today)
            if req.memorized_today:
                progress.memorized_past = True
                if not was_reviewed_today:
                    progress.review_count += 1
                progress.state = 2
                progress.status = "review"
                progress.last_reviewed_at = datetime.utcnow()
        await session.commit()
        return await _get_db_word_entry(session, req.unit, req.word)


@app.post("/api/db/swap_example")
async def swap_db_example(req: SwapExampleRequest):
    async with AsyncSessionLocal() as session:
        word = await session.scalar(
            select(Word)
            .options(selectinload(Word.examples))
            .where(Word.normalized == _norm(req.word))
            .limit(1)
        )
        if not word:
            raise HTTPException(status_code=404, detail="word not found")

        target_text = (req.target_example or "").strip()
        if not target_text:
            raise HTTPException(status_code=400, detail="target_example is required")

        examples = list(word.examples or [])
        if not examples:
            raise HTTPException(status_code=404, detail="examples not found")

        current_default_text = _select_default_example_text(examples, word.word, word.translation or "")
        target_example = next((example for example in examples if (example.text or "").strip() == target_text), None)
        current_default = next((example for example in examples if example.text == current_default_text), None)

        if not target_example:
            raise HTTPException(status_code=404, detail="target example not found")

        target_example.source_type = "pinned"
        target_example.source_name = target_example.source_name or "frontend"

        if current_default and current_default.id != target_example.id:
            current_default.source_type = "user"
            current_default.source_name = current_default.source_name or "frontend"

        await session.commit()
        return {
            "success": True,
            "msg": "Example swapped successfully",
            "word": word.word,
            "default_example": target_example.text,
            "downgraded_example": current_default.text if current_default and current_default.id != target_example.id else None,
        }


@app.post("/api/db/update_note", response_model=WordEntry)
async def update_db_note(req: UpdateNoteRequest):
    async with AsyncSessionLocal() as session:
        word = await session.scalar(select(Word).where(Word.normalized == _norm(req.word)).limit(1))
        if not word:
            raise HTTPException(status_code=404, detail="word not found")
        await session.execute(delete(Note).where(Note.word_id == word.id))
        for note in req.notes_v2 or []:
            text = str(note.get("text", "")).strip()
            if text:
                session.add(Note(word_id=word.id, text=text, extra={"links": note.get("links", [])}))
        await session.commit()
        return await _get_db_word_entry(session, req.unit, req.word)


@app.post("/api/db/enrich_word", response_model=WordEntry)
async def enrich_db_word(req: EnrichWordRequest):
    async with AsyncSessionLocal() as session:
        word = await session.scalar(select(Word).where(Word.normalized == _norm(req.word)).limit(1))
        if not word:
            raise HTTPException(status_code=404, detail="word not found")
        word.pos = req.pos or word.pos
        if req.definitions is not None:
            word.definition = "\n".join(req.definitions)
        if req.chinese is not None:
            word.translation = req.chinese or word.translation
        await session.execute(delete(Example).where(Example.word_id == word.id, Example.source_type == "user"))
        for sentence in req.example_sentences or []:
            text = sentence.strip()
            if text:
                session.add(Example(word_id=word.id, text=text, source_type="user", source_name="frontend"))
        await session.commit()
        return await _get_db_word_entry(session, req.unit, req.word)


@app.get("/api/db/tts")
async def get_db_tts(
    word: str = Query(..., min_length=1),
    voice: str = Query(TTS_CACHE_NAMESPACE, min_length=1),
    force: bool = Query(False),
):
    cache_path = _audio_cache_path(word, voice)
    if cache_path.exists() and not force:
        return FileResponse(cache_path, media_type="audio/wav", filename=cache_path.name)

    payload = _tts_request_payload(word)
    try:
        async with httpx.AsyncClient(timeout=TTS_TIMEOUT) as client:
            response = await client.get(TTS_API_URL, params=payload)
    except httpx.HTTPError as ex:
        raise HTTPException(status_code=502, detail=f"TTS service request failed: {ex}") from ex

    if response.status_code != 200:
        detail = response.text.strip() or f"TTS service returned {response.status_code}"
        raise HTTPException(status_code=502, detail=detail)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = cache_path.with_suffix(".tmp")
    temp_path.write_bytes(response.content)
    temp_path.replace(cache_path)
    await _update_word_audio_path(word, cache_path)
    return FileResponse(cache_path, media_type="audio/wav", filename=cache_path.name)


# Backward-compatible routes now delegate to the database-backed handlers.
@app.get("/api/units", response_model=List[UnitInfo])
async def get_units():
    return await get_db_units()


@app.get("/api/words/{unit_id}", response_model=List[WordEntry])
async def get_unit_words(unit_id: str):
    return await get_db_unit_words(unit_id)


@app.post("/api/update_word", response_model=WordEntry)
async def update_word(req: UpdateWordRequest):
    return await update_db_word(req)


@app.post("/api/update_note", response_model=WordEntry)
async def update_note(req: UpdateNoteRequest):
    return await update_db_note(req)


@app.post("/api/enrich_word", response_model=WordEntry)
async def enrich_word(req: EnrichWordRequest):
    return await enrich_db_word(req)


@app.get("/api/dashboard")
async def get_dashboard():
    return await get_db_dashboard()


@app.get("/api/all_words")
async def get_all_words():
    return await get_db_all_words()


@app.get("/api/unit_summary/{unit_id}")
def get_unit_summary(unit_id: str):
    path = _summary_file(unit_id)
    return {"unit": unit_id, "summary": path.read_text(encoding="utf-8") if path.exists() else ""}


@app.post("/api/unit_summary", response_model=Dict[str, str])
def post_unit_summary(req: UnitSummaryRequest):
    path = _summary_file(req.unit)
    path.write_text(req.summary, encoding="utf-8")
    return {"unit": req.unit, "summary": req.summary}


@app.get("/api/dict/{word}")
async def query_dict(word: str):
    async with AsyncSessionLocal() as session:
        corpus = await _list_all_word_entries(session)

    local = next((item for item in corpus if _norm(item.get("word")) == _norm(word)), None)
    senses = _wordnet_lookup(word)

    if not senses and local:
        translation = local.get("translation", "")
        senses = [{
            "pos": local.get("pos") or "",
            "definition": translation or f"Meaning of {word}",
            "examples": _usable_examples(local.get("example_sentences") or [], word, translation),
            "synonyms": [],
            "antonyms": [],
            "chinese": translation,
        }]
    elif senses and local:
        senses[0]["chinese"] = local.get("translation", "")
        senses[0]["examples"] = _usable_examples(
            senses[0].get("examples") or local.get("example_sentences") or [],
            word,
            local.get("translation", ""),
        )

    return {"word": word, "senses": senses, "source": "wordnet+db" if senses else "empty"}


@app.get("/api/search/{query}")
async def semantic_search(query: str, limit: int = Query(12, ge=1, le=50)):
    async with AsyncSessionLocal() as session:
        corpus = await _list_all_word_entries(session)

    scored = []
    for item in corpus:
        score = _search_score(query, item)
        if score > 12:
            scored.append((score, item))
    scored.sort(key=lambda item: item[0], reverse=True)

    related = [{
        "word": item.get("word"),
        "unit": item.get("unit"),
        "translation": item.get("translation", ""),
        "similarity": round(min(score / 120, 1), 3),
    } for score, item in scored[:limit]]

    opposite = []
    senses = _wordnet_lookup(query)
    antonyms = [antonym for sense in senses for antonym in sense.get("antonyms", [])]
    for antonym in antonyms[:6]:
        match = max(corpus, key=lambda item: _search_score(antonym, item), default=None)
        if match and _search_score(antonym, match) > 25:
            opposite.append({
                "word": match.get("word"),
                "unit": match.get("unit"),
                "translation": match.get("translation", ""),
                "similarity": round(_search_score(antonym, match) / 120, 3),
            })

    return {"related": related, "opposite": opposite, "query": query}


@app.get("/api/relations")
def get_relations():
    if not RELATIONS_FILE.exists():
        return {}
    return json.loads(RELATIONS_FILE.read_text(encoding="utf-8"))
