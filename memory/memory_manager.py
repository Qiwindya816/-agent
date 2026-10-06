from datetime import datetime
from pathlib import Path
import json
import shutil
import tempfile
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from config.settings import get_settings
from schemas.agent_state import AgentState
from schemas.trip_state import TripState
from schemas.user_profile import UserProfile
from repositories.agent_state_repository import AgentStateRepository
from utils.ids import new_session_id, new_trip_id, validate_user_id


T = TypeVar("T", bound=BaseModel)

# 第一阶段存储适配器：数据库是事实来源；在 PostgreSQL/pgvector 完全部署前，
# JSON 仅作为迁移和离线回退方案保留。
_database_state_store: AgentStateRepository | None = None


def _state_store() -> AgentStateRepository:
    """处理 `_state_store` 对应的数据和流程，返回该步骤的处理结果。"""
    global _database_state_store
    if _database_state_store is None:
        _database_state_store = AgentStateRepository()
    return _database_state_store


def use_database_state_store(store: AgentStateRepository | None) -> None:
    """切换使用 `use_database_state_store` 对应的数据和流程，返回该步骤的处理结果。"""
    global _database_state_store
    _database_state_store = store


def _memory_root() -> Path:
    """获取记忆存储根目录，并确保用户、会话和行程目录存在。"""
    root = Path(get_settings().memory_dir)
    (root / "users").mkdir(parents=True, exist_ok=True)
    (root / "sessions").mkdir(parents=True, exist_ok=True)
    (root / "trips").mkdir(parents=True, exist_ok=True)
    return root


