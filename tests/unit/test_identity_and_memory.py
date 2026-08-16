from types import SimpleNamespace

import pytest

import memory.memory_manager as memory_manager
from utils.ids import validate_user_id


def test_user_id_is_validated() -> None:
    assert validate_user_id("alice_01") == "alice_01"
    with pytest.raises(ValueError):
        validate_user_id("../alice")


def test_initialize_session_persists_user_and_session(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        memory_manager,
        "get_settings",
        lambda: SimpleNamespace(memory_dir=tmp_path / "memory"),
    )

    state = memory_manager.initialize_session("alice_01")

    assert state.user_id == "alice_01"
    assert (tmp_path / "memory" / "users" / "alice_01.json").exists()
    assert (tmp_path / "memory" / "sessions" / f"{state.session_id}.json").exists()
    loaded = memory_manager.load_agent_state(state.session_id, "alice_01")
    assert loaded.user_id == "alice_01"
    assert loaded.session_id == state.session_id

