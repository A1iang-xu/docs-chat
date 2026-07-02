"""DeepSeek API 封装 —— 支持流式调用、指数退避重试、Token 用量记录

v3.3 升级:
- LLM 降级保障: 主模型失败时自动降级到备选模型
"""
import logging
from typing import AsyncGenerator, Optional
from openai import AsyncOpenAI
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMService:
    """封装 DeepSeek API（OpenAI 兼容接口），v3.3: 支持备选模型降级"""

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
            timeout=httpx.Timeout(120.0, connect=10.0),
        )
        self.model = settings.DEEPSEEK_MODEL
        self.fallback_model = settings.LLM_FALLBACK_MODEL or settings.DEEPSEEK_MODEL
        self.max_tokens = settings.DEEPSEEK_MAX_TOKENS
        self.temperature = settings.DEEPSEEK_TEMPERATURE
        self.max_retries = 3
        self.retry_base_ms = 1000

    async def chat_stream(
        self,
        messages: list[dict],
        system_prompt: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """流式调用，v3.3: 支持主模型失败后降级到备选模型。"""
        if settings.LLM_FALLBACK_ENABLED and self.fallback_model != self.model:
            try:
                async for token in self._chat_stream_with_model(
                    messages, system_prompt, self.model
                ):
                    yield token
                return
            except Exception as e:
                logger.warning("主模型 %s 失败，降级到备选 %s: %s", self.model, self.fallback_model, e)
                async for token in self._chat_stream_with_model(
                    messages, system_prompt, self.fallback_model
                ):
                    yield token
                return

        async for token in self._chat_stream_with_model(
            messages, system_prompt, self.model
        ):
            yield token

    async def _chat_stream_with_model(
        self,
        messages: list[dict],
        system_prompt: Optional[str] = None,
        model: str = "",
    ) -> AsyncGenerator[str, None]:
        model = model or self.model
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        last_exception = None
        for attempt in range(self.max_retries + 1):
            try:
                stream = await self.client.chat.completions.create(
                    model=model,
                    messages=full_messages,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    stream=True,
                )
                async for chunk in stream:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if delta and delta.content:
                        yield delta.content
                return
            except Exception as e:
                last_exception = e
                if attempt < self.max_retries:
                    delay = self.retry_base_ms * (2 ** attempt)
                    logger.warning(
                        f"模型 %s 调用失败 (attempt {attempt + 1}/{self.max_retries + 1})，"
                        f"{delay}ms 后重试: {e}", model,
                    )
                    await self._async_sleep(delay / 1000)
                else:
                    logger.error(f"模型 %s 调用最终失败: {e}", model)

        raise last_exception or RuntimeError(f"LLM {model} 调用失败")

    async def chat(
        self,
        messages: list[dict],
        system_prompt: Optional[str] = None,
    ) -> str:
        """非流式调用，v3.3: 支持主模型失败后降级。"""
        if settings.LLM_FALLBACK_ENABLED and self.fallback_model != self.model:
            try:
                return await self._chat_with_model(messages, system_prompt, self.model)
            except Exception as e:
                logger.warning("主模型 %s 非流式失败，降级到备选 %s: %s", self.model, self.fallback_model, e)
                return await self._chat_with_model(messages, system_prompt, self.fallback_model)

        return await self._chat_with_model(messages, system_prompt, self.model)

    async def _chat_with_model(
        self,
        messages: list[dict],
        system_prompt: Optional[str] = None,
        model: str = "",
    ) -> str:
        model = model or self.model
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        response = await self.client.chat.completions.create(
            model=model,
            messages=full_messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            stream=False,
        )
        return response.choices[0].message.content or ""

    @staticmethod
    async def _async_sleep(seconds: float):
        import asyncio
        await asyncio.sleep(seconds)


llm_service = LLMService()
