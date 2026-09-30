"""Health endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text

from api.dependencies import get_database
from db.engine import DatabaseEngine
from schemas.api import HealthResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthResponse)
def health(database: DatabaseEngine = Depends(get_database)) -> HealthResponse:
    database_ok = False
    try:
        with database.session() as session:
            session.execute(text("select 1"))
        database_ok = True
    except Exception:
        database_ok = False
    return HealthResponse(database=database_ok, status="ok" if database_ok else "degraded")
