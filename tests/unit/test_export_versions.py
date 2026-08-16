from types import SimpleNamespace

from schemas.agent_state import AgentState
from services.export_service import ExportService


def test_export_keeps_request_and_snapshot_versions(tmp_path) -> None:
    service = ExportService()
    service.settings = SimpleNamespace(output_dir=tmp_path)
    state = AgentState(user_id="alice_01", session_id="session_abc123", request_id="req_first")

    first_request = service.save_request_response(state, "第一轮回答")
    first_version, latest = service.save_versioned_snapshot(state)
    state.request_id = "req_second"
    second_request = service.save_request_response(state, "第二轮回答")
    second_version, _ = service.save_versioned_snapshot(state)

    assert first_request.read_text(encoding="utf-8") == "第一轮回答"
    assert second_request.read_text(encoding="utf-8") == "第二轮回答"
    assert first_version.name == "v0001.md"
    assert second_version.name == "v0002.md"
    assert first_version.exists() and second_version.exists() and latest.exists()
    assert state.output_version == 2
