import asyncio

from backend.core.database import create_all_tables


def main() -> None:
    asyncio.run(create_all_tables())
    print("VocabOS database tables created.")


if __name__ == "__main__":
    main()
