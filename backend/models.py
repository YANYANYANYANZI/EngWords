from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class WordStatus(BaseModel):
    memorized_past: bool
    memorized_today: bool
    last_reviewed: Optional[str]
    review_count: int
    state: Optional[int] = None
    stability: Optional[float] = None
    difficulty: Optional[float] = None
    retrievability: Optional[float] = None
    lapses: Optional[int] = None
    reps: Optional[int] = None
    due: Optional[str] = None
    last_review: Optional[str] = None


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


class StudyReviewRequest(BaseModel):
    word_id: int
    rating: int


class StudyRatingResult(BaseModel):
    rating: int
    due: Optional[str]
    due_in_seconds: int
    requeue_in_session: bool
    state: int
    reps: int
    lapses: int
    stability: Optional[float] = None
    difficulty: Optional[float] = None
    retrievability: Optional[float] = None


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


class SwapExampleRequest(BaseModel):
    word: str
    target_example: str


class UnitSummaryRequest(BaseModel):
    unit: str
    summary: str
