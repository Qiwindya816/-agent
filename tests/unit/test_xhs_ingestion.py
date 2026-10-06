import pytest

from exceptions.external_api import ExternalAPIError
from services.xhs_ingestion import (
    XhsMcpService,
    _sanitize_raw_payload,
    is_xhs_note_id,
    parse_engagement_count,
)


class FakeMcpClient:
    def __init__(self, tools=None, responses=None):
        self.tools = tools or []
        self.responses = responses or {}

    def list_tools(self):
        return self.tools

    def call_tool(self, name, arguments):
        return self.responses[name], {"provider": "test"}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, 0),
        (123, 123),
        ("1,234", 1234),
        ("1.2万", 12000),
        ("3w+", 30000),
        ("2.5k", 2500),
        ("0.8亿", 80000000),
    ],
)
def test_parse_engagement_count(value, expected):
    assert parse_engagement_count(value) == expected


def test_mcp_facade_rejects_tools_outside_read_only_allowlist():
    service = XhsMcpService(
        FakeMcpClient(tools=[{"name": "xhs_search"}, {"name": "xhs_publish_video"}])
    )
    with pytest.raises(ExternalAPIError):
        service.list_tools()
    with pytest.raises(ValueError):
        service.call("xhs_publish_video", {})


def test_search_decodes_json_text_and_does_not_return_tokens_elsewhere():
    service = XhsMcpService(
        FakeMcpClient(
            responses={
                "xhs_search": '{"count": 1, "items": [{"id": "note-1", "xsecToken": "temporary"}]}'
            }
        )
    )
    assert service.search("北京", count=1, timeout_ms=1000)[0]["id"] == "note-1"


def test_raw_payload_removes_commenters_and_direct_author_id():
    sanitized = _sanitize_raw_payload(
        {
            "id": "note-1",
            "desc": "正文",
            "user": {"userid": "author-1", "nickname": "昵称"},
            "comments": {"list": [{"user": {"userid": "commenter"}}]},
        }
    )
    assert "comments" not in sanitized
    assert "user" not in sanitized
    assert sanitized["author"]["hash"]
    assert "author-1" not in str(sanitized)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("6a0ef8fa00000000350234fe", True),
        ("4919e92f-d8a5-49eb-aedb-58daead773cb#1791125635157", False),
        ("", False),
        ("not-a-note", False),
    ],
)
def test_xhs_note_id_filter(value, expected):
    assert is_xhs_note_id(value) is expected
