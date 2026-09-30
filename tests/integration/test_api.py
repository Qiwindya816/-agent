"""API integration tests using an isolated SQLite database."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from db import Base
from db.engine import DatabaseEngine, reset_database_engine
from repositories.user_repository import UserRepository
from repositories.session_repository import SessionRepository


@pytest.fixture()
def database(tmp_path: Path):
    engine = reset_database_engine(f"sqlite+pysqlite:///{tmp_path / 'api.db'}")
    Base.metadata.create_all(engine.engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def client(database: DatabaseEngine):
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def test_health(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["database"] is True


def test_session_isolation(client: TestClient, database: DatabaseEngine) -> None:
    headers_a = {"X-User-ID": "user_a"}
    headers_b = {"X-User-ID": "user_b"}

    created = client.post("/api/v1/sessions", json={"title": "A session"}, headers=headers_a)
    assert created.status_code == 201
    session_id = created.json()["session_id"]

    assert client.get("/api/v1/sessions", headers=headers_a).json()[0]["session_id"] == session_id
    assert client.get("/api/v1/sessions", headers=headers_b).json() == []
    assert client.get(f"/api/v1/sessions/{session_id}", headers=headers_b).status_code == 404
    assert client.delete(f"/api/v1/sessions/{session_id}", headers=headers_b).status_code == 404


def test_memory_endpoints_and_isolation(client: TestClient, database: DatabaseEngine) -> None:
    headers = {"X-User-ID": "api_user"}
    response = client.post("/api/v1/memory/settings", json={"personalization_enabled": False}, headers=headers)

    assert response.status_code == 200
    assert response.json()["personalization_enabled"] is False

    client.post("/api/v1/memory/settings", json={"personalization_enabled": True}, headers=headers)
    assert client.get("/api/v1/memory", headers=headers).json() == []
    assert client.get("/api/v1/memory", headers={"X-User-ID": "other_user"}).json() == []


def test_rag_search_requires_query(client: TestClient) -> None:
    # SQLite tests cannot execute pgvector cosine SQL; verify validation instead.
    response = client.post("/api/v1/rag/search", json={"query": ""})

    assert response.status_code == 422


def test_tools_list_and_health(client: TestClient) -> None:
    tools = client.get("/api/v1/tools")
    health = client.get("/api/v1/tools/health")

    assert tools.status_code == 200
    assert health.status_code == 200
    assert isinstance(tools.json(), list)
    assert isinstance(health.json(), dict)


def test_validation_error_format(client: TestClient) -> None:
    response = client.post("/api/v1/rag/search", json={"query": ""})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_rag_source_and_document_flow(client: TestClient, database: DatabaseEngine) -> None:
    headers = {"X-User-ID": "rag_api_user"}
    source = client.post(
        "/api/v1/rag/sources",
        json={"source_type": "official", "name": "API test source"},
        headers=headers,
    )
    assert source.status_code == 201
    source_id = source.json()["source_id"]

    document = client.post(
        f"/api/v1/rag/sources/{source_id}/documents",
        json={
            "title": "API test document",
            "content": "# API Test\n\nThis is a test fact.",
            "document_type": "fact",
            "metadata": {"city": "Test City"},
            "embed": False,
        },
        headers=headers,
    )
    assert document.status_code == 201
    assert document.json()["chunk_count"] == 1
    document_id = document.json()["document_id"]

    deleted = client.delete(f"/api/v1/rag/documents/{document_id}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
