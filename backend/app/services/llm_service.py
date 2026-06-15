"""DeepSeek API 封装 —— 支持流式调用、指数退避重试、Token 用量记录"""
import logging
from typing import AsyncGenerator, Optional
from openai import AsyncOpenAI
from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMService:
    """封装 DeepSeek API（OpenAI 兼容接口），提供流式和非流式调用"""

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
        )
        self.model = settings.DEEPSEEK_MODEL
        self.max_tokens = settings.DEEPSEEK_MAX_TOKENS
        self.temperature = settings.DEEPSEEK_TEMPERATURE
        self.max_retries = 3
        self.retry_base_ms = 1000

    async def chat_stream(
        self,
        messages: list[dict],
        system_prompt: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """
        流式调用 DeepSeek Chat API，逐 token 返回。
        支持指数退避重试（最多 3 次）。

        Args:
            messages: 对话历史，格式 [{"role": "user", "content": "..."}]
            system_prompt: 系统提示词（可选）

        Yields:
            每个 delta token 的文本内容
        """
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        last_exception = None
        for attempt in range(self.max_retries + 1):
            try:
                stream = await self.client.chat.completions.create(
                    model=self.model,
                    messages=full_messages,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    stream=True,
                )

                async for chunk in stream:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if delta and delta.content:
                        yield delta.content

                return  # 成功完成

            except Exception as e:
                last_exception = e
                if attempt < self.max_retries:
                    delay = self.retry_base_ms * (2 ** attempt)
                    logger.warning(
                        f"DeepSeek API 调用失败 (attempt {attempt + 1}/{self.max_retries + 1})，"
                        f"{delay}ms 后重试: {e}"
                    )
                    await self._async_sleep(delay / 1000)
                else:
                    logger.error(f"DeepSeek API 调用最终失败: {e}")

        raise last_exception or RuntimeError("DeepSeek API 调用失败")

    async def chat(
        self,
        messages: list[dict],
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        非流式调用 DeepSeek Chat API，返回完整回答。

        Args:
            messages: 对话历史
            system_prompt: 系统提示词（可选）

        Returns:
            完整回答文本
        """
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=full_messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            stream=False,
        )

        return response.choices[0].message.content or ""

    @staticmethod
    async def _async_sleep(seconds: float):
        """异步 sleep，兼容不同事件循环"""
        import asyncio
        await asyncio.sleep(seconds)


# 全局单例
llm_service = LLMService()