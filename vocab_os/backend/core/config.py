from pathlib import Path
import os


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
DB_DIR = BASE_DIR / "db"
DB_DIR.mkdir(parents=True, exist_ok=True)

# Async SQLite is the default local-first database. It can later be replaced by
# async PostgreSQL, for example postgresql+asyncpg://..., without changing ORM models.
DATABASE_URL = os.getenv("VOCABOS_DATABASE_URL", f"sqlite+aiosqlite:///{DB_DIR / 'vocabos.sqlite3'}")
