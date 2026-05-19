from collections.abc import AsyncGenerator

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import DATABASE_URL


engine = create_async_engine(
    DATABASE_URL,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autoflush=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for async request-scoped database sessions."""
    async with AsyncSessionLocal() as session:
        yield session


async def create_all_tables() -> None:
    """Create all tables for local development / first migration phase."""
    from backend.orm import models  # noqa: F401 - ensure model classes are registered

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_user_word_progress_schema)


def _ensure_user_word_progress_schema(sync_conn) -> None:
    inspector = inspect(sync_conn)
    table_names = set(inspector.get_table_names())
    if "user_word_progress" not in table_names:
        return

    columns = {column["name"] for column in inspector.get_columns("user_word_progress")}
    alter_statements = []
    if "reps" not in columns:
        alter_statements.append("ALTER TABLE user_word_progress ADD COLUMN reps INTEGER NOT NULL DEFAULT 0")
    if "last_review" not in columns:
        alter_statements.append("ALTER TABLE user_word_progress ADD COLUMN last_review DATETIME")
    if "due" not in columns:
        alter_statements.append("ALTER TABLE user_word_progress ADD COLUMN due DATETIME")
    if "fsrs_step" not in columns:
        alter_statements.append("ALTER TABLE user_word_progress ADD COLUMN fsrs_step INTEGER")
    if "fsrs_card_id" not in columns:
        alter_statements.append("ALTER TABLE user_word_progress ADD COLUMN fsrs_card_id INTEGER")

    for statement in alter_statements:
        sync_conn.execute(text(statement))

    sync_conn.execute(
        text(
            """
            UPDATE user_word_progress
            SET reps = CASE
                WHEN reps IS NULL OR reps = 0 THEN COALESCE(review_count, 0)
                ELSE reps
            END,
                last_review = COALESCE(last_review, last_reviewed_at),
                due = COALESCE(due, next_review_at),
                fsrs_card_id = COALESCE(fsrs_card_id, word_id)
            """
        )
    )
    sync_conn.execute(text("CREATE INDEX IF NOT EXISTS ix_user_word_progress_due ON user_word_progress (due)"))
    sync_conn.execute(text("CREATE INDEX IF NOT EXISTS ix_user_word_progress_fsrs_card_id ON user_word_progress (fsrs_card_id)"))
