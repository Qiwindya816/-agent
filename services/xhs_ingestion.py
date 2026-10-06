"""提供 核心领域服务和外部服务适配；本文件负责 `xhs_ingestion` 相关实现。"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from config.settings import get_settings
from db.engine import DatabaseEngine, get_database_engine
from db.models import RagSource, SocialMetricSnapshot, SocialNote, User
from exceptions.external_api import ExternalAPIError
from services.embedding_service import EmbeddingService
from services.mcp_client import MCPClient
from services.rag_ingestion import RagIngestionService


READ_ONLY_TOOLS = frozenset(
    {
        "xhs_list_accounts",
        "xhs_add_account",
        "xhs_check_login_session",
        "xhs_submit_verification",
        "xhs_check_auth_status",
        "xhs_search",
        "xhs_get_note",
    }
)


@dataclass
class PilotIngestionResult:
    """承载 试点、导入 的结构化结果。"""
    source_id: str
    cells_processed: int = 0
    searches: int = 0
    notes_fetched: int = 0
    documents_created: int = 0
    notes_reused: int = 0
    metric_snapshots_created: int = 0
    errors: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """转换为dict，供后续流程使用。"""
        return asdict(self)


class XhsMcpService:
    """提供 `XhsMcpService` 对应领域能力的统一服务。"""

    def __init__(self, client: MCPClient | None = None) -> None:
        """初始化 XhsMcpService 及其运行依赖。"""
        settings = get_settings()
        self.client = client or MCPClient(
            settings.xhs_mcp_url,
            timeout_seconds=settings.xhs_mcp_timeout_seconds,
            sse_read_timeout_seconds=settings.xhs_mcp_sse_read_timeout_seconds,
        )

    def list_tools(self) -> list[dict[str, Any]]:
        """列出工具列表并返回符合当前作用域的结果。"""
        tools = self.client.list_tools()
        unexpected = {str(tool.get("name")) for tool in tools} - READ_ONLY_TOOLS
        if unexpected:
            raise ExternalAPIError(f"小红书 MCP 暴露了未授权工具：{', '.join(sorted(unexpected))}")
        return tools

    def call(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        """调用白名单内的小红书 MCP 只读工具并规范化响应。"""
        if name not in READ_ONLY_TOOLS:
            raise ValueError(f"不允许调用小红书写操作或未知工具：{name}")
        data, _ = self.client.call_tool(name, arguments or {})
        return _decode_json(data)

    def list_accounts(self) -> dict[str, Any]:
        """列出accounts并返回符合当前作用域的结果。"""
        return _as_mapping(self.call("xhs_list_accounts"))

    def begin_login(self, name: str | None = None) -> dict[str, Any]:
        """启动小红书扫码登录流程并返回登录提示。"""
        return _as_mapping(self.call("xhs_add_account", {"name": name} if name else {}))

    def check_login(self, session_id: str) -> dict[str, Any]:
        """检查登录状态并返回校验结果。"""
        return _as_mapping(self.call("xhs_check_login_session", {"sessionId": session_id}))

    def submit_verification(self, session_id: str, code: str) -> dict[str, Any]:
        """提交登录验证信息并返回 MCP 校验结果。"""
        return _as_mapping(
            self.call("xhs_submit_verification", {"sessionId": session_id, "code": code})
        )

    def check_auth(self, account: str | None = None) -> dict[str, Any]:
        """检查auth并返回校验结果。"""
        return _as_mapping(
            self.call("xhs_check_auth_status", {"account": account} if account else {})
        )

    def search(
        self,
        keyword: str,
        *,
        count: int,
        timeout_ms: int,
        sort_by: str = "general",
        note_type: str = "all",
        publish_time: str = "half_year",
        account: str | None = None,
    ) -> list[dict[str, Any]]:
        """执行带用户隔离和可选过滤条件的检索。"""
        arguments: dict[str, Any] = {
            "keyword": keyword,
            "count": count,
            "timeout": timeout_ms,
            "sortBy": sort_by,
            "noteType": note_type,
            "publishTime": publish_time,
        }
        if account:
            arguments["account"] = account
        payload = self.call("xhs_search", arguments)
        if isinstance(payload, list):
            successful = next(
                (item for item in payload if isinstance(item, dict) and item.get("success")), None
            )
            payload = successful or {}
        mapping = _as_mapping(payload)
        items = mapping.get("items", [])
        return [item for item in items if isinstance(item, dict)]

    def get_note(
        self,
        note_id: str,
        xsec_token: str,
        *,
        account: str | None = None,
    ) -> dict[str, Any]:
        """获取笔记并返回符合当前作用域的结果。"""
        arguments: dict[str, Any] = {
            "noteId": note_id,
            "xsecToken": xsec_token,
            "describeImages": False,
        }
        if account:
            arguments["account"] = account
        return _as_mapping(self.call("xhs_get_note", arguments))


class XhsPilotIngestionService:
    """提供 `XhsPilotIngestionService` 对应领域能力的统一服务。"""

    SOURCE_NAME = "小红书旅游攻略试点"

    def __init__(
        self,
        database: DatabaseEngine | None = None,
        mcp: XhsMcpService | None = None,
        embeddings: EmbeddingService | None = None,
    ) -> None:
        """初始化 XhsPilotIngestionService 及其运行依赖。"""
        self.database = database or get_database_engine()
        self.mcp = mcp or XhsMcpService()
        self.ingestion = RagIngestionService(self.database)
        self.embeddings = embeddings
        self.settings = get_settings()

    def run(
        self,
        config_path: Path,
        *,
        account: str | None = None,
        cities: set[str] | None = None,
        themes: set[str] | None = None,
        notes_per_cell: int | None = None,
        embed: bool = True,
    ) -> PilotIngestionResult:
        """按城市和主题批量采集笔记，并导入 RAG 知识库。"""
        config = json.loads(config_path.read_text(encoding="utf-8"))
        user_id = self.settings.xhs_pilot_user_id
        source = self._ensure_source(user_id)
        result = PilotIngestionResult(source_id=source.source_id)
        target_count = notes_per_cell or self.settings.xhs_pilot_notes_per_cell
        search_config = config.get("search", {})

        self.mcp.list_tools()
        accounts = self.mcp.list_accounts().get("accounts", [])
        if not accounts:
            raise ExternalAPIError("尚未登录小红书账号，请先执行 python scripts/manage_xhs.py login")

        for city_config in config.get("cities", []):
            city = str(city_config.get("name", "")).strip()
            if not city or (cities and city not in cities):
                continue
            for theme_config in city_config.get("themes", []):
                theme_id = str(theme_config.get("id", "")).strip()
                theme_label = str(theme_config.get("label", theme_id)).strip()
                if themes and theme_id not in themes and theme_label not in themes:
                    continue
                result.cells_processed += 1
                candidates: dict[str, dict[str, Any]] = {}
                searches_for_cell = 0
                sort_options = search_config.get("sort_by", ["general"])
                for keyword in theme_config.get("keywords", []):
                    for sort_by in sort_options:
                        try:
                            items = self.mcp.search(
                                str(keyword),
                                count=max(target_count * 2, 10),
                                timeout_ms=int(search_config.get("timeout_ms", 120000)),
                                sort_by=str(sort_by),
                                note_type=str(search_config.get("note_type", "all")),
                                publish_time=str(search_config.get("publish_time", "half_year")),
                                account=account,
                            )
                            result.searches += 1
                            searches_for_cell += 1
                            for item in items:
                                note_id = str(item.get("id", "")).strip()
                                if is_xhs_note_id(note_id) and note_id not in candidates:
                                    candidates[note_id] = {**item, "crawl_query": str(keyword)}
                        except Exception as exc:  # 单个单元失败后继续处理试点批次中的其他单元
                            result.errors.append(
                                {"stage": "search", "city": city, "theme": theme_id, "error": _error_text(exc)}
                            )
                    if searches_for_cell >= len(sort_options) and len(candidates) >= target_count * 2:
                        break

                selected = 0
                for note_id, candidate in candidates.items():
                    if selected >= target_count:
                        break
                    token = str(candidate.get("xsecToken", "")).strip()
                    if not token:
                        continue
                    try:
                        detail = self.mcp.get_note(note_id, token, account=account)
                        result.notes_fetched += 1
                        created = self._store_note(
                            detail,
                            source_id=source.source_id,
                            user_id=user_id,
                            city=city,
                            theme_id=theme_id,
                            theme_label=theme_label,
                            crawl_query=str(candidate.get("crawl_query", "")),
                            embed=embed,
                        )
                        if created:
                            result.documents_created += 1
                        else:
                            result.notes_reused += 1
                        result.metric_snapshots_created += 1
                        selected += 1
                    except Exception as exc:  # 单篇笔记不可访问时不应终止整个批次
                        result.errors.append(
                            {
                                "stage": "note",
                                "city": city,
                                "theme": theme_id,
                                "note_id": note_id,
                                "error": _error_text(exc),
                            }
                        )
        return result

    def _ensure_source(self, user_id: str) -> RagSource:
        """查找或创建小红书试点对应的 RAG 知识来源。"""
        with self.database.session() as session:
            if session.get(User, user_id) is None:
                session.add(User(user_id=user_id, display_name=user_id))
                session.flush()
            source = session.scalar(
                select(RagSource).where(
                    RagSource.source_type == "xiaohongshu",
                    RagSource.name == self.SOURCE_NAME,
                    RagSource.owner_user_id == user_id,
                )
            )
            if source is None:
                source = RagSource(
                    source_id=f"src_{uuid4().hex[:16]}",
                    source_type="xiaohongshu",
                    name=self.SOURCE_NAME,
                    url="https://www.xiaohongshu.com",
                    license="platform-content-restricted",
                    authorization_status="research_only",
                    owner_user_id=user_id,
                )
                session.add(source)
                session.flush()
            session.refresh(source)
            return source

    def _store_note(
        self,
        detail: dict[str, Any],
        *,
        source_id: str,
        user_id: str,
        city: str,
        theme_id: str,
        theme_label: str,
        crawl_query: str,
        embed: bool,
    ) -> bool:
        """去重保存笔记正文、互动快照并生成 RAG 文档。"""
        note_id = str(detail.get("id", "")).strip()
        if not note_id:
            raise ValueError("笔记详情缺少 id")
        social_note_id = f"xhs_{note_id}"
        now = datetime.now(timezone.utc)
        stats = detail.get("stats") if isinstance(detail.get("stats"), dict) else {}

        with self.database.session() as session:
            existing = session.scalar(
                select(SocialNote).where(
                    SocialNote.platform == "xiaohongshu",
                    SocialNote.external_note_id == note_id,
                )
            )
            if existing is not None:
                merged_themes = list(dict.fromkeys([*(existing.themes or []), theme_id]))
                existing.themes = merged_themes
                existing.fetched_at = now
                self._add_snapshot(session, existing.social_note_id, stats, now)
                return False

        title = str(detail.get("title") or f"小红书旅行笔记 {note_id}").strip()
        description = str(detail.get("desc") or "").strip()
        tags = [str(tag).strip() for tag in detail.get("tags", []) if str(tag).strip()]
        content = _note_content(title, description, tags)
        metadata = {
            "platform": "xiaohongshu",
            "external_note_id": note_id,
            "city": city,
            "theme": theme_id,
            "theme_label": theme_label,
            "tags": tags,
            "content_scope": "note_body_only",
        }
        embeddings: list[list[float]] | None = None
        if embed:
            embedding_service = self.embeddings or EmbeddingService()
            chunks = self.ingestion.chunker.chunk(content, "guide", metadata)
            embeddings = embedding_service.embed_texts([chunk.chunk_text for chunk in chunks])

        published_at = _parse_datetime(detail.get("time"))
        document, created_chunks = self.ingestion.ingest_document(
            source_id,
            title,
            content,
            document_type="guide",
            owner_user_id=user_id,
            metadata=metadata,
            embeddings=embeddings,
            published_at=published_at,
        )
        images = [
            str(image.get("url"))
            for image in detail.get("imageList", [])
            if isinstance(image, dict) and image.get("url")
        ]
        author = detail.get("user") if isinstance(detail.get("user"), dict) else {}
        author_id = str(author.get("userid") or "")
        raw_path = self._store_raw_payload(note_id, _sanitize_raw_payload(detail), now)

        with self.database.session() as session:
            document_row = session.get(type(document), document.document_id)
            if document_row is not None:
                document_row.raw_file_path = str(raw_path)
            social = SocialNote(
                social_note_id=social_note_id,
                platform="xiaohongshu",
                external_note_id=note_id,
                document_id=document.document_id,
                canonical_url=f"https://www.xiaohongshu.com/explore/{note_id}",
                author_hash=_author_hash(author_id) if author_id else None,
                note_type=str(detail.get("type") or "normal"),
                tags=tags,
                image_urls=images,
                city=city,
                themes=[theme_id],
                crawl_query=crawl_query[:255] or None,
                published_at=published_at,
                fetched_at=now,
            )
            session.add(social)
            # 这两个仅用于导入的模型刻意不建立 ORM relationship。
            # 显式刷新父记录，让 PostgreSQL 能确定性校验快照外键。
            session.flush()
            self._add_snapshot(session, social_note_id, stats, now)
        return bool(created_chunks)

    @staticmethod
    def _add_snapshot(session: Any, social_note_id: str, stats: dict[str, Any], captured_at: datetime) -> None:
        """添加snapshot，并保持相关状态或持久化数据一致。"""
        session.add(
            SocialMetricSnapshot(
                snapshot_id=f"metric_{uuid4().hex[:16]}",
                social_note_id=social_note_id,
                likes=parse_engagement_count(stats.get("likedCount")),
                collects=parse_engagement_count(stats.get("collectedCount")),
                comments=parse_engagement_count(stats.get("commentCount")),
                shares=parse_engagement_count(stats.get("shareCount")),
                captured_at=captured_at,
            )
        )

    def _store_raw_payload(self, note_id: str, detail: dict[str, Any], fetched_at: datetime) -> Path:
        """保存脱敏后的原始 MCP 载荷，供审计和问题复现。"""
        directory = self.settings.rag_raw_dir / "xiaohongshu" / note_id
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{fetched_at.strftime('%Y%m%dT%H%M%SZ')}.json"
        path.write_text(json.dumps(detail, ensure_ascii=False, indent=2), encoding="utf-8")
        return path


def parse_engagement_count(value: Any) -> int:
    """Parse counters such as ``1.2万``, ``3k`` and plain integers."""
    if value is None or value == "":
        return 0
    if isinstance(value, (int, float)):
        return max(0, int(value))
    text = str(value).strip().lower().replace(",", "").replace("+", "")
    match = re.search(r"(\d+(?:\.\d+)?)\s*([万亿千wk]?)", text)
    if not match:
        return 0
    multiplier = {"": 1, "千": 1_000, "k": 1_000, "万": 10_000, "w": 10_000, "亿": 100_000_000}
    return max(0, int(float(match.group(1)) * multiplier[match.group(2)]))


def is_xhs_note_id(value: str) -> bool:
    """识别并排除搜索结果中的广告或占位笔记 ID。"""
    return bool(re.fullmatch(r"[0-9a-fA-F]{24}", value.strip()))


def _decode_json(value: Any) -> Any:
    """解码json，供后续流程使用。"""
    if not isinstance(value, str):
        return value
    text = value.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError as exc:
        raise ExternalAPIError(f"小红书 MCP 返回了非 JSON 内容：{text[:200]}") from exc


def _as_mapping(value: Any) -> dict[str, Any]:
    """将未知 MCP 响应安全转换为字典。"""
    if not isinstance(value, dict):
        raise ExternalAPIError(f"小红书 MCP 返回结构异常：{type(value).__name__}")
    return value


def _parse_datetime(value: Any) -> datetime | None:
    """解析datetime，供后续流程使用。"""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)) or str(value).isdigit():
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        try:
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _author_hash(author_id: str) -> str:
    """生成不可逆的作者标识哈希，避免保存直接身份信息。"""
    return hashlib.sha256(f"xiaohongshu:{author_id}".encode("utf-8")).hexdigest()


def _note_content(title: str, description: str, tags: list[str]) -> str:
    """从笔记详情中组合适合 RAG 入库的标题、正文和标签。"""
    sections = [f"# {title}"]
    if description:
        sections.append(description)
    if tags:
        sections.append("相关主题：" + "、".join(tags))
    return "\n\n".join(sections)


def _sanitize_raw_payload(detail: dict[str, Any]) -> dict[str, Any]:
    """保留笔记证据，同时移除评论者和直接作者标识。"""
    sanitized = {key: value for key, value in detail.items() if key not in {"comments", "user"}}
    author = detail.get("user") if isinstance(detail.get("user"), dict) else {}
    author_id = str(author.get("userid") or "")
    sanitized["author"] = {"hash": _author_hash(author_id) if author_id else None}
    return sanitized


def _error_text(error: Exception, limit: int = 600) -> str:
    """从不同形态的 MCP 错误响应中提取可读消息。"""
    text = " ".join(str(error).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
