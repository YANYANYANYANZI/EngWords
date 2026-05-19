from collections.abc import AsyncGenerator

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
