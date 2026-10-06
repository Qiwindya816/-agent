"""提供 核心领域服务和外部服务适配；本文件负责 `context_builder` 相关实现。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from schemas.agent_state import AgentState
from schemas.travel_request import TravelRequest


@dataclass(frozen=True)
class ContextSection:
    """封装 `ContextSection` 的核心数据与行为。"""

    name: str
    content: str
    priority: int


class ContextBuilder:
    """集中实现 `ContextBuilder` 对应的确定性业务逻辑。"""

    def __init__(
        self,
        *,
        recent_turns: int = 8,
        max_context_tokens: int = 6000,
    ) -> None:
        """初始化 ContextBuilder 及其运行依赖。"""
        self.recent_turns = recent_turns
        self.max_context_tokens = max_context_tokens

    def build(self, state: AgentState, user_input: str, **extra: Any) -> str:
        """构建 `build` 对应的数据和流程，返回该步骤的处理结果。"""
        sections = [
            ContextSection("current_input", f"用户本轮输入：{user_input}", 100),
            ContextSection("travel_request", self._format_travel_request(state.travel_request), 90),
            ContextSection(
                "current_itinerary",
                f"当前行程版本：{state.output_version}",
                80,
            ),
            ContextSection("recent_chat", self._format_recent_chat(state.chat_history), 60),
            ContextSection("user_profile", self._format_profile(state.user_profile), 50),
        ]
        memory_results = extra.get("memory_results")
        if memory_results:
            sections.append(ContextSection("long_term_memory", self._format_memory_results(memory_results), 48))

        rag_results = extra.get("rag_results")
        if rag_results:
            sections.append(ContextSection("rag_knowledge", self._format_rag_results(rag_results), 45))

        for name, value in extra.items():
            if name in {"rag_results", "memory_results"}:
                continue
            sections.append(ContextSection(name, str(value), 40))

        selected: list[ContextSection] = []
        used = 0
        for section in sorted(sections, key=lambda item: item.priority, reverse=True):
            tokens = self.estimate_tokens(section.content)
            if used + tokens > self.max_context_tokens:
                continue
            selected.append(section)
            used += tokens

        return "\n\n".join(section.content for section in selected)

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """估算 `estimate_tokens` 对应的数据和流程，返回该步骤的处理结果。"""
        return max(1, (len(text) + 3) // 4)

    @staticmethod
    def _format_travel_request(request: TravelRequest) -> str:
        """将当前旅行约束格式化为可注入模型的文本。"""
        values = request.model_dump(exclude_none=True, exclude_defaults=True)
        if not values:
            return "当前旅行约束：暂无。"
        return "当前旅行约束：" + ", ".join(f"{key}={value}" for key, value in values.items())

    def _format_recent_chat(self, chat_history: list[Any]) -> str:
        """格式化限定轮数内的最近聊天记录。"""
        if not chat_history:
            return "最近对话：暂无。"
        messages = chat_history[-self.recent_turns :]
        return "最近对话：" + "; ".join(f"{item.role}:{item.content}" for item in messages)

    @staticmethod
    def _format_rag_results(rag_results: Any) -> str:
        """处理 `_format_rag_results` 对应的数据和流程，返回该步骤的处理结果。"""
        lines = ["检索到的参考知识："]
        for item in rag_results:
            source_name = getattr(item, "source_name", None) or "未知来源"
            source_url = getattr(item, "source_url", None)
            published_at = getattr(item, "published_at", None)
            fetched_at = getattr(item, "fetched_at", None)
            authorization = getattr(item, "source_authorization_status", None)
            chunk_text = getattr(item, "chunk_text", str(item))
            citation = source_name
            if source_url:
                citation += f"（{source_url}）"
            if published_at:
                citation += f"，发布时间：{published_at}"
            if fetched_at:
                citation += f"，更新时间：{fetched_at}"
            if authorization:
                citation += f"，授权状态：{authorization}"
            lines.append(f"- {chunk_text}\n  来源：{citation}")
        return "\n".join(lines)

    @staticmethod
    def _format_memory_results(memory_results: Any) -> str:
        """处理 `_format_memory_results` 对应的数据和流程，返回该步骤的处理结果。"""
        lines = ["长期记忆："]
        for item in memory_results:
            memory = getattr(item, "memory", item)
            statement = getattr(memory, "statement", str(item))
            memory_type = getattr(memory, "memory_type", "memory")
            confidence = getattr(memory, "confidence", 0.0)
            evidence_count = getattr(memory, "evidence_count", 0)
            reason = getattr(item, "reason", "")
            lines.append(f"- {statement}\n  类型：{memory_type}，置信度：{confidence:.2f}，证据数：{evidence_count}")
            if reason:
                lines.append(f"  选择原因：{reason}")
        return "\n".join(lines)

    @staticmethod
    def _format_profile(profile: Any) -> str:
        """格式化用户画像，供后续流程使用。"""
        values = profile.model_dump(exclude_none=True, exclude_defaults=True)
        if not values:
            return "长期偏好：暂无。"
        return "长期偏好：" + ", ".join(f"{key}={value}" for key, value in values.items())


class ConversationSummarizer:
    """封装 `ConversationSummarizer` 的核心数据与行为。"""

    def __init__(self, *, summary_after_turns: int = 12, summary_max_tokens: int = 800) -> None:
        """初始化 ConversationSummarizer 及其运行依赖。"""
        self.summary_after_turns = summary_after_turns
        self.summary_max_tokens = summary_max_tokens

    def should_summarize(self, state: AgentState) -> bool:
        """判断当前状态是否满足summarize条件。"""
        return len(state.chat_history) >= self.summary_after_turns

    def summarize(self, state: AgentState) -> dict[str, Any]:
        """汇总 `summarize` 对应的数据和流程，返回该步骤的处理结果。"""
        request = state.travel_request.model_dump(exclude_none=True, exclude_defaults=True)
        rejected = state.travel_request.special_requirements
        summary = {
            "user_id": state.user_id,
            "session_id": state.session_id,
            "trip_id": state.trip_id,
            "confirmed_constraints": request,
            "open_questions": [],
            "rejected_or_special_requirements": rejected,
            "current_itinerary_version": state.output_version,
            "message_count": len(state.chat_history),
        }
        return summary

    def build_summary_text(self, state: AgentState) -> str:
        """构建 `build_summary_text` 对应的数据和流程，返回该步骤的处理结果。"""
        summary = self.summarize(state)
        lines = ["会话摘要："]
        for key, value in summary.items():
            lines.append(f"- {key}: {value}")
        text = "\n".join(lines)
        token_estimate = ContextBuilder.estimate_tokens(text)
        if token_estimate <= self.summary_max_tokens:
            return text
        # 保留摘要开头；这里只是安全回退，不是正常截断路径。
        allowed_chars = self.summary_max_tokens * 4
        return text[:allowed_chars]
