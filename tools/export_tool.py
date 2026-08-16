from typing import Any

from schemas.tool import ToolResult
from services.export_service import ExportService
from tools.base import BaseTool

# 定义一个具体工具 ExportTool，用于导出最终旅行方案。
class ExportTool(BaseTool):
    name = "finalize_plan"
    description = "导出最终旅行方案。"

    def __init__(self, export_service: ExportService | None = None) -> None:
        """初始化最终方案导出工具及其导出服务。"""
        self.export_service = export_service or ExportService()

    # 定义 run 方法，接收工具输入并返回统一的工具结果。
    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        """根据当前状态生成完整旅行方案；版本化保存由工作流统一完成。"""
        state = tool_input.get("state")
        if not state:
            return ToolResult.failure(self.name, "missing_state", "当前没有可导出的旅行方案。")
        content = self.export_service.build_final_markdown(state)
        return ToolResult.ok(self.name, content)
