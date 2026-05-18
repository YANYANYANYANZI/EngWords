from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class WordStatus(BaseModel):
    memorized_past: bool
    memorized_today: bool
    last_reviewed: Optional[str]
    review_count: int


class WordEntry(BaseModel):
    word: str
    translation: str
    unit: str
    status: WordStatus
    notes: str
    notes_v2: Optional[List[Dict[str, Any]]] = None
    phonetic: Optional[str] = None
    tags: Optional[str] = None
    pos: Optional[str] = None
    definitions: Optional[List[str]] = None
    example_sentences: Optional[List[str]] = None
    chinese: Optional[str] = None
    default_example: Optional[str] = None


class UnitInfo(BaseModel):
    unit: str
    count: int
    updated_at: Optional[str]
    title: Optional[str] = None


class UpdateWordRequest(BaseModel):
    unit: str
    word: str
    memorized_past: Optional[bool] = None
    memorized_today: Optional[bool] = None


class UpdateNoteRequest(BaseModel):
    unit: str
    word: str
    notes: str = ""
    notes_v2: Optional[List[Dict[str, Any]]] = None


class EnrichWordRequest(BaseModel):
    unit: str
    word: str
    pos: Optional[str] = None
    definitions: Optional[List[str]] = None
    example_sentences: Optional[List[str]] = None
    chinese: Optional[str] = None


class UnitSummaryRequest(BaseModel):
    unit: str
    summary: str
