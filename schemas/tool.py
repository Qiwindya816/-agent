from typing import Any

from pydantic import BaseModel, Field


class ToolError(BaseModel):
    """定义 工具、错误响应 的结构化数据模型。"""
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)

# 工具执行结果的统一数据结构，包含成功标志、业务数据、错误信息和元信息。
class ToolResult(BaseModel):
    """承载 工具 的结构化结果。"""
    success: bool
    tool_name: str
    data: Any | None = None
    error: ToolError | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def ok(cls, tool_name: str, data: Any, metadata: dict[str, Any] | None = None) -> "ToolResult":
        """构造包含业务数据和可选元信息的成功结果。"""
        return cls(success=True, tool_name=tool_name, data=data, metadata=metadata or {})

    @classmethod
    def failure(
        cls,
        tool_name: str,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> "ToolResult":
        """构造包含标准错误信息的失败结果。"""
        return cls(
            success=False,
            tool_name=tool_name,
            error=ToolError(code=code, message=message, retryable=retryable, details=details or {}),
        )
