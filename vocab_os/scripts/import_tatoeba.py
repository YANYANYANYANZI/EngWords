"""Import short English-Chinese Tatoeba examples into the examples table.

Run from ``vocab_os/``:

    python scripts/import_tatoeba.py

The script downloads and caches three official Tatoeba per-language exports:

* eng-cmn_links.tsv.bz2
* eng_sentences.tsv.bz2
* cmn_sentences.tsv.bz2

It then keeps English sentences whose length is between 20 and 100 characters,
matches them against learning words with regex word boundaries, and inserts at
most 1-2 examples per word into the SQLAlchemy ``examples`` table.
"""

from __future__ import annotations

import argparse
import asyncio
import bz2
import csv
import re
import sys
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.core.database import AsyncSessionLocal, create_all_tables  # noqa: E402
from backend.orm import Example, Word  # noqa: E402


TATOEBA_BASE_URL = "https://downloads.tatoeba.org/exports/per_language"
DEFAULT_CACHE_DIR = ROOT_DIR / "data" / "tatoeba"
FILES = {
    "links": f"{TATOEBA_BASE_URL}/eng/eng-cmn_links.tsv.bz2",
    "eng_sentences": f"{TATOEBA_BASE_URL}/eng/eng_sentences.tsv.bz2",
    "cmn_sentences": f"{TATOEBA_BASE_URL}/cmn/cmn_sentences.tsv.bz2",
}


@dataclass(frozen=True)
class Candidate:
    word_id: int
    word: str
    text: str
    translation: str
    quality_score: float
    eng_id: int
    cmn_id: int


def download_file(url: str, destination: Path, force: bool = False) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 0 and not force:
        print(f"Using cached {destination.name} ({destination.stat().st_size / 1024 / 1024:.1f} MB)")
        return

    print(f"Downloading {url} -> {destination}")
    request = urllib.request.Request(url, headers={"User-Agent": "VocabOS Tatoeba importer"})
    with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as output:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)


def ensure_exports(cache_dir: Path, force_download: bool = False) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for name, url in FILES.items():
        path = cache_dir / url.rsplit("/", 1)[-1]
        download_file(url, path, force=force_download)
        paths[name] = path
    return paths


