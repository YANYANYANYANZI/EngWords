from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict
from datetime import datetime
from functools import lru_cache
import difflib
import re

from . import db
from .models import (
    UnitInfo,
    WordEntry,
    UpdateWordRequest,
    UpdateNoteRequest,
    EnrichWordRequest,
    UnitSummaryRequest,
)

app = FastAPI(title="VocabOS API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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

