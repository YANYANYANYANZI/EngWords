"""Generate AI fallback examples for words missing curated examples.

Run from the project root:

    DEEPSEEK_API_KEY=sk-... python scripts/fill_ai_examples.py

The script finds words that do not yet have ``tatoeba``, ``ai`` or ``pinned``
examples, asks DeepSeek for one concise Nahida-style English sentence, and
stores it in the ``examples`` table with ``source_type='ai'``.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT_DIR / "db" / "vocabos.sqlite3"
DEFAULT_MAX_WORKERS = 10
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_BASE_URL = "https://api.deepseek.com"

dotenv_path = ROOT_DIR / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)

SYSTEM_PROMPT = """你扮演《原神》中的纳西妲（智慧之神）。请为提供的英文单词造一句极简的英文例句。
要求：
1. 长度绝对控制在 50 个字母以内。
2. 语气带有一丝温柔、哲理或自然的意象（如：梦境、树叶、知识、流星等），但不可生硬中二。
3. 英文例句必须自然包含目标单词或其常见形态。
4. 必须返回合法的 JSON 格式，包含 "text" (英文) 和 "chinese" (中文翻译)。
例如：{"text": "Even knowledge needs a little sunshine.", "chinese": "即使是知识，也需要一点阳光。"}"""


@dataclass(frozen=True)
class WordRecord:
    id: int
    word: str


@dataclass(frozen=True)
class GeneratedExample:
    word_id: int
    word: str
    text: str | None
    translation: str
    error: str | None = None


_db_write_lock = threading.Lock()


def get_missing_words(db_path: Path, limit: int | None = None) -> list[WordRecord]:
    """Find words without curated, AI, or pinned examples."""
    sql = """
        SELECT id, word
        FROM words
        WHERE id NOT IN (
            SELECT word_id
            FROM examples
            WHERE source_type IN ('tatoeba', 'ai', 'pinned')
        )
        ORDER BY id
    """
    if limit:
        sql += " LIMIT ?"

    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(sql, (limit,) if limit else ())
        return [WordRecord(id=row[0], word=row[1]) for row in cursor.fetchall()]


def parse_json_response(content: str) -> tuple[str, str]:
    """Parse DeepSeek JSON response and normalize fields."""
    data = json.loads(content)
    text = str(data.get("text", "")).strip()
    translation = str(data.get("chinese", "")).strip()
    if not text:
        raise ValueError("DeepSeek response did not contain a non-empty text field")
    if len(text) > 80:
        # The prompt asks for 50 letters, but keep a small safety margin for
        # punctuation/spaces instead of discarding otherwise useful sentences.
        raise ValueError(f"Generated sentence is too long: {len(text)} chars")
    return text, translation


def generate_example(
    client: OpenAI,
    word_record: WordRecord,
    model: str,
    temperature: float,
    retries: int,
) -> GeneratedExample:
    """Call DeepSeek with basic retry handling for transient failures."""
    last_error = ""
    for attempt in range(1, retries + 2):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"请为单词造句：{word_record.word}"},
                ],
                response_format={"type": "json_object"},
                temperature=temperature,
            )
            content = response.choices[0].message.content or "{}"
            text, translation = parse_json_response(content)
            return GeneratedExample(word_record.id, word_record.word, text, translation)
        except Exception as exc:  # noqa: BLE001 - keep batch jobs resilient.
            last_error = str(exc)
            if attempt <= retries:
                time.sleep(min(2 ** attempt, 8))
    return GeneratedExample(word_record.id, word_record.word, None, "", last_error)


def save_to_db(db_path: Path, example: GeneratedExample, model: str) -> bool:
    """Insert generated example. Returns True if a new row was written."""
    if not example.text:
        return False

    # sqlite3 connections are not shared across threads, but writes are still
    # serialized to avoid SQLITE_BUSY during high-concurrency batch runs.
    with _db_write_lock:
        with sqlite3.connect(db_path, timeout=30) as conn:
            conn.execute("PRAGMA busy_timeout = 30000")
            now = datetime.utcnow().isoformat(sep=" ", timespec="seconds")
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO examples (
                    word_id,
                    text,
                    translation,
                    source_type,
                    source_name,
                    quality_score,
                    extra,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, 'ai', 'deepseek_nahida', 8, ?, ?, ?)
                """,
                (
                    example.word_id,
                    example.text,
                    example.translation,
                    json.dumps({"model": model, "style": "nahida"}, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            conn.commit()
            return cursor.rowcount > 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fill missing VocabOS examples with DeepSeek-generated AI examples.")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--api-key", default=os.getenv("DEEPSEEK_API_KEY", ""))
    parser.add_argument("--base-url", default=os.getenv("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--model", default=os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL))
    parser.add_argument("--max-workers", type=int, default=int(os.getenv("DEEPSEEK_MAX_WORKERS", DEFAULT_MAX_WORKERS)))
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--limit", type=int, help="Only process the first N missing words, useful for smoke tests.")
    args = parser.parse_args()

    if not args.api_key:
        parser.error("DeepSeek API key is required. Set DEEPSEEK_API_KEY or pass --api-key.")
    if args.max_workers < 1:
        parser.error("--max-workers must be >= 1")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be >= 1")
    return args


def main() -> None:
    args = parse_args()
    db_path = args.db_path.resolve()
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    words = get_missing_words(db_path, args.limit)
    print(f"🎯 查找到 {len(words)} 个需要 AI 补全的单词。开始召唤纳西妲...")
    if not words:
        return

    client = OpenAI(api_key=args.api_key, base_url=args.base_url)
    success_count = 0
    failed_count = 0

    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = {
            executor.submit(generate_example, client, word, args.model, args.temperature, args.retries): word
            for word in words
        }
        for future in as_completed(futures):
            result = future.result()
            if result.text and save_to_db(db_path, result, args.model):
                success_count += 1
                print(f"[成功] {result.word} -> {result.text} ({result.translation})")
            elif result.text:
                print(f"[跳过] {result.word} : 例句已存在或被唯一约束忽略")
            else:
                failed_count += 1
                print(f"[失败] {result.word} : {result.error}", file=sys.stderr)

    print(f"✅ 任务完成！成功生成 {success_count} 条，失败 {failed_count} 条。")


if __name__ == "__main__":
    main()
