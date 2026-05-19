"""Import existing Unit_*.json files into the new SQLAlchemy schema.

This script is intentionally idempotent-ish for Phase 1: it upserts words,
clusters, examples, notes and the default local user's progress without deleting
anything. The old JSON files remain the source of truth until APIs are switched
to the database in a later phase.

Run from the project root:

    python -m data_pipeline.import_legacy_json
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import DATA_DIR
from backend.core.database import AsyncSessionLocal, create_all_tables
from backend.orm import Cluster, Example, Note, User, UserWordProgress, Word, WordCluster


def normalize_word(value: str) -> str:
    return (value or "").strip().lower()


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).replace(tzinfo=None)
    except ValueError:
        return None


def split_notes(entry: dict[str, Any]) -> list[dict[str, Any]]:
    notes_v2 = entry.get("notes_v2")
    if isinstance(notes_v2, list):
        result = []
        for item in notes_v2:
            if isinstance(item, dict) and str(item.get("text", "")).strip():
                result.append(item)
            elif isinstance(item, str) and item.strip():
                result.append({"text": item.strip()})
        return result
    legacy = str(entry.get("notes") or "").strip()
    return [{"text": part.strip()} for part in legacy.split("\n") if part.strip()]


async def get_or_create_default_user(session: AsyncSession) -> User:
    user = await session.scalar(select(User).where(User.name == "local"))
    if user:
        return user
    user = User(name="local", is_default=True)
    session.add(user)
    await session.flush()
    return user


async def get_or_create_cluster(session: AsyncSession, unit_id: str, sort_order: int) -> Cluster:
    cluster = await session.scalar(select(Cluster).where(Cluster.code == unit_id))
    if cluster:
        return cluster
    cluster = Cluster(
        code=unit_id,
        name=unit_id.replace("_", " "),
        source="legacy_json",
        sort_order=sort_order,
        extra={"legacy_unit": unit_id},
    )
    session.add(cluster)
    await session.flush()
    return cluster


async def get_or_create_word(session: AsyncSession, entry: dict[str, Any]) -> Word:
    raw_word = str(entry.get("word") or "").strip()
    normalized = normalize_word(raw_word)
    word = await session.scalar(select(Word).where(Word.normalized == normalized))
    if not word:
        word = Word(word=raw_word, normalized=normalized)
        session.add(word)
        await session.flush()

    word.translation = str(entry.get("translation") or word.translation or "")
    word.pos = entry.get("pos") or word.pos
    definitions = entry.get("definitions") or []
    if definitions and not word.definition:
        word.definition = "\n".join(str(item) for item in definitions if item)
    word.extra = {
        **(word.extra or {}),
        "legacy_unit": entry.get("unit"),
        "chinese": entry.get("chinese"),
        "legacy_definitions": definitions,
    }
    return word


async def link_word_cluster(
    session: AsyncSession,
    word: Word,
    cluster: Cluster,
    position: int,
    cluster_link_cache: dict[tuple[int, int], WordCluster],
) -> None:
    cache_key = (word.id, cluster.id)
    exists = cluster_link_cache.get(cache_key)
    if not exists:
        exists = await session.scalar(
            select(WordCluster).where(WordCluster.word_id == word.id, WordCluster.cluster_id == cluster.id)
        )
    if exists:
        exists.position = position
        cluster_link_cache[cache_key] = exists
        return
    link = WordCluster(word_id=word.id, cluster_id=cluster.id, position=position)
    session.add(link)
    cluster_link_cache[cache_key] = link


async def import_examples(session: AsyncSession, word: Word, entry: dict[str, Any]) -> None:
    for sentence in entry.get("example_sentences") or []:
        text = str(sentence or "").strip()
        if not text:
            continue
        exists = await session.scalar(
            select(Example).where(
                Example.word_id == word.id,
                Example.text == text,
                Example.source_type == "user",
            )
        )
        if not exists:
            session.add(Example(word_id=word.id, text=text, source_type="user", source_name="legacy_json"))


async def import_notes(session: AsyncSession, word: Word, entry: dict[str, Any]) -> None:
    for note in split_notes(entry):
        text = str(note.get("text") or "").strip()
        if not text:
            continue
        exists = await session.scalar(select(Note).where(Note.word_id == word.id, Note.text == text))
        if not exists:
            session.add(
                Note(
                    word_id=word.id,
                    text=text,
                    extra={"legacy_id": note.get("id"), "legacy_links": note.get("links") or []},
                )
            )


async def import_progress(
    session: AsyncSession,
    user: User,
    word: Word,
    entry: dict[str, Any],
    progress_cache: dict[tuple[int, int], UserWordProgress],
) -> None:
    status = entry.get("status") or {}
    cache_key = (user.id, word.id)
    progress = progress_cache.get(cache_key)
    if not progress:
        progress = await session.scalar(
            select(UserWordProgress).where(UserWordProgress.user_id == user.id, UserWordProgress.word_id == word.id)
        )
    if not progress:
        progress = UserWordProgress(user_id=user.id, word_id=word.id)
        session.add(progress)
    progress_cache[cache_key] = progress
    progress.memorized_past = bool(status.get("memorized_past", False))
    progress.memorized_today = bool(status.get("memorized_today", False))
    progress.review_count = max(progress.review_count or 0, int(status.get("review_count") or 0))
    last_reviewed_at = parse_datetime(status.get("last_reviewed"))
    if last_reviewed_at and (not progress.last_reviewed_at or last_reviewed_at > progress.last_reviewed_at):
        progress.last_reviewed_at = last_reviewed_at
    progress.state = 2 if progress.review_count else 0
    progress.status = "review" if progress.state == 2 else "new"


def unit_sort_key(path: Path) -> tuple[int, int, str]:
    match = re.search(r"Unit_(\d+)_Sub(\d+)", path.stem)
    if not match:
        return (9999, 9999, path.stem)
    return (int(match.group(1)), int(match.group(2)), path.stem)


async def import_legacy_json() -> None:
    await create_all_tables()
    unit_files = sorted(DATA_DIR.glob("Unit_*_Sub*.json"), key=unit_sort_key)
    async with AsyncSessionLocal() as session:
        user = await get_or_create_default_user(session)
        imported_words = 0
        progress_cache: dict[tuple[int, int], UserWordProgress] = {}
        cluster_link_cache: dict[tuple[int, int], WordCluster] = {}
        for unit_index, path in enumerate(unit_files, start=1):
            cluster = await get_or_create_cluster(session, path.stem, unit_index)
            entries = json.loads(path.read_text(encoding="utf-8"))
            for position, entry in enumerate(entries, start=1):
                entry.setdefault("unit", path.stem)
                word = await get_or_create_word(session, entry)
                await link_word_cluster(session, word, cluster, position, cluster_link_cache)
                await import_examples(session, word, entry)
                await import_notes(session, word, entry)
                await import_progress(session, user, word, entry, progress_cache)
                imported_words += 1
        await session.commit()
    print(f"Imported {imported_words} legacy word rows from {len(unit_files)} unit files.")


if __name__ == "__main__":
    asyncio.run(import_legacy_json())
