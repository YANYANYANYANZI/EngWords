import json
import os
import re
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

import difflib
from dotenv import load_dotenv
from fsrs import Card, Rating, Scheduler, State

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
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.orm import selectinload

from .core.config import BASE_DIR
from .core.database import AsyncSessionLocal, create_all_tables
from .models import (
    EnrichWordRequest,
    StudyRatingResult,
    StudyReviewRequest,
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
FSRS_DESIRED_RETENTION = float(os.getenv("VOCABOS_FSRS_DESIRED_RETENTION", "0.9"))
FSRS_MAXIMUM_INTERVAL = int(os.getenv("VOCABOS_FSRS_MAXIMUM_INTERVAL", "3650"))
FSRS_ENABLE_FUZZING = os.getenv("VOCABOS_FSRS_ENABLE_FUZZING", "true").strip().lower() not in {"0", "false", "no"}
STUDY_NEW_LIMIT_DEFAULT = int(os.getenv("VOCABOS_STUDY_NEW_LIMIT", "20"))
STUDY_REVIEW_LIMIT_DEFAULT = int(os.getenv("VOCABOS_STUDY_REVIEW_LIMIT", "50"))
SESSION_REQUEUE_WINDOW_MINUTES = int(os.getenv("VOCABOS_SESSION_REQUEUE_WINDOW_MINUTES", "15"))
FSRS_SCHEDULER = Scheduler(
    desired_retention=FSRS_DESIRED_RETENTION,
    maximum_interval=FSRS_MAXIMUM_INTERVAL,
    enable_fuzzing=FSRS_ENABLE_FUZZING,
)




@app.on_event("startup")
async def on_startup() -> None:
    await create_all_tables()


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
    value = _to_utc(value)
    return value.isoformat().replace("+00:00", "Z") if value else None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _to_db_utc(value: datetime | None) -> datetime | None:
    value = _to_utc(value)
    return value.replace(tzinfo=None) if value else None


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


def _pick_example_by_source(examples: List[Example], source_type: str) -> Example | None:
    wanted = (source_type or "").strip().lower()
    matches = [example for example in (examples or []) if (example.source_type or "").strip().lower() == wanted and example.text]
    if not matches:
        return None
    matches.sort(key=lambda example: (-(example.quality_score or 0), len(example.text or ""), example.id or 0))
    return matches[0]


def _progress_state_value(progress: UserWordProgress | None) -> int:
    if not progress:
        return State.Learning.value
    return progress.state if progress.state in {1, 2, 3} else State.Learning.value


def _progress_reps(progress: UserWordProgress | None) -> int:
    if not progress:
        return 0
    return max(progress.reps or 0, progress.review_count or 0)


def _progress_due(progress: UserWordProgress | None) -> datetime | None:
    if not progress:
        return None
    return _to_utc(progress.due or progress.next_review_at)


def _progress_last_review(progress: UserWordProgress | None) -> datetime | None:
    if not progress:
        return None
    return _to_utc(progress.last_review or progress.last_reviewed_at)


def _progress_to_card(progress: UserWordProgress, now: datetime) -> Card:
    if progress.stability is None or progress.difficulty is None:
        reps = max(1, min(_progress_reps(progress), 3))
        seed_card = Card(card_id=progress.fsrs_card_id or progress.word_id)
        for offset in range(reps):
            review_time = now - timedelta(days=max(reps - offset, 1))
            seed_card, _ = FSRS_SCHEDULER.review_card(seed_card, Rating.Good, review_datetime=review_time)
        return Card(
            card_id=seed_card.card_id,
            state=State.Review if _progress_reps(progress) > 0 else State.Learning,
            step=seed_card.step,
            stability=seed_card.stability,
            difficulty=seed_card.difficulty,
            due=_progress_due(progress) or now,
            last_review=_progress_last_review(progress) or seed_card.last_review,
        )
    return Card(
        card_id=progress.fsrs_card_id or progress.word_id,
        state=State(_progress_state_value(progress)),
        step=progress.fsrs_step,
        stability=progress.stability,
        difficulty=progress.difficulty,
        due=_progress_due(progress) or now,
        last_review=_progress_last_review(progress),
    )


def _study_status(progress: UserWordProgress | None) -> Dict[str, Any]:
    return {
        "memorized_past": bool(progress.memorized_past) if progress else False,
        "memorized_today": bool(progress.memorized_today) if progress else False,
        "last_reviewed": _dt_to_iso(progress.last_reviewed_at) if progress else None,
        "review_count": progress.review_count if progress else 0,
        "state": _progress_state_value(progress) if progress else State.Learning.value,
        "stability": progress.stability if progress else None,
        "difficulty": progress.difficulty if progress else None,
        "retrievability": progress.retrievability if progress else None,
        "lapses": progress.lapses if progress else 0,
        "reps": _progress_reps(progress),
        "due": _dt_to_iso(_progress_due(progress)),
        "last_review": _dt_to_iso(_progress_last_review(progress)),
    }


def _merge_study_queue(review_cards: List[Dict[str, Any]], new_cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    queue: List[Dict[str, Any]] = []
    review_index = 0
    new_index = 0
    while review_index < len(review_cards) or new_index < len(new_cards):
        for _ in range(2):
            if review_index < len(review_cards):
                queue.append(review_cards[review_index])
                review_index += 1
        if new_index < len(new_cards):
            queue.append(new_cards[new_index])
            new_index += 1
        if review_index >= len(review_cards) and new_index < len(new_cards):
            queue.extend(new_cards[new_index:])
            break
        if new_index >= len(new_cards) and review_index < len(review_cards):
            queue.extend(review_cards[review_index:])
            break
    return queue


def _study_card_payload(word: Word, unit_id: str, progress: UserWordProgress | None, queue_kind: str) -> Dict[str, Any]:
    default_example = _select_default_example_text(word.examples, word.word, word.translation or "")
    tatoeba_example = _pick_example_by_source(word.examples, "tatoeba")
    ai_example = _pick_example_by_source(word.examples, "ai")
    notes = [{
        "id": f"db_note_{note.id}",
        "text": note.text,
        "links": note.extra.get("links", []) if isinstance(note.extra, dict) else [],
        "created_at": _dt_to_iso(note.created_at),
        "updated_at": _dt_to_iso(note.updated_at),
    } for note in (word.notes or [])]
    user_examples = _select_user_examples(word.examples, word.word)
    return {
        "word_id": word.id,
        "word": word.word,
        "unit": unit_id,
        "queue_kind": queue_kind,
        "phonetic": word.phonetic or "",
        "translation": word.translation or "",
        "chinese": word.translation or "",
        "pos": word.pos or "",
        "tags": word.tags or "",
        "definitions": [line.strip() for line in (word.definition or "").splitlines() if line.strip()],
        "default_example": default_example,
        "example_sentences": user_examples,
        "notes": "\n".join(note["text"] for note in notes if note.get("text")),
        "notes_v2": notes,
        "tatoeba_example": {
            "text": tatoeba_example.text,
            "translation": tatoeba_example.translation or "",
        } if tatoeba_example else None,
        "ai_example": {
            "text": ai_example.text,
            "translation": ai_example.translation or "",
        } if ai_example else None,
        "status": _study_status(progress),
    }


def _apply_review_result(
    progress: UserWordProgress,
    card: Card,
    rating_value: int,
    review_time: datetime,
) -> StudyRatingResult:
    progress.fsrs_card_id = card.card_id
    progress.fsrs_step = card.step
    progress.state = int(card.state.value)
    progress.stability = card.stability
    progress.difficulty = card.difficulty
    progress.last_review = _to_db_utc(card.last_review or review_time)
    progress.last_reviewed_at = progress.last_review
    progress.due = _to_db_utc(card.due)
    progress.next_review_at = progress.due
    progress.reps = _progress_reps(progress) + 1
    progress.review_count = progress.reps
    if rating_value == int(Rating.Again):
        progress.lapses = (progress.lapses or 0) + 1
    progress.memorized_past = progress.reps > 0
    progress.memorized_today = True
    progress.retrievability = FSRS_SCHEDULER.get_card_retrievability(card, current_datetime=review_time)
    progress.status = "review" if progress.state == State.Review.value else "learning"
    extra = dict(progress.extra or {})
    extra["last_rating"] = int(rating_value)
    progress.extra = extra

    due_utc = _to_utc(card.due) or review_time
    due_in_seconds = max(0, int((due_utc - review_time).total_seconds()))
    return StudyRatingResult(
        rating=int(rating_value),
        due=_dt_to_iso(card.due),
        due_in_seconds=due_in_seconds,
        requeue_in_session=due_in_seconds <= SESSION_REQUEUE_WINDOW_MINUTES * 60,
        state=progress.state,
        reps=progress.reps,
        lapses=progress.lapses,
        stability=progress.stability,
        difficulty=progress.difficulty,
        retrievability=progress.retrievability,
    )


def _tts_request_payload(word: str) -> Dict[str, Any]:
    if not TTS_REF_AUDIO_PATH:
        raise HTTPException(
            status_code=503,
            detail="VOCABOS_TTS_REF_AUDIO_PATH is not configured",
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
    status = _study_status(progress)
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


@app.get("/api/db/study/today")
async def get_study_today(
    new_limit: int = Query(STUDY_NEW_LIMIT_DEFAULT, ge=0, le=100),
    review_limit: int = Query(STUDY_REVIEW_LIMIT_DEFAULT, ge=0, le=200),
    unit: str | None = Query(None),
):
    async with AsyncSessionLocal() as session:
        user_id = await _get_default_user_id(session)
        now = _utc_now()
        unit_code = unit.strip() if unit and unit.strip() else None

        review_rows = (
            await session.execute(
                select(Word, Cluster.code, UserWordProgress)
                .join(WordCluster, WordCluster.word_id == Word.id)
                .join(Cluster, Cluster.id == WordCluster.cluster_id)
                .join(
                    UserWordProgress,
                    and_(UserWordProgress.word_id == Word.id, UserWordProgress.user_id == user_id),
                )
                .options(selectinload(Word.examples), selectinload(Word.notes))
                .where(
                    or_(
                        UserWordProgress.due <= _to_db_utc(now),
                        and_(
                            UserWordProgress.due.is_(None),
                            or_(
                                UserWordProgress.next_review_at <= _to_db_utc(now),
                                UserWordProgress.next_review_at.is_(None),
                            ),
                        ),
                    ),
                    func.coalesce(UserWordProgress.reps, UserWordProgress.review_count, 0) > 0,
                    Cluster.code == unit_code if unit_code else True,
                )
                .order_by(
                    func.coalesce(
                        UserWordProgress.due,
                        UserWordProgress.next_review_at,
                        UserWordProgress.last_review,
                        UserWordProgress.last_reviewed_at,
                        UserWordProgress.created_at,
                    ),
                    Cluster.code,
                    WordCluster.position,
                )
                .limit(review_limit)
            )
        ).all()

        new_rows = (
            await session.execute(
                select(Word, Cluster.code, UserWordProgress)
                .join(WordCluster, WordCluster.word_id == Word.id)
                .join(Cluster, Cluster.id == WordCluster.cluster_id)
                .outerjoin(
                    UserWordProgress,
                    and_(UserWordProgress.word_id == Word.id, UserWordProgress.user_id == user_id),
                )
                .options(selectinload(Word.examples))
                .options(selectinload(Word.notes))
                .where(func.coalesce(UserWordProgress.reps, UserWordProgress.review_count, 0) == 0)
                .where(Cluster.code == unit_code if unit_code else True)
                .order_by(Cluster.code, WordCluster.position, Word.word)
                .limit(new_limit)
            )
        ).all()

        review_cards = [_study_card_payload(word, unit_id, progress, "review") for word, unit_id, progress in review_rows]
        new_cards = [_study_card_payload(word, unit_id, progress, "new") for word, unit_id, progress in new_rows]

        total_due_reviews = await session.scalar(
            select(func.count())
            .select_from(UserWordProgress)
            .join(Word, Word.id == UserWordProgress.word_id)
            .join(WordCluster, WordCluster.word_id == Word.id)
            .join(Cluster, Cluster.id == WordCluster.cluster_id)
            .where(
                UserWordProgress.user_id == user_id,
                func.coalesce(UserWordProgress.reps, UserWordProgress.review_count, 0) > 0,
                Cluster.code == unit_code if unit_code else True,
                or_(
                    UserWordProgress.due <= _to_db_utc(now),
                    and_(
                        UserWordProgress.due.is_(None),
                        or_(
                            UserWordProgress.next_review_at <= _to_db_utc(now),
                            UserWordProgress.next_review_at.is_(None),
                        ),
                    ),
                ),
            )
        ) or 0
        total_new_cards = await session.scalar(
            select(func.count())
            .select_from(Word)
            .join(WordCluster, WordCluster.word_id == Word.id)
            .join(Cluster, Cluster.id == WordCluster.cluster_id)
            .outerjoin(
                UserWordProgress,
                and_(UserWordProgress.word_id == Word.id, UserWordProgress.user_id == user_id),
            )
            .where(func.coalesce(UserWordProgress.reps, UserWordProgress.review_count, 0) == 0)
            .where(Cluster.code == unit_code if unit_code else True)
        ) or 0

        return {
            "generated_at": _dt_to_iso(now),
            "unit": unit_code,
            "stats": {
                "new_limit": new_limit,
                "review_limit": review_limit,
                "new_remaining": len(new_cards),
                "review_remaining": len(review_cards),
                "new_total": total_new_cards,
                "review_total": total_due_reviews,
            },
            "queue": _merge_study_queue(review_cards, new_cards),
        }


@app.post("/api/db/study/review")
async def post_study_review(req: StudyReviewRequest):
    if req.rating not in {1, 2, 3, 4}:
        raise HTTPException(status_code=400, detail="rating must be one of 1, 2, 3, 4")

    async with AsyncSessionLocal() as session:
        user_id = await _get_default_user_id(session)
        row = (
            await session.execute(
                select(Word, Cluster.code, UserWordProgress)
                .join(WordCluster, WordCluster.word_id == Word.id)
                .join(Cluster, Cluster.id == WordCluster.cluster_id)
                .outerjoin(
                    UserWordProgress,
                    and_(UserWordProgress.word_id == Word.id, UserWordProgress.user_id == user_id),
                )
                .options(selectinload(Word.examples))
                .options(selectinload(Word.notes))
                .where(Word.id == req.word_id)
                .order_by(WordCluster.position)
                .limit(1)
            )
        ).first()
        if not row:
            raise HTTPException(status_code=404, detail="word not found")

        word, unit_id, progress = row
        if not progress:
            progress = UserWordProgress(
                user_id=user_id,
                word_id=word.id,
                status="new",
                state=State.Learning.value,
                fsrs_card_id=word.id,
                reps=0,
                review_count=0,
                lapses=0,
            )
            session.add(progress)
            await session.flush()

        review_time = _utc_now()
        card = _progress_to_card(progress, review_time)
        reviewed_card, _review_log = FSRS_SCHEDULER.review_card(card, Rating(req.rating), review_datetime=review_time)
        result = _apply_review_result(progress, reviewed_card, req.rating, review_time)
        await session.commit()

        queue_kind = "review" if progress.reps > 1 else "new"
        return {
            "ok": True,
            "review": result.model_dump(),
            "card": _study_card_payload(word, unit_id, progress, queue_kind),
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
                    progress.reps = max(progress.reps or 0, progress.review_count)
                progress.state = State.Review.value
                progress.status = "review"
                now = _to_db_utc(_utc_now())
                progress.last_reviewed_at = now
                progress.last_review = now
                progress.next_review_at = progress.next_review_at or now
                progress.due = progress.due or progress.next_review_at
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
