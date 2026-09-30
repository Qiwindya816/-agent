"""Migrate existing JSON user/session/trip files into the database."""

import argparse
import json
from pathlib import Path

from config.settings import get_settings
from db.engine import DatabaseEngine
from repositories.memory_rag_tool_repository import MemoryRepository
from repositories.session_repository import SessionRepository
from repositories.trip_repository import TripRepository
from repositories.user_repository import UserRepository
from utils.ids import new_request_id


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def migrate(memory_dir: Path, database_url: str | None, *, dry_run: bool = False) -> int:
    engine = DatabaseEngine(database_url)
    engine.create_all()
    migrated = {"users": 0, "sessions": 0, "trips": 0}
    try:
        with engine.session() as session:
            users = UserRepository(session)

            user_dir = memory_dir / "users"
            for path in user_dir.glob("*.json"):
                data = read_json(path)
                user_id = data.get("user_id") or path.stem
                if users.get(user_id) is None:
                    users.create(user_id, data.get("display_name"))
                    migrated["users"] += 1

            session_dir = memory_dir / "sessions"
            for path in session_dir.glob("*.json"):
                data = read_json(path)
                user_id = data["user_id"]
                session_id = data["session_id"]
                if SessionRepository(session).get(user_id, session_id) is None:
                    SessionRepository(session).create(user_id, session_id, title=data.get("last_intent"))
                    migrated["sessions"] += 1
                for index, message in enumerate(data.get("chat_history", [])):
                    SessionRepository(session)
                    from repositories.session_repository import MessageRepository

                    message_id = f"{session_id}_legacy_{index}"
                    if MessageRepository(session).get(user_id, session_id, message_id) is None:
                        MessageRepository(session).add(
                            user_id,
                            session_id,
                            message_id,
                            message.get("role", "user"),
                            message.get("content", ""),
                        )

            trip_dir = memory_dir / "trips"
            for path in trip_dir.glob("*/trip.json"):
                data = read_json(path)
                user_id = data["user_id"]
                session_id = data["session_id"]
                trip_id = data["trip_id"]
                trips = TripRepository(session)
                if trips.get(user_id, session_id, trip_id) is None:
                    trips.create(user_id, session_id, trip_id, destination=data.get("destination"))
                    migrated["trips"] += 1

        if dry_run:
            raise RuntimeError("dry-run rollback")
        print(json.dumps(migrated, ensure_ascii=False))
        return 0
    except Exception:
        # DatabaseEngine.session context performs rollback on exception.
        raise
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate legacy JSON storage to the database")
    parser.add_argument("--memory-dir", default="memory_data")
    parser.add_argument("--url", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return migrate(Path(args.memory_dir), args.url, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
