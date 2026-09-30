"""Tests for context builder and conversation summarizer."""

from schemas.agent_state import AgentState
from schemas.travel_request import TravelRequest
from schemas.user_profile import UserProfile
from services.context_builder import ContextBuilder, ConversationSummarizer


def test_context_builder_prioritizes_current_input_and_constraints() -> None:
    state = AgentState(
        user_id="user_a",
        session_id="session_a",
        travel_request=TravelRequest(destination="成都", travel_days=3),
        user_profile=UserProfile(interests=["历史文化"]),
    )

    context = ContextBuilder(recent_turns=2, max_context_tokens=6000).build(
        state, "帮我规划成都行程", extra_rag="测试知识"
    )

    assert "用户本轮输入：帮我规划成都行程" in context
    assert "destination=成都" in context
    assert "历史文化" in context
    assert context.index("用户本轮输入") < context.index("当前旅行约束")


def test_context_builder_respects_token_budget() -> None:
    state = AgentState(user_id="user_a", session_id="session_a")
    builder = ContextBuilder(max_context_tokens=2)

    context = builder.build(state, "这段输入很长" * 100)

    assert ContextBuilder.estimate_tokens(context) <= 2


def test_conversation_summarizer_preserves_constraints() -> None:
    state = AgentState(
        user_id="user_a",
        session_id="session_a",
        trip_id="trip_a",
        travel_request=TravelRequest(
            destination="成都",
            travel_days=3,
            budget=3000,
            special_requirements=["不要安排夜爬"],
        ),
        output_version=2,
    )
    summarizer = ConversationSummarizer(summary_after_turns=2)

    assert summarizer.should_summarize(state) is False
    from schemas.agent_state import ChatMessage
    state.chat_history = [ChatMessage(role="user", content="a") for _ in range(2)]

    summary = summarizer.summarize(state)
    assert summary["confirmed_constraints"]["destination"] == "成都"
    assert summary["rejected_or_special_requirements"] == ["不要安排夜爬"]
    assert summary["current_itinerary_version"] == 2


class RetrievedChunkStub:
    chunk_text = "参观需要提前预约。"
    source_name = "北京文旅"
    source_url = "https://example.com"
    fetched_at = "2026-09-30"


def test_context_builder_formats_rag_results_with_citations() -> None:
    state = AgentState(user_id="user_a", session_id="session_a")

    context = ContextBuilder().build(state, "规划北京行程", rag_results=[RetrievedChunkStub()])

    assert "检索到的参考知识" in context
    assert "参观需要提前预约。" in context
    assert "北京文旅" in context
    assert "https://example.com" in context
    assert "更新时间：2026-09-30" in context


class RetrievedMemoryStub:
    memory_type = "semantic"
    category = "interests"
    statement = "用户喜欢博物馆"
    confidence = 0.98
    evidence_count = 2


class MemoryDecisionStub:
    memory = RetrievedMemoryStub()
    reason = "semantic 记忆，证据充分"


def test_context_builder_formats_long_term_memory_with_evidence() -> None:
    state = AgentState(user_id="user_a", session_id="session_a")

    context = ContextBuilder().build(state, "规划行程", memory_results=[MemoryDecisionStub()])

    assert "长期记忆：" in context
    assert "用户喜欢博物馆" in context
    assert "类型：semantic" in context
    assert "置信度：0.98" in context
    assert "证据数：2" in context
    assert "选择原因：semantic 记忆，证据充分" in context
