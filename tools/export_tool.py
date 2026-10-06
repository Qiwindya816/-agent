from typing import Any

from schemas.tool import ToolResult
from services.export_service import ExportService
from tools.base import BaseTool

# 定义一个具体工具 ExportTool，用于导出最终旅行方案。
class ExportTool(BaseTool):
    """实现 export 能力的统一工具接口。"""
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
        # 完整状态只写入后台导出快照；聊天窗口仅返回用户可读的精简确认。
        version_path, latest_path = self.export_service.save_versioned_snapshot(state)
        content = self.export_service.build_user_summary(state)
        return ToolResult.ok(
            self.name,
            content,
            metadata={"version_path": str(version_path), "latest_path": str(latest_path)},
        )
