"""LLM 服务层测试 —— 使用 Mock 避免真实 API 调用"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.llm_service import LLMService


class _MockAsyncStream:
    """Python 3.13 兼容的异步迭代器 mock ——
    MagicMock.__aiter__ 内部调用 iter(ret_val)，但 async generator
    对象无法被 iter() 包装，因此改为手写的异步迭代器类。
    """
    def __init__(self, items: list):
        self._items = items
        self._iter = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


def _mock_openai_stream(content: str):
    """构造一个可被 async for 遍历的假流对象"""
    mock_chunk = MagicMock()
    mock_chunk.choices = [
        MagicMock(delta=MagicMock(content=content))
    ]
    return _MockAsyncStream([mock_chunk])


class TestLLMService:
    """LLM 服务单元测试"""

    @pytest.mark.asyncio
    async def test_chat_stream_yields_tokens(self):
        """验证流式调用能正确逐 token 返回"""
        mock_stream = _mock_openai_stream("Hello")

        # OpenAI AsyncOpenAI 客户端的 create 方法本身是 async 的
        mock_create = AsyncMock(return_value=mock_stream)
        mock_completions = MagicMock()
        mock_completions.create = mock_create
        mock_chat = MagicMock()
        mock_chat.completions = mock_completions
        mock_client = MagicMock()
        mock_client.chat = mock_chat

        service = LLMService()
        service.client = mock_client

        tokens = []
        async for token in service.chat_stream(
            messages=[{"role": "user", "content": "Hi"}]
        ):
            tokens.append(token)

        assert len(tokens) >= 1
        assert "Hello" in tokens
        # 验证 create 被正确调用
        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["stream"] is True

    @pytest.mark.asyncio
    async def test_chat_stream_with_system_prompt(self):
        """验证系统提示词被正确注入"""
        mock_stream = _mock_openai_stream("Got it")
        mock_create = AsyncMock(return_value=mock_stream)
        mock_completions = MagicMock()
        mock_completions.create = mock_create
        mock_chat = MagicMock()
        mock_chat.completions = mock_completions
        mock_client = MagicMock()
        mock_client.chat = mock_chat

        service = LLMService()
        service.client = mock_client

        async for token in service.chat_stream(
            messages=[{"role": "user", "content": "What is RAG?"}],
            system_prompt="You are a helpful assistant.",
        ):
            pass

        call_kwargs = mock_create.call_args[1]
        messages = call_kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are a helpful assistant."
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "What is RAG?"

    @pytest.mark.asyncio
    async def test_chat_non_stream(self):
        """验证非流式调用返回完整内容"""
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="完整回答"))
        ]

        mock_client = MagicMock()
        mock_client.chat = MagicMock()
        mock_client.chat.completions = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        service = LLMService()
        service.client = mock_client

        result = await service.chat(
            messages=[{"role": "user", "content": "Hello"}]
        )

        assert result == "完整回答"
        assert mock_client.chat.completions.create.called