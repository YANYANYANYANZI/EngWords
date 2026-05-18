from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict
from datetime import datetime
from functools import lru_cache
import difflib
import re
from sqlalchemy import and_, delete, func, select
from sqlalchemy.orm import selectinload

from . import db
from .core.database import AsyncSessionLocal
from .models import (
    UnitInfo,
    WordEntry,
    UpdateWordRequest,
    UpdateNoteRequest,
    EnrichWordRequest,
    UnitSummaryRequest,
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


@app.get("/api/db_health")
async def get_db_health():
    """Lightweight async health check for the new SQLAlchemy/SQLite data layer.

    Phase 1 keeps the old JSON-backed APIs unchanged; this endpoint only reports
    whether the new database is reachable and how much legacy data was imported.
    """
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


@lru_cache(maxsize=1)
def get_word_corpus():
    """Load all words once for fast local search/dictionary fallback."""
    rows = []
    for unit in db.list_units():
        unit_id = unit["unit"]
        for w in db.load_words(unit_id):
            item = w.copy()
            item["unit"] = unit_id
            item["_haystack"] = " ".join([
                item.get("word", ""),
                item.get("translation", ""),
                item.get("chinese", "") or "",
                " ".join(item.get("definitions") or []),
            ]).lower()
            rows.append(item)
    return rows


def _search_score(query: str, item: Dict) -> float:
    q = _norm(query)
    word = _norm(item.get("word", ""))
    haystack = item.get("_haystack", "")
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


def _wordnet_lookup(word: str):
    """Best-effort WordNet lookup. Never downloads at request time."""
    try:
        from nltk.corpus import wordnet as wn
        synsets = wn.synsets(word)
    except Exception:
        return []
    senses = []
    for s in synsets[:4]:
        lemmas = s.lemmas()
        synonyms = sorted({l.name().replace("_", " ") for l in lemmas if l.name().lower() != word.lower()})[:6]
        antonyms = sorted({a.name().replace("_", " ") for l in lemmas for a in l.antonyms()})[:6]
        senses.append({
            "pos": s.pos(),
            "definition": s.definition(),
            "examples": s.examples(),
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
    cleaned = [e for e in (examples or []) if e and not _is_low_quality_example(e, word)]
    return cleaned[:3] if cleaned else _template_examples(word, translation)


def _default_example(word: str, translation: str) -> str:
    return _template_examples(word, translation)[0]


def _with_default_example(entry: Dict) -> Dict:
    item = entry.copy()
    item["default_example"] = _default_example(item.get("word", ""), item.get("translation", ""))
    return item


def _dt_to_iso(value):
    return value.isoformat() + "Z" if value else None


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


def _word_to_frontend_entry(word: Word, unit_id: str, progress: UserWordProgress | None = None) -> Dict:
    user_examples = [example.text for example in word.examples if example.source_type != "default"]
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
    return _with_default_example({
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
    })


async def _get_db_word_entry(session, unit_id: str, word_text: str) -> Dict:
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


@app.get("/api/db/units", response_model=List[UnitInfo])
async def get_db_units():
    """Read units from the new async SQLAlchemy data layer, preserving the old API shape."""
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
    """Read one unit from SQLite while returning the frontend-compatible word shape."""
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


@app.get("/api/db/dashboard")
async def get_db_dashboard():
    async with AsyncSessionLocal() as session:
        user_id = await _get_default_user_id(session)
        total_words = await session.scalar(select(func.count()).select_from(Word)) or 0
        progress_rows = (await session.execute(select(UserWordProgress).where(UserWordProgress.user_id == user_id))).scalars().all()
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
        progress = await session.scalar(select(UserWordProgress).where(UserWordProgress.user_id == user_id, UserWordProgress.word_id == word.id))
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


@app.get("/api/units", response_model=List[UnitInfo])
def get_units():
    units = db.list_units()
    return units


@app.get("/api/words/{unit_id}", response_model=List[WordEntry])
def get_unit_words(unit_id: str):
    try:
        words = [_with_default_example(w) for w in db.load_words(unit_id)]
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="unit not found")
    return words


@app.post("/api/update_word", response_model=WordEntry)
def update_word(req: UpdateWordRequest):
    now = datetime.utcnow().isoformat() + "Z"
    try:
        updated = db.update_word_status(
            req.unit,
            req.word,
            memorized_past=req.memorized_past,
            memorized_today=req.memorized_today,
            last_reviewed=now,
        )
        get_word_corpus.cache_clear()
        return WordEntry(**_with_default_example(updated))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="unit not found")
    except ValueError as ex:
        raise HTTPException(status_code=404, detail=str(ex))


@app.post("/api/update_note", response_model=WordEntry)
def update_note(req: UpdateNoteRequest):
    try:
        updated = db.update_notes(req.unit, req.word, req.notes, req.notes_v2)
        get_word_corpus.cache_clear()
        return WordEntry(**_with_default_example(updated))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="unit not found")
    except ValueError as ex:
        raise HTTPException(status_code=404, detail=str(ex))


