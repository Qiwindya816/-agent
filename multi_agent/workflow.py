"""面向 CLI/API 的 LangGraph 工作流入口。"""

from __future__ import annotations

from typing import Any

from multi_agent.graph import build_travel_graph
from utils.ids import new_request_id, new_session_id, validate_user_id


class MultiAgentTravelWorkflow:
    """用稳定 user/session/thread 标识执行五角色旅行工作流。"""

    def __init__(
        self,
        user_id: str = "default_user",
        session_id: str | None = None,
        *,
        graph: Any | None = None,
    ) -> None:
        self.user_id = validate_user_id(user_id)
        self.session_id = session_id or (
            "default_session" if self.user_id == "default_user" else new_session_id()
        )
        self.graph = graph or build_travel_graph()

    def run_with_state(self, user_input: str) -> dict[str, Any]:
        """运行一轮并返回最终状态，供 API、调试和评测使用。"""

        text = user_input.strip()
        if not text:
            raise ValueError("用户输入不能为空。")
        result = self.graph.invoke(
            {
                "user_id": self.user_id,
                "session_id": self.session_id,
                "request_id": new_request_id(),
                "user_input": text,
                "node_trace": [],
                "errors": [],
            },
            config={"configurable": {"thread_id": self.session_id}},
        )
        return dict(result)

    def run(self, user_input: str) -> str:
        """运行一轮并只返回面向用户的回复。"""

        return str(self.run_with_state(user_input)["response"])