def iter_bz2_tsv(path: Path) -> Iterable[list[str]]:
    with bz2.open(path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        yield from reader


def normalize_sentence(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def is_good_english_sentence(text: str, min_len: int, max_len: int) -> bool:
    if not (min_len <= len(text) <= max_len):
        return False
    if not re.search(r"[A-Za-z]", text):
        return False
    if re.search(r"[\[\]{}<>]", text):
        return False
    return True


def sentence_quality(text: str) -> float:
    """Prefer concise, natural complete sentences for TTS-friendly examples."""
    length = len(text)
    words = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", text)
    score = 100.0
    score -= abs(length - 55) * 0.45
    score -= max(0, len(words) - 14) * 2.0
    if text.endswith((".", "?", "!")):
        score += 5.0
    if re.search(r"\b(I|you|he|she|we|they|Tom|Mary)\b", text):
        score += 2.0
    if re.search(r"\d|[:;()]|--", text):
        score -= 8.0
    return round(max(0.0, min(100.0, score)), 2)


async def load_words(session: AsyncSession) -> list[Word]:
    result = await session.execute(select(Word).order_by(Word.id))
    words = []
    for word in result.scalars():
        normalized = (word.normalized or word.word or "").strip().lower()
        # Tatoeba regex matching is intentionally limited to simple English tokens.
        if re.fullmatch(r"[a-z][a-z'-]*", normalized):
            words.append(word)
    return words


def build_word_index(words: list[Word]) -> tuple[dict[str, list[Word]], set[str]]:
    by_initial: dict[str, list[Word]] = defaultdict(list)
    exact_words: set[str] = set()
    for word in words:
        normalized = (word.normalized or word.word).lower()
        by_initial[normalized[0]].append(word)
        exact_words.add(normalized)
    # Prefer longer words first when multiple tokens appear in the same sentence.
    for initial in by_initial:
        by_initial[initial].sort(key=lambda item: len(item.normalized or item.word), reverse=True)
    return by_initial, exact_words


def load_english_sentences(path: Path, min_len: int, max_len: int) -> dict[int, str]:
    sentences: dict[int, str] = {}
    for row in iter_bz2_tsv(path):
        if len(row) < 3:
            continue
        try:
            sentence_id = int(row[0])
        except ValueError:
            continue
        text = normalize_sentence(row[2])
        if is_good_english_sentence(text, min_len, max_len):
            sentences[sentence_id] = text
    print(f"Loaded {len(sentences):,} short English sentences ({min_len}-{max_len} chars).")
    return sentences


def load_chinese_sentences(path: Path) -> dict[int, str]:
    sentences: dict[int, str] = {}
    for row in iter_bz2_tsv(path):
        if len(row) < 3:
            continue
        try:
            sentence_id = int(row[0])
        except ValueError:
            continue
        text = normalize_sentence(row[2])
        if text:
            sentences[sentence_id] = text
    print(f"Loaded {len(sentences):,} Chinese sentences.")
    return sentences


def match_candidates(
    links_path: Path,
    english_sentences: dict[int, str],
    chinese_sentences: dict[int, str],
    words: list[Word],
    per_word_limit: int,
) -> dict[int, list[Candidate]]:
    by_initial, exact_words = build_word_index(words)
    candidates: dict[int, list[Candidate]] = defaultdict(list)
    seen_texts: dict[int, set[str]] = defaultdict(set)
    scanned_pairs = 0
    usable_pairs = 0

    for row in iter_bz2_tsv(links_path):
        if len(row) < 2:
            continue
        try:
            eng_id = int(row[0])
            cmn_id = int(row[1])
        except ValueError:
            continue
        text = english_sentences.get(eng_id)
        translation = chinese_sentences.get(cmn_id)
        scanned_pairs += 1
        if not text or not translation:
            continue
        usable_pairs += 1

        tokens = {token.lower() for token in re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", text)}
        possible_words = [token for token in tokens if token in exact_words]

        # Also support hyphenated/apostrophe vocabulary items via explicit word-boundary regex.
        initials = {token[0] for token in tokens if token}
        for initial in initials:
            for word in by_initial.get(initial, []):
                normalized = (word.normalized or word.word).lower()
                if normalized in tokens or normalized in possible_words:
                    if text in seen_texts[word.id] or len(candidates[word.id]) >= per_word_limit * 4:
                        continue
                    pattern = re.compile(rf"\b{re.escape(normalized)}\b", re.IGNORECASE)
                    if not pattern.search(text):
                        continue
                    seen_texts[word.id].add(text)
                    candidates[word.id].append(
                        Candidate(
                            word_id=word.id,
                            word=word.word,
                            text=text,
                            translation=translation,
                            quality_score=sentence_quality(text),
                            eng_id=eng_id,
                            cmn_id=cmn_id,
                        )
                    )

    for word_id, items in list(candidates.items()):
        items.sort(key=lambda item: (-item.quality_score, len(item.text), item.eng_id))
        candidates[word_id] = items[:per_word_limit]

    print(f"Scanned {scanned_pairs:,} eng-cmn links; {usable_pairs:,} had short English + Chinese text.")
    return candidates


async def clear_existing_tatoeba(session: AsyncSession) -> int:
    result = await session.execute(delete(Example).where(Example.source_type == "tatoeba"))
    await session.flush()
    return int(result.rowcount or 0)


async def insert_candidates(session: AsyncSession, candidates: dict[int, list[Candidate]]) -> int:
    inserted = 0
    for items in candidates.values():
        for item in items:
            exists = await session.scalar(
                select(Example.id).where(
                    Example.word_id == item.word_id,
                    Example.text == item.text,
                    Example.source_type == "tatoeba",
                )
            )
            if exists:
                continue
            session.add(
                Example(
                    word_id=item.word_id,
                    text=item.text,
                    translation=item.translation,
                    source_type="tatoeba",
                    source_name="Tatoeba eng-cmn",
                    quality_score=item.quality_score,
                    extra={
                        "license": "CC BY 2.0 FR / Tatoeba export",
                        "eng_sentence_id": item.eng_id,
                        "cmn_sentence_id": item.cmn_id,
                        "matched_word": item.word,
                    },
                )
            )
            inserted += 1
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise
    return inserted


async def import_tatoeba(args: argparse.Namespace) -> None:
    await create_all_tables()
    paths = ensure_exports(args.cache_dir, force_download=args.force_download)

    async with AsyncSessionLocal() as session:
        words = await load_words(session)
        total_words = await session.scalar(select(func.count(Word.id))) or 0
        if not words:
            raise RuntimeError("No learning words found in words table.")

        print(f"Loaded {len(words):,}/{total_words:,} regex-matchable learning words.")
        english = load_english_sentences(paths["eng_sentences"], args.min_len, args.max_len)
        chinese = load_chinese_sentences(paths["cmn_sentences"])
        candidates = match_candidates(paths["links"], english, chinese, words, args.per_word_limit)

        if args.replace:
            removed = await clear_existing_tatoeba(session)
            print(f"Removed {removed:,} existing Tatoeba examples.")

        inserted = await insert_candidates(session, candidates)
        matched_words = len(candidates)
        examples_found = sum(len(items) for items in candidates.values())
        success_rate = matched_words / len(words) * 100

        print("\nTatoeba import summary")
        print("----------------------")
        print(f"Total words in DB:          {total_words:,}")
        print(f"Regex-matchable words:      {len(words):,}")
        print(f"Words with examples:        {matched_words:,} ({success_rate:.2f}%)")
        print(f"Candidate examples chosen:  {examples_found:,}")
        print(f"New examples inserted:      {inserted:,}")
        print(f"Per-word limit:             {args.per_word_limit}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import Tatoeba English-Chinese examples into VocabOS.")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--min-len", type=int, default=20)
    parser.add_argument("--max-len", type=int, default=100)
    parser.add_argument("--per-word-limit", type=int, default=2)
    parser.add_argument("--replace", action="store_true", help="Delete existing source_type=tatoeba examples before inserting.")
    parser.add_argument("--force-download", action="store_true", help="Re-download cached Tatoeba exports.")
    args = parser.parse_args()
    if args.min_len < 1 or args.max_len < args.min_len:
        parser.error("Invalid length range.")
    if not 1 <= args.per_word_limit <= 5:
        parser.error("--per-word-limit must be between 1 and 5.")
    return args


if __name__ == "__main__":
    asyncio.run(import_tatoeba(parse_args()))