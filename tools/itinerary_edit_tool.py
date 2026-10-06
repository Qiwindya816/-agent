"""提供 工作流可调用工具；本文件负责 `itinerary_edit_tool` 相关实现。"""

from __future__ import annotations

from typing import Any

from schemas.itinerary import Activity, Itinerary
from schemas.tool import ToolResult
from tools.base import BaseTool
from services.itinerary_editor import ItineraryEditor
from validators.itinerary_validator import ItineraryValidator


class ItineraryEditTool(BaseTool):
    """实现 行程、编辑 能力的统一工具接口。"""
    name = "edit_itinerary_activity"
    description = "基于 activity_id 局部修改行程，不重写整份行程。"

    def __init__(self, editor: ItineraryEditor | None = None) -> None:
        """初始化 ItineraryEditTool 及其运行依赖。"""
        self.editor = editor or ItineraryEditor()

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        """执行行程、编辑的完整业务流程并返回执行结果。"""
        state = tool_input.get("state")
        itinerary = getattr(state, "structured_itinerary", None)
        if not isinstance(itinerary, Itinerary):
            return ToolResult.failure(self.name, "missing_current_itinerary", "当前没有可编辑的结构化行程。")

        arguments = tool_input.get("mcp_arguments") or {}
        action = str(arguments.get("action") or "").lower()
        activity_id = arguments.get("activity_id")

        try:
            if action == "remove":
                if not activity_id:
                    return ToolResult.failure(self.name, "missing_activity_id", "缺少 activity_id。")
                edited = self.editor.remove_activity(itinerary, str(activity_id))
                reason = f"删除活动 {activity_id}"
            elif action == "update":
                if not activity_id:
                    return ToolResult.failure(self.name, "missing_activity_id", "缺少 activity_id。")
                edited = self.editor.update_activity(
                    itinerary,
                    str(activity_id),
                    start_time=arguments.get("start_time"),
                    end_time=arguments.get("end_time"),
                    name=arguments.get("name"),
                    estimated_cost=arguments.get("estimated_cost"),
                    notes=arguments.get("notes"),
                )
                reason = f"更新活动 {activity_id}"
            elif action == "add":
                raw = arguments.get("activity")
                if not isinstance(raw, dict):
                    return ToolResult.failure(self.name, "missing_activity", "缺少 activity 对象。")
                day_number = int(arguments.get("day", 1))
                activity = Activity.model_validate(raw)
                edited = self.editor.add_activity(itinerary, day_number, activity)
                reason = f"在第 {day_number} 天添加活动 {activity.name}"
            elif action == "reorder":
                ordered_ids = arguments.get("ordered_activity_ids")
                if not isinstance(ordered_ids, list) or not all(isinstance(value, str) for value in ordered_ids):
                    return ToolResult.failure(self.name, "invalid_ordered_activity_ids", "ordered_activity_ids 必须为字符串数组。")
                day_number = int(arguments.get("day", 1))
                edited = self.editor.reorder_activities(itinerary, day_number, ordered_ids)
                reason = f"重排第 {day_number} 天活动"
            else:
                return ToolResult.failure(self.name, "unsupported_action", "支持的 action 为 remove、update、add、reorder。")
        except Exception as exc:
            return ToolResult.failure(self.name, "itinerary_edit_error", "行程局部修改失败。", details={"error": str(exc)})

        validation = ItineraryValidator().validate(edited)
        return ToolResult.ok(
            self.name,
            edited.model_dump(mode="json"),
            {
                "schema": "Itinerary",
                "schema_version": edited.schema_version,
                "change_reason": reason,
                "validation": validation.model_dump(mode="json"),
            },
        )
