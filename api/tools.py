"""Tool descriptor, health, and invocation endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.dependencies import get_current_user, get_database
from db.engine import DatabaseEngine
from schemas.api import UserContext
from services.tool_providers import build_provider_registry
from tools.gateway_tool import GatewayTool
from tools.registry import build_default_registry

router = APIRouter(prefix="/tools", tags=["tools"])


class InvokeRequest(BaseModel):
    arguments: dict[str, Any] = {}
    session_id: str | None = None
    trip_id: str | None = None


@router.get("")
def list_tools(_: UserContext = Depends(get_current_user)) -> list[dict[str, Any]]:
    return build_default_registry().descriptors()


@router.get("/health")
def provider_health(_: UserContext = Depends(get_current_user)) -> dict[str, Any]:
    return build_provider_registry().health_snapshot()


@router.post("/{tool_name}/invoke")
def invoke_tool(
    tool_name: str,
    request: InvokeRequest,
    user: UserContext = Depends(get_current_user),
    _: DatabaseEngine = Depends(get_database),
) -> dict[str, Any]:
    registry = build_default_registry()
    tool = registry.get(tool_name)
    if not isinstance(tool, GatewayTool):
        raise HTTPException(status_code=404, detail="Gateway tool not found")
    result = tool.run(
        {
            "mcp_arguments": request.arguments,
            "user_id": user.user_id,
            "session_id": request.session_id,
            "trip_id": request.trip_id,
        }
    )
    return result.model_dump(mode="json", exclude_none=True)
