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
    memory_dir: Path = PROJECT_ROOT / "memory_data"
    output_dir: Path = PROJECT_ROOT / "outputs"
    log_dir: Path = PROJECT_ROOT / "logs"

    model_config = SettingsConfigDict(env_file=str(PROJECT_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """加载环境变量并返回进程内缓存的项目配置。"""
    load_dotenv(PROJECT_ROOT / ".env")
    return Settings()