@app.post("/api/enrich_word", response_model=WordEntry)
def enrich_word(req: EnrichWordRequest):
    try:
        updated = db.enrich_word(
            req.unit,
            req.word,
            pos=req.pos,
            definitions=req.definitions,
            example_sentences=req.example_sentences,
            chinese=req.chinese,
        )
        get_word_corpus.cache_clear()
        return WordEntry(**_with_default_example(updated))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="unit not found")
    except ValueError as ex:
        raise HTTPException(status_code=404, detail=str(ex))


@app.get("/api/unit_summary/{unit_id}")
def get_unit_summary(unit_id: str):
    try:
        return {"unit": unit_id, "summary": db.load_unit_summary(unit_id)}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="unit not found")


@app.post("/api/unit_summary", response_model=Dict[str, str])
def post_unit_summary(req: UnitSummaryRequest):
    try:
        summary = db.save_unit_summary(req.unit, req.summary)
        return {"unit": req.unit, "summary": summary}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@app.get("/api/dict/{word}")
def query_dict(word: str):
    corpus = get_word_corpus()
    local = next((x for x in corpus if _norm(x.get("word")) == _norm(word)), None)
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
        senses[0]["examples"] = _usable_examples(senses[0].get("examples") or local.get("example_sentences") or [], word, local.get("translation", ""))

    return {"word": word, "senses": senses, "source": "wordnet+local" if senses else "empty"}


@app.get("/api/search/{query}")
def semantic_search(query: str, limit: int = Query(12, ge=1, le=50)):
    try:
        corpus = get_word_corpus()
        scored = []
        for item in corpus:
            score = _search_score(query, item)
            if score > 12:
                scored.append((score, item))
        scored.sort(key=lambda x: x[0], reverse=True)

        related = [{
            "word": item.get("word"),
            "unit": item.get("unit"),
            "translation": item.get("translation", ""),
            "similarity": round(min(score / 120, 1), 3),
        } for score, item in scored[:limit]]

        opposite = []
        senses = _wordnet_lookup(query)
        antonyms = [a for s in senses for a in s.get("antonyms", [])]
        for ant in antonyms[:6]:
            match = max(corpus, key=lambda x: _search_score(ant, x), default=None)
            if match and _search_score(ant, match) > 25:
                opposite.append({
                    "word": match.get("word"),
                    "unit": match.get("unit"),
                    "translation": match.get("translation", ""),
                    "similarity": round(_search_score(ant, match) / 120, 3),
                })

        return {"related": related, "opposite": opposite, "query": query}

    except Exception as ex:
        return {"related": [], "opposite": [], "error": str(ex)}


@app.get("/api/dashboard")
def get_dashboard():
    try:
        units = db.list_units()
        total_words = 0
        reviewed_today = 0
        total_reviews = 0
        past_memorized = 0
        today = datetime.utcnow().date().isoformat()

        for unit in units:
            words = db.load_words(unit['unit'])
            total_words += len(words)
            for w in words:
                st = w.get('status', {})
                total_reviews += st.get('review_count', 0)
                if st.get('memorized_past'):
                    past_memorized += 1
                if st.get('memorized_today') and st.get('last_today') == today:
                    reviewed_today += 1

        review_rate = (reviewed_today / total_words * 100) if total_words > 0 else 0
        today_goal = 50  # 示例目标
        progress = min(100, reviewed_today / today_goal * 100)

        # 遗忘曲线数据：简化，假设间隔
        forget_curve = [1, 0.8, 0.6, 0.4, 0.2]  # 示例

        return {
            "total_words": total_words,
            "reviewed_today": reviewed_today,
            "total_reviews": total_reviews,
            "past_memorized": past_memorized,
            "review_rate": review_rate,
            "today_goal": today_goal,
            "progress": progress,
            "forget_curve": forget_curve
        }

    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@app.get("/api/all_words")
def get_all_words():
    try:
        results = []
        for unit in db.list_units():
            words = db.load_words(unit['unit'])
            for w in words:
                entry = w.copy()
                entry['unit'] = unit['unit']
                results.append(_with_default_example(entry))
        return results
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@app.get("/api/relations")
def get_relations():
    try:
        return db.load_relations()
    except Exception as ex:
        return {}

