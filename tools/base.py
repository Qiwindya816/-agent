from abc import ABC, abstractmethod
from typing import Any

from schemas.tool import ToolResult

# 定义一个抽象基类 BaseTool，作为所有工具的基类。
class BaseTool(ABC):
    name: str
    description: str

    @abstractmethod
    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        """执行工具并返回统一结果；具体逻辑由子类实现。"""
        raise NotImplementedError
