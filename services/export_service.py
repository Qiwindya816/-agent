from pathlib import Path
import tempfile

from config.settings import get_settings
from schemas.agent_state import AgentState
from utils.ids import validate_user_id


class ExportService:
    def __init__(self) -> None:
        """加载导出目录等项目配置。"""
        self.settings = get_settings()

    def build_final_markdown(self, state: AgentState) -> str:
        """汇总当前旅行需求、长期画像及全部工具结果，生成完整 Markdown。"""
        parts = [
            "# TravelMind 完整旅行方案",
            f"- 用户 ID：`{state.user_id}`",
            f"- 会话 ID：`{state.session_id}`",
            f"- 旅行 ID：`{state.trip_id}`",
        ]

        parts.append("## 当前旅行需求")
        parts.append(f"```json\n{state.travel_request.model_dump_json(indent=2, exclude_none=True)}\n```")

        parts.append("## 长期用户偏好")
        parts.append(f"```json\n{state.user_profile.model_dump_json(indent=2, exclude_none=True)}\n```")

        if state.current_itinerary:
            parts.extend(["## 当前行程", state.current_itinerary])
        if state.budget_plan:
            parts.extend(["## 预算方案", state.budget_plan])
        if state.weather_info:
            parts.extend(["## 天气信息", str(state.weather_info.get("result") or state.weather_info)])
        if state.exchange_info:
            parts.extend(["## 汇率信息", str(state.exchange_info.get("result") or state.exchange_info)])
        return "\n\n".join(parts)

    def save_request_response(self, state: AgentState, content: str) -> Path:
        """按 request_id 保存本轮原始回答，保证不同轮次不会互相覆盖。"""
        request_id = state.request_id or "unknown_request"
        path = self._session_dir(state) / "requests" / f"{request_id}.md"
        self._atomic_write(path, content)
        return path

    def save_versioned_snapshot(self, state: AgentState) -> tuple[Path, Path]:
        """保存不可变版本和 latest 快照，并更新状态中的输出版本号。"""
        state.output_version += 1
        content = self.build_final_markdown(state)
        session_dir = self._session_dir(state)
        version_path = session_dir / "versions" / f"v{state.output_version:04d}.md"
        latest_path = session_dir / "latest.md"
        self._atomic_write(version_path, content)
        self._atomic_write(latest_path, content)
        return version_path, latest_path

    def save_markdown(self, content: str, filename: str = "travel_result.md") -> Path:
        """兼容旧调用，将指定内容原子保存到输出根目录。"""
        path = self.settings.output_dir / filename
        self._atomic_write(path, content)
        return path

    def _session_dir(self, state: AgentState) -> Path:
        """返回用户和会话隔离后的输出目录。"""
        user_id = validate_user_id(state.user_id)
        return self.settings.output_dir / "users" / user_id / "sessions" / state.session_id

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        """通过同目录临时文件原子替换目标 Markdown，避免半写入文件。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", delete=False, dir=str(path.parent), suffix=".tmp"
        ) as temp_file:
            temp_file.write(content)
            temp_path = Path(temp_file.name)
        temp_path.replace(path)
