"""Short-term context and token budget management for TravelMind."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from schemas.agent_state import AgentState
from schemas.travel_request import TravelRequest


@dataclass(frozen=True)
class ContextSection:
    """A prioritized prompt section."""

    name: str
    content: str
    priority: int


class ContextBuilder:
    """Build bounded, prioritized context for planner and generator prompts."""

    def __init__(
        self,
        *,
        recent_turns: int = 8,
        max_context_tokens: int = 6000,
    ) -> None:
        self.recent_turns = recent_turns
        self.max_context_tokens = max_context_tokens

    def build(self, state: AgentState, user_input: str, **extra: Any) -> str:
        """Return compact context ordered by decision priority."""
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
        """Cheap deterministic estimate suitable for local budget enforcement."""
        return max(1, (len(text) + 3) // 4)

    @staticmethod
    def _format_travel_request(request: TravelRequest) -> str:
        values = request.model_dump(exclude_none=True, exclude_defaults=True)
        if not values:
            return "当前旅行约束：暂无。"
        return "当前旅行约束：" + ", ".join(f"{key}={value}" for key, value in values.items())

    def _format_recent_chat(self, chat_history: list[Any]) -> str:
        if not chat_history:
            return "最近对话：暂无。"
        messages = chat_history[-self.recent_turns :]
        return "最近对话：" + "; ".join(f"{item.role}:{item.content}" for item in messages)

    @staticmethod
    def _format_rag_results(rag_results: Any) -> str:
        """Format retrieved chunks with source and freshness metadata."""
        lines = ["检索到的参考知识："]
        for item in rag_results:
            source_name = getattr(item, "source_name", None) or "未知来源"
            source_url = getattr(item, "source_url", None)
            fetched_at = getattr(item, "fetched_at", None)
            chunk_text = getattr(item, "chunk_text", str(item))
            citation = source_name
            if source_url:
                citation += f"（{source_url}）"
            if fetched_at:
                citation += f"，更新时间：{fetched_at}"
            lines.append(f"- {chunk_text}\n  来源：{citation}")
        return "\n".join(lines)

    @staticmethod
    def _format_memory_results(memory_results: Any) -> str:
        """Format long-term memories with type, confidence, and evidence count."""
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
        values = profile.model_dump(exclude_none=True, exclude_defaults=True)
        if not values:
            return "长期偏好：暂无。"
        return "长期偏好：" + ", ".join(f"{key}={value}" for key, value in values.items())


class ConversationSummarizer:
    """Compress long chat history while retaining hard travel constraints."""

    def __init__(self, *, summary_after_turns: int = 12, summary_max_tokens: int = 800) -> None:
        self.summary_after_turns = summary_after_turns
        self.summary_max_tokens = summary_max_tokens

    def should_summarize(self, state: AgentState) -> bool:
        return len(state.chat_history) >= self.summary_after_turns

    def summarize(self, state: AgentState) -> dict[str, Any]:
        """Return a structured summary without calling an LLM.

        The first version deliberately preserves deterministic fields. LLM summary
        generation can be layered later without changing the data contract.
        """
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
        """Build a bounded summary text for prompt injection."""
        summary = self.summarize(state)
        lines = ["会话摘要："]
        for key, value in summary.items():
            lines.append(f"- {key}: {value}")
        text = "\n".join(lines)
        token_estimate = ContextBuilder.estimate_tokens(text)
        if token_estimate <= self.summary_max_tokens:
            return text
        # Preserve the head; this is a safety fallback rather than normal behavior.
        allowed_chars = self.summary_max_tokens * 4
        return text[:allowed_chars]
