"""Import selected ECDICT rows into the new words table.

Usage from the project root:

    python -m data_pipeline.import_ecdict /path/to/ecdict.csv

By default this only enriches words that already exist in the learning database.
That keeps the learning corpus small while using ECDICT as a dictionary source.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import select

from backend.core.database import AsyncSessionLocal, create_all_tables
from backend.orm import Word


async def import_ecdict(csv_path: Path, chunksize: int = 50_000) -> None:
    await create_all_tables()
    if not csv_path.exists():
        raise FileNotFoundError(csv_path)

    async with AsyncSessionLocal() as session:
        existing_words = {
            row[0]
            for row in (await session.execute(select(Word.normalized))).all()
            if row[0]
        }
        if not existing_words:
            raise RuntimeError("No learning words found. Run import_legacy_json first.")

        updated = 0
        for chunk in pd.read_csv(
            csv_path,
            chunksize=chunksize,
            usecols=lambda col: col in {"word", "phonetic", "translation", "definition", "tag"},
        ):
            chunk["normalized"] = chunk["word"].astype(str).str.strip().str.lower()
            filtered = chunk[chunk["normalized"].isin(existing_words)]
            for _, row in filtered.iterrows():
                word = await session.scalar(select(Word).where(Word.normalized == row["normalized"]))
                if not word:
                    continue
                word.phonetic = row.get("phonetic") if pd.notna(row.get("phonetic")) else word.phonetic
                if pd.notna(row.get("translation")):
                    word.translation = str(row.get("translation"))
                if pd.notna(row.get("definition")):
                    word.definition = str(row.get("definition"))
                if pd.notna(row.get("tag")):
                    word.tags = str(row.get("tag"))
                word.source = "ecdict"
                updated += 1
            await session.commit()
    print(f"Updated {updated} learning words from ECDICT.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python -m data_pipeline.import_ecdict /path/to/ecdict.csv")
    asyncio.run(import_ecdict(Path(sys.argv[1])))