def _atomic_write(path: Path, content: str) -> None:
    """先写临时文件再原子替换目标文件，避免产生不完整数据。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=str(path.parent), suffix=".tmp") as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def _load_model(path: Path, model: type[T]) -> T:
    """从 JSON 文件加载 Pydantic 模型，损坏时备份并返回默认模型。"""
    if not path.exists():
        return model()

    try:
        return model(**json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, ValidationError, OSError):
        backup = path.with_suffix(path.suffix + ".corrupt")
        try:
            shutil.copy2(path, backup)
        except OSError:
            pass
        return model()


def _save_model(path: Path, value: BaseModel) -> None:
    """更新时间戳，并将 Pydantic 模型原子保存为 JSON。"""
    if hasattr(value, "updated_at"):
        value.updated_at = datetime.utcnow()
    _atomic_write(path, value.model_dump_json(indent=2, exclude_none=True))


def _profile_path(user_id: str = "default_user") -> Path:
    """生成指定用户画像的 JSON 文件路径。"""
    return _memory_root() / "users" / f"{validate_user_id(user_id)}.json"


def _session_path(session_id: str = "default_session") -> Path:
    """生成指定会话状态的 JSON 文件路径，并对文件名做安全处理。"""
    forbidden = set('<>:"/\\|?*')
    if not session_id or any(character in forbidden for character in session_id):
        raise ValueError("无效的会话 ID。")
    safe_name = session_id.replace(" ", "_")
    return _memory_root() / "sessions" / f"{safe_name}.json"


def _trip_dir(trip_id: str) -> Path:
    """生成指定旅行记录的存储目录路径。"""
    if not trip_id.startswith("trip_") or not trip_id.removeprefix("trip_").isalnum():
        raise ValueError("无效的旅行 ID。")
    return _memory_root() / "trips" / trip_id


def load_user_profile(user_id: str = "default_user") -> UserProfile:
    """加载指定用户的长期旅行画像；数据库优先，JSON 存档兜底。"""
    store = _state_store()
    try:
        return store.load_user_profile(user_id)
    except LookupError:
        return _load_model(_profile_path(user_id), UserProfile)


def save_user_profile(profile: UserProfile, user_id: str = "default_user") -> None:
    """保存指定用户的长期旅行画像，并同步到 JSON 兼容存档。"""
    _save_model(_profile_path(user_id), profile)
    try:
        _state_store().save_user_profile(profile, user_id)
    except LookupError:
        # 新用户由 initialize_session 或 save_agent_state 创建。
        return


def update_user_profile(
    updates: UserProfile,
    user_id: str = "default_user",
    *,
    clear_fields: list[str] | None = None,
    remove_items: dict[str, list] | None = None,
) -> UserProfile:
    """把增量更新应用到指定用户的长期画像并持久化。"""
    profile = load_user_profile(user_id).apply_update(
        updates,
        clear_fields=clear_fields,
        remove_items=remove_items,
    )
    save_user_profile(profile, user_id)
    return profile


def load_agent_state(session_id: str = "default_session", user_id: str | None = None) -> AgentState:
    """加载数据库中的会话状态；数据库不可用时回退到 JSON 存档。"""
    normalized_user_id = validate_user_id(user_id or "default_user")
    try:
        return _state_store().load_agent_state(session_id, normalized_user_id)
    except (LookupError, ValueError, ValidationError, OSError):
        pass
    return _load_legacy_agent_state(session_id, user_id)


def _load_legacy_agent_state(session_id: str, user_id: str | None) -> AgentState:
    """从旧 JSON 存档加载会话并保留 1.x 字段迁移逻辑。"""
    path = _session_path(session_id)
    if path.exists():
        state = _load_model(path, AgentState)
        if user_id is not None and state.user_id != validate_user_id(user_id):
            raise ValueError("该会话不属于当前用户。")
    else:
        state = AgentState(user_id=validate_user_id(user_id or "default_user"), session_id=session_id)

    state.session_id = session_id
    legacy_profile = state.user_profile
    legacy_values = {
        field: getattr(legacy_profile, field, None)
        for field in [
            "departure_city", "destination", "travel_month", "travel_dates",
            "travel_days", "budget", "currency",
        ]
    }
    if any(value not in (None, "") for value in legacy_values.values()):
        state.travel_request = state.travel_request.apply_update(
            state.travel_request.__class__(**legacy_values)
        )
    state.user_profile = load_user_profile(state.user_id)
    return state


def initialize_session(user_id: str, session_id: str | None = None) -> AgentState:
    """创建并保存一次登录后的新会话，同时确保用户 ID 已被持久化。"""
    normalized_user_id = validate_user_id(user_id)
    state = AgentState(
        user_id=normalized_user_id,
        session_id=session_id or new_session_id(),
        user_profile=load_user_profile(normalized_user_id),
    )
    save_agent_state(state)
    return state


def save_agent_state(state: AgentState) -> None:
    """以数据库为主存，JSON 存档作为迁移与离线兜底。"""
    state.user_id = validate_user_id(state.user_id)
    _state_store().save_agent_state(state)
    _save_model(_profile_path(state.user_id), state.user_profile)
    _save_model(_session_path(state.session_id), state)
    _sync_trip_state(state)


def _sync_trip_state(state: AgentState) -> None:
    """把会话中的当前旅行数据同步到独立 TripState 存档。"""
    path = _trip_dir(state.trip_id) / "trip.json"
    versions = []
    created_at = datetime.utcnow()
    if path.exists():
        try:
            previous = TripState(**json.loads(path.read_text(encoding="utf-8")))
            versions = previous.itinerary_versions
            created_at = previous.created_at
        except (json.JSONDecodeError, ValidationError, OSError):
            pass
    trip = TripState(
        trip_id=state.trip_id,
        user_id=state.user_id,
        session_id=state.session_id,
        travel_request=state.travel_request,
        current_itinerary=state.current_itinerary,
        structured_itinerary=state.structured_itinerary,
        budget_plan=state.budget_plan,
        weather_info=state.weather_info,
        exchange_info=state.exchange_info,
        itinerary_versions=versions,
        created_at=created_at,
    )
    _save_model(path, trip)


def save_trip_state(trip: TripState) -> None:
    """将旅行状态保存到以旅行 ID 命名的目录中。"""
    trip_path = _trip_dir(trip.trip_id) / "trip.json"
    _save_model(trip_path, trip)


def create_trip_state(title: str | None = None) -> TripState:
    """创建带唯一 ID 的旅行状态，保存后返回该对象。"""
    trip = TripState(trip_id=new_trip_id(), title=title)
    save_trip_state(trip)
    return trip
