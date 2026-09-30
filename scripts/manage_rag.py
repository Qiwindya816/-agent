"""Manage RAG sources, ingestion, search, embeddings, and deletion."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from config.settings import get_settings
from db.engine import DatabaseEngine
from repositories.rag_repository import RagRepository
from services.embedding_service import EmbeddingService
from services.rag_ingestion import RagIngestionService
from services.rag_retrieval import RagRetrievalService


def default_database() -> DatabaseEngine:
    return DatabaseEngine(get_settings().database_url)


def create_source(args: argparse.Namespace) -> int:
    service = RagIngestionService(default_database())
    source = service.create_source(
        args.source_type,
        args.name,
        url=args.url,
        license_name=args.license,
        authorization_status=args.authorization_status,
        owner_user_id=args.owner_user_id,
    )
    print(source.source_id)
    return 0


def ingest(args: argparse.Namespace) -> int:
    database = default_database()
    service = RagIngestionService(database)
    content = Path(args.file).read_text(encoding=args.encoding).lstrip("\ufeff")
    metadata = json.loads(args.metadata or "{}")
    embeddings = None
    if args.embed:
        chunk_inputs = service.chunker.chunk(content, args.document_type, metadata)
        embeddings = EmbeddingService().embed_texts([item.chunk_text for item in chunk_inputs])
    document, chunks = service.ingest_document(
        args.source_id,
        args.title,
        content,
        document_type=args.document_type,
        owner_user_id=args.owner_user_id,
        metadata=metadata,
        embeddings=embeddings,
    )
    print(
        json.dumps(
            {
                "document_id": document.document_id,
                "chunk_count": len(chunks),
                "raw_file_path": document.raw_file_path,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def search(args: argparse.Namespace) -> int:
    retrieval = RagRetrievalService(default_database(), EmbeddingService() if args.no_embedding is False else None)
    results = retrieval.search(
        args.user_id,
        args.query,
        city=args.city,
        theme=args.theme,
        travel_days=args.travel_days,
        audience=args.audience,
        top_k=args.top_k,
    )
    payload = [
        {
            "rank": item.rank,
            "score": item.score,
            "chunk_text": item.chunk_text,
            "chunk_type": item.chunk_type,
            "source_name": item.source_name,
            "source_url": item.source_url,
            "fetched_at": item.fetched_at,
        }
        for item in results
    ]
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def list_sources(_: argparse.Namespace) -> int:
    with default_database().session() as session:
        repository = RagRepository(session)
        payload = [
            {
                "source_id": item.source_id,
                "source_type": item.source_type,
                "name": item.name,
                "url": item.url,
                "authorization_status": item.authorization_status,
                "owner_user_id": item.owner_user_id,
            }
            for item in repository.list_sources()
        ]
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def delete(args: argparse.Namespace) -> int:
    with default_database().session() as session:
        repository = RagRepository(session)
        deleted = repository.delete_source(args.source_id) if args.source_id else repository.delete_document(args.document_id)
    print(json.dumps({"deleted": deleted}, ensure_ascii=False))
    return 0 if deleted else 2


def backfill_embeddings(_: argparse.Namespace) -> int:
    database = default_database()
    service = EmbeddingService()
    with database.session() as session:
        chunks = RagRepository(session).chunks_missing_embeddings()
        vectors = service.embed_texts([chunk.chunk_text for chunk in chunks])
        for chunk, vector in zip(chunks, vectors):
            chunk.embedding = vector
    print(json.dumps({"backfilled": len(chunks)}, ensure_ascii=False))
    return 0


def main() -> int:
    # Windows terminals may default to GBK; force UTF-8 for reliable JSON output.
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in {"utf-8", "utf8"}:
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Manage TravelMind RAG")
    commands = parser.add_subparsers(dest="command", required=True)

    source = commands.add_parser("create-source")
    source.add_argument("source_type")
    source.add_argument("name")
    source.add_argument("--url")
    source.add_argument("--license")
    source.add_argument("--authorization-status", default="authorized")
    source.add_argument("--owner-user-id")
    source.set_defaults(func=create_source)

    ingest_parser = commands.add_parser("ingest")
    ingest_parser.add_argument("source_id")
    ingest_parser.add_argument("file")
    ingest_parser.add_argument("--title", required=True)
    ingest_parser.add_argument("--document-type", choices=["fact", "guide", "template"], default="fact")
    ingest_parser.add_argument("--metadata", default="{}")
    ingest_parser.add_argument("--owner-user-id")
    ingest_parser.add_argument("--encoding", default="utf-8")
    ingest_parser.add_argument("--embed", action="store_true")
    ingest_parser.set_defaults(func=ingest)

    search_parser = commands.add_parser("search")
    search_parser.add_argument("user_id")
    search_parser.add_argument("query")
    search_parser.add_argument("--city")
    search_parser.add_argument("--theme")
    search_parser.add_argument("--travel-days", type=int)
    search_parser.add_argument("--audience")
    search_parser.add_argument("--top-k", type=int)
    search_parser.add_argument("--no-embedding", action="store_true")
    search_parser.set_defaults(func=search)

    commands.add_parser("list-sources").set_defaults(func=list_sources)

    delete_parser = commands.add_parser("delete")
    delete_parser.add_argument("--source-id")
    delete_parser.add_argument("--document-id")
    delete_parser.set_defaults(func=delete)

    commands.add_parser("backfill-embeddings").set_defaults(func=backfill_embeddings)

    args = parser.parse_args()
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
