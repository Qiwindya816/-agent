"""Initialize and manage the TravelMind database.

Development default is SQLite. Production should use PostgreSQL with pgvector.
"""

import argparse

from db.engine import reset_database_engine


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage TravelMind database tables")
    parser.add_argument("--url", help="Database URL; defaults to DATABASE_URL")
    parser.add_argument("--drop", action="store_true", help="Drop all tables before creating them")
    args = parser.parse_args()

    engine = reset_database_engine(args.url)
    if args.drop:
        from db import Base

        Base.metadata.drop_all(engine.engine)
    engine.create_all()
    print(f"Database initialized: {engine.url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
