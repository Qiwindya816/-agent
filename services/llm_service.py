from openai import OpenAI
import time

from config.settings import get_settings
from exceptions.llm import LLMServiceError
from utils.json_parser import parse_json_object
from utils.logger import get_logger


logger = get_logger("llm")


class LLMService:
    """统一管理 DeepSeek/OpenAI-compatible LLM 调用。"""

    def __init__(self) -> None:
        """加载模型配置，并延迟创建 API 客户端。"""
        self.settings = get_settings()
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI:
        """校验 API 密钥，按需创建并缓存 OpenAI 兼容客户端。"""
        if not self.settings.deepseek_api_key:
            raise LLMServiceError("缺少 DEEPSEEK_API_KEY，请在本地 .env 文件中配置。")
        if self._client is None:
            self._client = OpenAI(
                api_key=self.settings.deepseek_api_key,
                base_url=self.settings.deepseek_base_url,
                timeout=self.settings.api_timeout,
                max_retries=self.settings.max_retries,
            )
        return self._client

    def generate_text(
        self,
        prompt: str,
        *,
        system_prompt: str = "你是一名专业的旅行助手。",
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """调用配置的语言模型并返回纯文本响应。"""
        started = time.perf_counter()
        try:
            request = {
                "model": self.settings.deepseek_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "temperature": self.settings.llm_temperature if temperature is None else temperature,
            }
            if max_tokens is not None:
                request["max_tokens"] = max_tokens
            response = self.client.chat.completions.create(
                **request,
            )
        except Exception:
            logger.exception(
                "llm_call_failed",
                extra={"event_name": "llm_call_failed", "elapsed_ms": round((time.perf_counter() - started) * 1000, 3)},
            )
            raise
        usage = response.usage
        logger.info(
            "llm_call_completed",
            extra={
                "event_name": "llm_call_completed",
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                "prompt_tokens": getattr(usage, "prompt_tokens", None),
                "completion_tokens": getattr(usage, "completion_tokens", None),
                "total_tokens": getattr(usage, "total_tokens", None),
            },
        )
        return response.choices[0].message.content or ""

    def generate_json(
        self,
        prompt: str,
        *,
        system_prompt: str = "你是一个严格输出 JSON 的助手。",
        temperature: float = 0,
        max_tokens: int | None = None,
    ) -> dict:
        """调用语言模型并将响应解析为 JSON 对象。"""
        return parse_json_object(
            self.generate_text(
                prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        )
