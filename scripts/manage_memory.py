"""提供 项目维护和命令行操作；本文件负责 `manage_memory` 相关实现。"""

import argparse
import json
import sys
from typing import Any

from config.settings import get_settings
from db.engine import DatabaseEngine
from repositories.memory_repository import MemoryRepository
from repositories.user_repository import UserRepository
from services.embedding_service import EmbeddingService
from services.memory_conflict_resolver import MemoryConflictResolver
from services.memory_retrieval import MemoryRetrievalService


def default_database() -> DatabaseEngine:
    """创建使用当前项目配置的数据库访问对象。"""
    return DatabaseEngine(get_settings().database_url)


def list_memories(args: argparse.Namespace) -> int:
    """列出记忆列表并返回符合当前作用域的结果。"""
    with default_database().session() as session:
        repository = MemoryRepository(session)
        items = repository.list_items(
            args.user_id,
            memory_type=args.memory_type,
            scope=args.scope,
            status=args.status,
        )
        payload = [
            {
                "memory_id": item.memory_id,
                "memory_type": item.memory_type,
                "category": item.category,
                "statement": item.statement,
                "scope": item.scope,
                "polarity": item.polarity,
                "importance": item.importance,
                "confidence": item.confidence,
                "evidence_count": item.evidence_count,
                "status": item.status,
                "has_embedding": item.embedding is not None,
                "last_confirmed_at": str(item.last_confirmed_at) if item.last_confirmed_at else None,
            }
            for item in items
        ]
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def search_memories(args: argparse.Namespace) -> int:
    """检索记忆列表并返回符合当前作用域的结果。"""
    service = MemoryRetrievalService(default_database(), EmbeddingService() if not args.no_embedding else None)
    results = service.retrieve(args.user_id, args.query, scope=args.scope)
    decisions = MemoryConflictResolver().resolve(results, scope=args.scope)
    payload = [
        {
            "rank": index,
            "priority": item.priority,
            "reason": item.reason,
            "memory_type": item.memory.memory_type,
            "statement": item.memory.statement,
            "confidence": item.memory.confidence,
            "evidence_count": item.memory.evidence_count,
            "scope": item.memory.scope,
        }
        for index, item in enumerate(decisions, start=1)
    ]
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def update_memory(args: argparse.Namespace) -> int:
    """更新记忆，并保持相关状态或持久化数据一致。"""
    with default_database().session() as session:
        item = MemoryRepository(session).update_statement(args.user_id, args.memory_id, args.statement)
    print(json.dumps({"updated": item is not None}, ensure_ascii=False))
    return 0 if item is not None else 2


def delete_memory(args: argparse.Namespace) -> int:
    """删除记忆，并保持相关状态或持久化数据一致。"""
    with default_database().session() as session:
        deleted = MemoryRepository(session).delete_item(args.user_id, args.memory_id)
    print(json.dumps({"deleted": deleted}, ensure_ascii=False))
    return 0 if deleted else 2


def list_evidence(args: argparse.Namespace) -> int:
    """列出证据并返回符合当前作用域的结果。"""
    with default_database().session() as session:
        evidence = MemoryRepository(session).list_evidence(args.user_id, args.memory_id)
        payload = [
            {
                "evidence_id": item.evidence_id,
                "memory_id": item.memory_id,
                "session_id": item.session_id,
                "message_id": item.message_id,
                "trip_id": item.trip_id,
                "evidence_text": item.evidence_text,
                "evidence_type": item.evidence_type,
                "confidence": item.confidence,
                "observed_at": str(item.observed_at) if item.observed_at else None,
            }
            for item in evidence
        ]
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def clear_memories(args: argparse.Namespace) -> int:
    """清空记忆列表，并保持相关状态或持久化数据一致。"""
    with default_database().session() as session:
        deleted = MemoryRepository(session).clear_items(args.user_id)
    print(json.dumps({"deleted": deleted}, ensure_ascii=False))
    return 0


def export_memories(args: argparse.Namespace) -> int:
    """导出当前用户的长期记忆及其证据记录。"""
    with default_database().session() as session:
        payload = MemoryRepository(session).export_items(args.user_id)
    print(json.dumps({"user_id": args.user_id, "memories": payload}, ensure_ascii=False, indent=2))
    return 0


def update_settings(args: argparse.Namespace) -> int:
    """更新设置，并保持相关状态或持久化数据一致。"""
    with default_database().session() as session:
        repository = UserRepository(session)
        if repository.get(args.user_id) is None:
            repository.create(args.user_id)
        user = repository.update_settings(
            args.user_id,
            personalization_enabled=None if args.personalization is None else args.personalization,
            long_term_memory_enabled=None if args.long_term_memory is None else args.long_term_memory,
        )
    print(
        json.dumps(
            {
                "user_id": user.user_id,
                "personalization_enabled": user.personalization_enabled,
                "long_term_memory_enabled": user.long_term_memory_enabled,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def main() -> int:
    """解析命令行参数并执行 manage_memory 的主流程。"""
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in {"utf-8", "utf8"}:
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Manage TravelMind long-term memory")
    commands = parser.add_subparsers(dest="command", required=True)

    list_parser = commands.add_parser("list")
    list_parser.add_argument("user_id")
    list_parser.add_argument("--memory-type", choices=["semantic", "episodic", "procedural", "explicit"])
    list_parser.add_argument("--scope")
    list_parser.add_argument("--status", default="active")
    list_parser.set_defaults(func=list_memories)

    search_parser = commands.add_parser("search")
    search_parser.add_argument("user_id")
    search_parser.add_argument("query")
    search_parser.add_argument("--scope")
    search_parser.add_argument("--no-embedding", action="store_true")
    search_parser.set_defaults(func=search_memories)

    update_parser = commands.add_parser("update")
    update_parser.add_argument("user_id")
    update_parser.add_argument("memory_id")
    update_parser.add_argument("statement")
    update_parser.set_defaults(func=update_memory)

    delete_parser = commands.add_parser("delete")
    delete_parser.add_argument("user_id")
    delete_parser.add_argument("memory_id")
    delete_parser.set_defaults(func=delete_memory)

    evidence_parser = commands.add_parser("evidence")
    evidence_parser.add_argument("user_id")
    evidence_parser.add_argument("memory_id")
    evidence_parser.set_defaults(func=list_evidence)

    clear_parser = commands.add_parser("clear")
    clear_parser.add_argument("user_id")
    clear_parser.set_defaults(func=clear_memories)

    export_parser = commands.add_parser("export")
    export_parser.add_argument("user_id")
    export_parser.set_defaults(func=export_memories)

    settings_parser = commands.add_parser("settings")
    settings_parser.add_argument("user_id")
    settings_parser.add_argument("--personalization", action=argparse.BooleanOptionalAction)
    settings_parser.add_argument("--long-term-memory", action=argparse.BooleanOptionalAction)
    settings_parser.set_defaults(func=update_settings)

    args = parser.parse_args()
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
