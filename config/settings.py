from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    deepseek_api_key: str | None = Field(default=None, alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field(default="https://api.deepseek.com", alias="DEEPSEEK_BASE_URL")
    deepseek_model: str = Field(default="deepseek-v4-flash", alias="DEEPSEEK_MODEL")
    llm_temperature: float = Field(default=0.3, alias="LLM_TEMPERATURE")
    api_timeout: int = Field(default=10, alias="API_TIMEOUT")
    max_retries: int = Field(default=1, alias="MAX_RETRIES")
    mcp_enabled: bool = Field(default=False, alias="MCP_ENABLED")
    amap_mcp_url: str | None = Field(default=None, alias="AMAP_MCP_URL")
    amap_mcp_token: str | None = Field(default=None, alias="AMAP_MCP_TOKEN")
    amap_mcp_tool_map: dict[str, str] = Field(default_factory=dict, alias="AMAP_MCP_TOOL_MAP")
    mcp_timeout_seconds: float = Field(default=30, gt=0, alias="MCP_TIMEOUT_SECONDS")
    mcp_sse_read_timeout_seconds: float = Field(default=300, gt=0, alias="MCP_SSE_READ_TIMEOUT_SECONDS")
    railway_mcp_enabled: bool = Field(default=False, alias="RAILWAY_MCP_ENABLED")
    railway_mcp_url: str | None = Field(default=None, alias="RAILWAY_MCP_URL")
    railway_mcp_token: str | None = Field(default=None, alias="RAILWAY_MCP_TOKEN")
    railway_mcp_tool_map: dict[str, str] = Field(default_factory=dict, alias="RAILWAY_MCP_TOOL_MAP")
    railway_mcp_timeout_seconds: float = Field(default=30, gt=0, alias="RAILWAY_MCP_TIMEOUT_SECONDS")
    railway_mcp_sse_read_timeout_seconds: float = Field(default=300, gt=0, alias="RAILWAY_MCP_SSE_READ_TIMEOUT_SECONDS")
    database_url: str = Field(default="sqlite+pysqlite:///./travelmind.db", alias="DATABASE_URL")
    database_echo: bool = Field(default=False, alias="DATABASE_ECHO")
    db_pool_size: int = Field(default=5, gt=0, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=10, ge=0, alias="DB_MAX_OVERFLOW")
    checkpoint_backend: str = Field(default="postgresql", alias="CHECKPOINT_BACKEND")
    memory_recent_turns: int = Field(default=8, gt=0, alias="MEMORY_RECENT_TURNS")
    memory_summary_after_turns: int = Field(default=12, gt=1, alias="MEMORY_SUMMARY_AFTER_TURNS")
    memory_max_context_tokens: int = Field(default=6000, gt=0, alias="MEMORY_MAX_CONTEXT_TOKENS")
    memory_summary_max_tokens: int = Field(default=800, gt=0, alias="MEMORY_SUMMARY_MAX_TOKENS")
    dashscope_api_key: str | None = Field(default=None, alias="DASHSCOPE_API_KEY")
    embedding_base_url: str = Field(default="https://dashscope.aliyuncs.com/compatible-mode/v1", alias="EMBEDDING_BASE_URL")
    embedding_model: str = Field(default="text-embedding-v3", alias="EMBEDDING_MODEL")
    embedding_dimensions: int = Field(default=1024, gt=0, alias="EMBEDDING_DIMENSIONS")
    embedding_batch_size: int = Field(default=16, gt=0, alias="EMBEDDING_BATCH_SIZE")
    rag_raw_dir: Path = PROJECT_ROOT / "rag_data"
    rag_dense_top_k: int = Field(default=20, gt=0, alias="RAG_DENSE_TOP_K")
    rag_bm25_top_k: int = Field(default=20, gt=0, alias="RAG_BM25_TOP_K")
    rag_geo_top_k: int = Field(default=20, gt=0, alias="RAG_GEO_TOP_K")
    rag_template_top_k: int = Field(default=20, gt=0, alias="RAG_TEMPLATE_TOP_K")
    rag_rrf_top_k: int = Field(default=15, gt=0, alias="RAG_RRF_TOP_K")
    rag_min_relevance: float = Field(default=0.0, ge=0, le=1, alias="RAG_MIN_RELEVANCE")
    memory_retrieval_top_k: int = Field(default=8, gt=0, alias="MEMORY_RETRIEVAL_TOP_K")
    memory_injection_top_k: int = Field(default=5, gt=0, alias="MEMORY_INJECTION_TOP_K")
    memory_min_relevance: float = Field(default=0.70, ge=0, le=1, alias="MEMORY_MIN_RELEVANCE")
    memory_semantic_write_threshold: float = Field(default=0.85, ge=0, le=1, alias="MEMORY_SEMANTIC_WRITE_THRESHOLD")
    memory_procedural_write_threshold: float = Field(default=0.85, ge=0, le=1, alias="MEMORY_PROCEDURAL_WRITE_THRESHOLD")
    memory_min_evidence_count: int = Field(default=2, gt=1, alias="MEMORY_MIN_EVIDENCE_COUNT")
    api_cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        alias="API_CORS_ORIGINS",
    )
    memory_dir: Path = PROJECT_ROOT / "memory_data"
    output_dir: Path = PROJECT_ROOT / "outputs"
    log_dir: Path = PROJECT_ROOT / "logs"

    model_config = SettingsConfigDict(env_file=str(PROJECT_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """加载环境变量并返回进程内缓存的项目配置。"""
    load_dotenv(PROJECT_ROOT / ".env")
    return Settings()
