from pathlib import Path
import json
from typing import List, Dict, Optional
from threading import Lock
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SUMMARY_DIR = DATA_DIR / "unit_summaries"
DATA_DIR.mkdir(exist_ok=True, parents=True)
SUMMARY_DIR.mkdir(exist_ok=True, parents=True)

file_lock = Lock()


def unit_file(unit_id: str) -> Path:
    return DATA_DIR / f"{unit_id}.json"


def summary_file(unit_id: str) -> Path:
    return SUMMARY_DIR / f"{unit_id}.md"


def load_units_index() -> List[Dict]:
    idx = DATA_DIR / "units.json"
    if not idx.exists():
        return []
    return json.loads(idx.read_text(encoding="utf-8"))


def list_units() -> List[Dict]:
    entries = load_units_index()
    if entries:
        return entries

    units = []
    for path in sorted(DATA_DIR.glob("Unit_*_Sub*.json")):
        try:
            words = json.loads(path.read_text(encoding="utf-8"))
            units.append({"unit": path.stem, "count": len(words)})
        except Exception:
            continue
    return units


def load_words(unit_id: str) -> List[Dict]:
    path = unit_file(unit_id)
    if not path.exists():
        raise FileNotFoundError(f"Unit not found: {unit_id}")
    return [_normalize_word_entry(item) for item in json.loads(path.read_text(encoding="utf-8"))]


def _note_id(unit_id: str, word: str, index: int) -> str:
    safe_word = "".join(ch if ch.isalnum() else "_" for ch in word.lower())
    return f"note_{unit_id}_{safe_word}_{index + 1}"


def _normalize_notes(entry: Dict) -> List[Dict]:
    """Return independent note objects while keeping old `notes` string compatible."""
    raw_notes_v2 = entry.get("notes_v2")
    if isinstance(raw_notes_v2, list):
        normalized = []
        for index, note in enumerate(raw_notes_v2):
            if isinstance(note, dict):
                text = str(note.get("text", ""))
                normalized.append({
                    "id": note.get("id") or _note_id(entry.get("unit", "unit"), entry.get("word", "word"), index),
                    "text": text,
                    "links": note.get("links") if isinstance(note.get("links"), list) else [],
                    "created_at": note.get("created_at"),
                    "updated_at": note.get("updated_at"),
                })
            elif str(note).strip():
                normalized.append({
                    "id": _note_id(entry.get("unit", "unit"), entry.get("word", "word"), index),
                    "text": str(note),
                    "links": [],
                    "created_at": None,
                    "updated_at": None,
                })
        return normalized

    legacy = str(entry.get("notes") or "").strip()
    if not legacy:
        return []
    parts = [part.strip() for part in legacy.split("\n") if part.strip()]
    return [{
        "id": _note_id(entry.get("unit", "unit"), entry.get("word", "word"), index),
        "text": part,
        "links": [],
        "created_at": None,
        "updated_at": None,
    } for index, part in enumerate(parts)]


def _normalize_word_entry(entry: Dict) -> Dict:
    item = entry.copy()
    item.setdefault("notes", "")
    item["notes_v2"] = _normalize_notes(item)
    item["notes"] = "\n".join(note.get("text", "") for note in item["notes_v2"] if note.get("text", "").strip())
    item.setdefault("example_sentences", [])
    return item


def save_words(unit_id: str, words: List[Dict]) -> None:
    path = unit_file(unit_id)
    with file_lock:
        tmp = DATA_DIR / f".{unit_id}.tmp"
        tmp.write_text(json.dumps(words, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)


def update_word_status(unit_id: str, word: str, memorized_past: Optional[bool] = None, memorized_today: Optional[bool] = None, last_reviewed: Optional[str] = None):
    words = load_words(unit_id)
    changed = False
    for entry in words:
        if entry.get("word") == word:
            st = entry.setdefault("status", {})
            if memorized_past is not None:
                st["memorized_past"] = bool(memorized_past)
                changed = True
            if memorized_today is not None:
                today = datetime.utcnow().date().isoformat()
                last_today = st.get("last_today", "")
                if bool(memorized_today):
                    if last_today != today:
                        st["review_count"] = st.get("review_count", 0) + 1
                        st["last_today"] = today
                    # else: already reviewed today, no +1
                else:
                    if last_today == today:
                        st["review_count"] = max(0, st.get("review_count", 0) - 1)
                        st["last_today"] = ""
                st["memorized_today"] = bool(memorized_today)
                changed = True
            if last_reviewed is not None:
                st["last_reviewed"] = last_reviewed
                changed = True
            break
    if changed:
        save_words(unit_id, words)
        return entry
    raise ValueError(f"Word not found: {word}")


def update_notes(unit_id: str, word: str, notes: str, notes_v2: Optional[List[Dict]] = None) -> Dict:
    words = load_words(unit_id)
    changed = False
    for entry in words:
        if entry.get("word") == word:
            entry["notes"] = notes
            if notes_v2 is not None:
                entry["notes_v2"] = _normalize_notes({**entry, "notes_v2": notes_v2})
                entry["notes"] = "\n".join(note.get("text", "") for note in entry["notes_v2"] if note.get("text", "").strip())
            changed = True
            break
    if not changed:
        raise ValueError(f"Word not found: {word}")
    save_words(unit_id, words)
    return entry


def enrich_word(unit_id: str, word: str, pos: Optional[str] = None, definitions: Optional[List[str]] = None, example_sentences: Optional[List[str]] = None, chinese: Optional[str] = None) -> Dict:
    words = load_words(unit_id)
    changed = False
    for entry in words:
        if entry.get("word") == word:
            if pos is not None:
                entry["pos"] = pos
                changed = True
            if definitions is not None:
                entry["definitions"] = definitions
                changed = True
            if example_sentences is not None:
                entry["example_sentences"] = example_sentences
                changed = True
            if chinese is not None:
                entry["chinese"] = chinese
                changed = True
            break
    if not changed:
        raise ValueError(f"Word not found: {word}")
    save_words(unit_id, words)
    return entry


def load_unit_summary(unit_id: str) -> str:
    path = summary_file(unit_id)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def save_unit_summary(unit_id: str, summary: str) -> str:
    path = summary_file(unit_id)
    path.write_text(summary, encoding="utf-8")
    return summary


def load_relations() -> Dict:
    path = DATA_DIR / "relations.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))

