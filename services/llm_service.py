from openai import OpenAI

from config.settings import get_settings
from exceptions.llm import LLMServiceError
from utils.json_parser import parse_json_object


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
            )
        return self._client

    def generate_text(
        self,
        prompt: str,
        *,
        system_prompt: str = "你是一名专业的旅行助手。",
        temperature: float | None = None,
    ) -> str:
        """调用配置的语言模型并返回纯文本响应。"""
        response = self.client.chat.completions.create(
            model=self.settings.deepseek_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=self.settings.llm_temperature if temperature is None else temperature,
        )
        return response.choices[0].message.content or ""

    def generate_json(
        self,
        prompt: str,
        *,
        system_prompt: str = "你是一个严格输出 JSON 的助手。",
        temperature: float = 0,
    ) -> dict:
        """调用语言模型并将响应解析为 JSON 对象。"""
        return parse_json_object(
            self.generate_text(prompt, system_prompt=system_prompt, temperature=temperature)
        )
