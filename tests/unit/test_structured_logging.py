import json
import logging

from utils.logger import JsonFormatter, bind_log_context, redact_secrets, reset_log_context


def test_json_formatter_adds_trace_context_and_redacts_secrets() -> None:
    token = bind_log_context(request_id="req_test", session_id="session_test", trip_id="trip_test")
    try:
        record = logging.LogRecord(
            "travelmind.test",
            logging.INFO,
            __file__,
            1,
            "authorization=Bearer-secret token=abc123",
            (),
            None,
        )
        payload = json.loads(JsonFormatter().format(record))
    finally:
        reset_log_context(token)

    assert payload["request_id"] == "req_test"
    assert payload["session_id"] == "session_test"
    assert payload["trip_id"] == "trip_test"
    assert "Bearer-secret" not in payload["event"]
    assert "abc123" not in payload["event"]


def test_nested_credentials_are_redacted() -> None:
    assert redact_secrets({"api_key": "real", "nested": {"password": "real"}}) == {
        "api_key": "***",
        "nested": {"password": "***"},
    }
