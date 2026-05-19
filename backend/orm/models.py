from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base


def utcnow() -> datetime:
    return datetime.utcnow()


class Word(Base):
    """Canonical word entry, independent from study units and user progress."""

    __tablename__ = "words"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    word: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    normalized: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    phonetic: Mapped[Optional[str]] = mapped_column(String(256))
    word_audio_path: Mapped[Optional[str]] = mapped_column(String(512))
    translation: Mapped[str] = mapped_column(Text, default="", nullable=False)
    definition: Mapped[Optional[str]] = mapped_column(Text)
    pos: Mapped[Optional[str]] = mapped_column(String(64))
    tags: Mapped[Optional[str]] = mapped_column(String(512))
    difficulty: Mapped[Optional[float]] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(64), default="legacy_json", nullable=False)
    extra: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    forms: Mapped[list["WordForm"]] = relationship(back_populates="word", cascade="all, delete-orphan")
    clusters: Mapped[list["WordCluster"]] = relationship(back_populates="word", cascade="all, delete-orphan")
    examples: Mapped[list["Example"]] = relationship(back_populates="word", cascade="all, delete-orphan")
    notes: Mapped[list["Note"]] = relationship(back_populates="word", cascade="all, delete-orphan")
    progress: Mapped[list["UserWordProgress"]] = relationship(back_populates="word", cascade="all, delete-orphan")


class WordForm(Base):
    __tablename__ = "word_forms"
    __table_args__ = (UniqueConstraint("word_id", "form", "form_type", name="uq_word_form"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id"), index=True, nullable=False)
    form: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    form_type: Mapped[str] = mapped_column(String(64), default="variant", nullable=False)

    word: Mapped[Word] = relationship(back_populates="forms")


class Cluster(Base):
    """Study unit / semantic cluster. Supports nested Unit -> SubUnit -> Topic."""

    __tablename__ = "clusters"

    __table_args__ = (UniqueConstraint("code", name="uq_cluster_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("clusters.id"), index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source: Mapped[str] = mapped_column(String(64), default="legacy_json", nullable=False)
    extra: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    parent: Mapped[Optional["Cluster"]] = relationship(remote_side=[id], back_populates="children")
    children: Mapped[list["Cluster"]] = relationship(back_populates="parent")
    words: Mapped[list["WordCluster"]] = relationship(back_populates="cluster", cascade="all, delete-orphan")


class WordCluster(Base):
    __tablename__ = "word_clusters"
    __table_args__ = (UniqueConstraint("word_id", "cluster_id", name="uq_word_cluster"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id"), index=True, nullable=False)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("clusters.id"), index=True, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    weight: Mapped[Optional[float]] = mapped_column(Float)

    word: Mapped[Word] = relationship(back_populates="clusters")
    cluster: Mapped[Cluster] = relationship(back_populates="words")


class Example(Base):
    """Default/user/movie/AI examples all live here as reusable resources."""

    __tablename__ = "examples"

    __table_args__ = (UniqueConstraint("word_id", "text", "source_type", name="uq_example_word_text_source"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id"), index=True, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    translation: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), default="user", index=True, nullable=False)
    source_name: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    audio_path: Mapped[Optional[str]] = mapped_column(String(512))
    video_path: Mapped[Optional[str]] = mapped_column(String(512))
    start_time: Mapped[Optional[float]] = mapped_column(Float)
    end_time: Mapped[Optional[float]] = mapped_column(Float)
    quality_score: Mapped[Optional[float]] = mapped_column(Float)
    extra: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    word: Mapped[Word] = relationship(back_populates="examples")
    notes: Mapped[list["Note"]] = relationship(back_populates="source_example")


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id"), index=True, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    source_example_id: Mapped[Optional[int]] = mapped_column(ForeignKey("examples.id"), index=True)
    source_note_id: Mapped[Optional[int]] = mapped_column(ForeignKey("notes.id"), index=True)
    is_synced_copy: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    extra: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    word: Mapped[Word] = relationship(back_populates="notes")
    source_example: Mapped[Optional[Example]] = relationship(back_populates="notes")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    settings: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    progress: Mapped[list["UserWordProgress"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    ai_sessions: Mapped[list["AISession"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class UserWordProgress(Base):
    __tablename__ = "user_word_progress"
    __table_args__ = (UniqueConstraint("user_id", "word_id", name="uq_user_word_progress"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id"), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="new", index=True, nullable=False)
    state: Mapped[int] = mapped_column(Integer, default=0, index=True, nullable=False)
    lapses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    memorized_past: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    memorized_today: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    review_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_review: Mapped[Optional[datetime]] = mapped_column(DateTime)
    next_review_at: Mapped[Optional[datetime]] = mapped_column(DateTime, index=True)
    due: Mapped[Optional[datetime]] = mapped_column(DateTime, index=True)
    stability: Mapped[Optional[float]] = mapped_column(Float)
    difficulty: Mapped[Optional[float]] = mapped_column(Float)
    retrievability: Mapped[Optional[float]] = mapped_column(Float)
    fsrs_step: Mapped[Optional[int]] = mapped_column(Integer)
    fsrs_card_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    extra: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    user: Mapped[User] = relationship(back_populates="progress")
    word: Mapped[Word] = relationship(back_populates="progress")


class AISession(Base):
    __tablename__ = "ai_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    word_id: Mapped[Optional[int]] = mapped_column(ForeignKey("words.id"), index=True)
    mode: Mapped[str] = mapped_column(String(64), default="socratic", nullable=False)
    stage: Mapped[str] = mapped_column(String(64), default="intro", nullable=False)
    context: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    user: Mapped[User] = relationship(back_populates="ai_sessions")
    messages: Mapped[list["AIMessage"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class AIMessage(Base):
    __tablename__ = "ai_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("ai_sessions.id"), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    extra: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    session: Mapped[AISession] = relationship(back_populates="messages")
