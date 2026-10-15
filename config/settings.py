from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """集中声明并校验项目运行配置。"""
    deepseek_api_key: str | None = Field(default=None, alias="DEEPSEEK_API_KEY")  # DeepSeek API Key
    deepseek_base_url: str = Field(default="https://api.deepseek.com", alias="DEEPSEEK_BASE_URL")  # DeepSeek/OpenAI-compatible API 地址
    deepseek_model: str = Field(default="deepseek-v4-flash", alias="DEEPSEEK_MODEL")  # 对话模型名
    llm_temperature: float = Field(default=0.3, alias="LLM_TEMPERATURE")  # 默认生成温度
    api_timeout: int = Field(default=180, alias="API_TIMEOUT")  # 通用请求超时秒数
    max_retries: int = Field(default=3, alias="MAX_RETRIES")  # 通用最大重试次数
    mcp_enabled: bool = Field(default=False, alias="MCP_ENABLED")  # 是否启用高德 MCP
    amap_mcp_url: str | None = Field(default=None, alias="AMAP_MCP_URL")  # 高德 MCP 地址
    amap_mcp_token: str | None = Field(default=None, alias="AMAP_MCP_TOKEN")  # 高德 MCP Token
    amap_mcp_tool_map: dict[str, str] = Field(default_factory=dict, alias="AMAP_MCP_TOOL_MAP")  # 高德工具别名映射
    mcp_timeout_seconds: float = Field(default=120, gt=0, alias="MCP_TIMEOUT_SECONDS")  # 高德 MCP 请求超时
    mcp_sse_read_timeout_seconds: float = Field(default=900, gt=0, alias="MCP_SSE_READ_TIMEOUT_SECONDS")  # 高德 MCP SSE 读取超时
    railway_mcp_enabled: bool = Field(default=False, alias="RAILWAY_MCP_ENABLED")  # 是否启用 12306 MCP
    railway_mcp_url: str | None = Field(default=None, alias="RAILWAY_MCP_URL")  # 12306 MCP 地址
    railway_mcp_token: str | None = Field(default=None, alias="RAILWAY_MCP_TOKEN")  # 12306 MCP Token
    railway_mcp_tool_map: dict[str, str] = Field(default_factory=dict, alias="RAILWAY_MCP_TOOL_MAP")  # 12306 工具映射
    railway_mcp_timeout_seconds: float = Field(default=120, gt=0, alias="RAILWAY_MCP_TIMEOUT_SECONDS")  # 12306 请求超时
    railway_mcp_sse_read_timeout_seconds: float = Field(default=900, gt=0, alias="RAILWAY_MCP_SSE_READ_TIMEOUT_SECONDS")  # 12306 SSE 超时
    xhs_mcp_enabled: bool = Field(default=False, alias="XHS_MCP_ENABLED")  # 是否启用小红书 MCP
    xhs_mcp_url: str = Field(default="http://127.0.0.1:18060/mcp", alias="XHS_MCP_URL")  # 小红书 MCP 地址
    xhs_mcp_port: int = Field(default=18060, gt=0, le=65535, alias="XHS_MCP_PORT")  # 小红书 MCP 端口
    xhs_mcp_data_dir: Path = Field(default=PROJECT_ROOT / ".xhs-mcp", alias="XHS_MCP_DATA_DIR")  # 小红书数据目录
    xhs_mcp_headless: bool = Field(default=False, alias="XHS_MCP_HEADLESS")  # 是否无头浏览器
    xhs_mcp_request_interval_ms: int = Field(default=5000, ge=2000, alias="XHS_MCP_REQUEST_INTERVAL")  # 请求间隔毫秒
    xhs_mcp_timeout_seconds: float = Field(default=120, gt=0, alias="XHS_MCP_TIMEOUT_SECONDS")  # 请求超时
    xhs_mcp_sse_read_timeout_seconds: float = Field(default=900, gt=0, alias="XHS_MCP_SSE_READ_TIMEOUT_SECONDS")  # SSE 超时
    database_url: str = Field(default="sqlite+pysqlite:///./travelmind.db", alias="DATABASE_URL")  # 数据库连接串
    database_echo: bool = Field(default=False, alias="DATABASE_ECHO")  # 是否打印 SQL
    db_pool_size: int = Field(default=5, gt=0, alias="DB_POOL_SIZE")  # 连接池大小
    db_max_overflow: int = Field(default=10, ge=0, alias="DB_MAX_OVERFLOW")  # 最大溢出连接
    checkpoint_backend: str = Field(default="postgresql", alias="CHECKPOINT_BACKEND")  # Checkpoint 后端
    memory_recent_turns: int = Field(default=8, gt=0, alias="MEMORY_RECENT_TURNS")  # 短期保留轮数
    memory_summary_after_turns: int = Field(default=12, gt=1, alias="MEMORY_SUMMARY_AFTER_TURNS")  # 触发摘要轮数
    memory_max_context_tokens: int = Field(default=6000, gt=0, alias="MEMORY_MAX_CONTEXT_TOKENS")  # 上下文最大 Token
    memory_summary_max_tokens: int = Field(default=800, gt=0, alias="MEMORY_SUMMARY_MAX_TOKENS")  # 摘要最大 Token
    dashscope_api_key: str | None = Field(default=None, alias="DASHSCOPE_API_KEY")  # DashScope/百炼 API Key
    embedding_base_url: str = Field(default="https://dashscope.aliyuncs.com/compatible-mode/v1", alias="EMBEDDING_BASE_URL")  # Embedding API 地址
    embedding_model: str = Field(default="text-embedding-v3", alias="EMBEDDING_MODEL")  # Embedding 模型
    embedding_dimensions: int = Field(default=1024, gt=0, alias="EMBEDDING_DIMENSIONS")  # 向量维度
    embedding_batch_size: int = Field(default=16, gt=0, alias="EMBEDDING_BATCH_SIZE")  # 向量化批量大小
    rag_raw_dir: Path = PROJECT_ROOT / "rag_data"  # RAG 原始文件目录
    rag_dense_top_k: int = Field(default=20, gt=0, alias="RAG_DENSE_TOP_K")  # 向量召回数量
    rag_bm25_top_k: int = Field(default=20, gt=0, alias="RAG_BM25_TOP_K")  # BM25 召回数量
    rag_geo_top_k: int = Field(default=20, gt=0, alias="RAG_GEO_TOP_K")  # 地理召回数量
    rag_template_top_k: int = Field(default=20, gt=0, alias="RAG_TEMPLATE_TOP_K")  # 模板召回数量
    rag_rrf_top_k: int = Field(default=15, gt=0, alias="RAG_RRF_TOP_K")  # RRF 融合数量
    rag_min_relevance: float = Field(default=0.0, ge=0, le=1, alias="RAG_MIN_RELEVANCE")  # RAG 最低相关度
    xhs_pilot_user_id: str = Field(default="demo_traveler", alias="XHS_PILOT_USER_ID")  # 试点数据所属用户
    xhs_pilot_notes_per_cell: int = Field(default=10, gt=0, le=50, alias="XHS_PILOT_NOTES_PER_CELL")  # 每个搜索单元抓取笔记数
    memory_retrieval_top_k: int = Field(default=8, gt=0, alias="MEMORY_RETRIEVAL_TOP_K")  # 记忆召回数量
    memory_injection_top_k: int = Field(default=5, gt=0, alias="MEMORY_INJECTION_TOP_K")  # 记忆注入数量
    memory_min_relevance: float = Field(default=0.70, ge=0, le=1, alias="MEMORY_MIN_RELEVANCE")  # 记忆最低相似度
    memory_semantic_write_threshold: float = Field(default=0.85, ge=0, le=1, alias="MEMORY_SEMANTIC_WRITE_THRESHOLD")  # 语义记忆写入阈值
    memory_procedural_write_threshold: float = Field(default=0.85, ge=0, le=1, alias="MEMORY_PROCEDURAL_WRITE_THRESHOLD")  # 程序记忆写入阈值
    memory_min_evidence_count: int = Field(default=2, gt=1, alias="MEMORY_MIN_EVIDENCE_COUNT")  # 归纳最少证据数
    api_cors_origins: str = Field(  # 允许的前端来源
        default="http://localhost:5173,http://127.0.0.1:5173",
        alias="API_CORS_ORIGINS",
    )
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")  # 日志级别
    log_json: bool = Field(default=True, alias="LOG_JSON")  # 是否 JSON 日志
    log_to_stdout: bool = Field(default=True, alias="LOG_TO_STDOUT")  # 是否输出 stdout
    memory_dir: Path = PROJECT_ROOT / "memory_data"  # 本地记忆目录
    output_dir: Path = PROJECT_ROOT / "outputs"  # 输出目录
    log_dir: Path = PROJECT_ROOT / "logs"  # 日志目录

    model_config = SettingsConfigDict(env_file=str(PROJECT_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """加载环境变量并返回进程内缓存的项目配置。"""
    load_dotenv(PROJECT_ROOT / ".env")
    return Settings()
