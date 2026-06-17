"""SSE 聊天端点测试"""
import pytest
import json
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch, MagicMock


class _MockAsyncStream:
    """Python 3.13 兼容的异步迭代器 mock"""
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


@pytest.mark.asyncio
async def test_chat_stream_returns_sse_format(client: AsyncClient):
    """验证 SSE 端点返回 data: 前缀格式"""
    mock_stream = _mock_openai_stream("您好")

    # 构造完整的 mock 链: client.chat.completions.create
    mock_create = AsyncMock(return_value=mock_stream)
    mock_completions = MagicMock()
    mock_completions.create = mock_create
    mock_chat = MagicMock()
    mock_chat.completions = mock_completions
    mock_openai = MagicMock()
    mock_openai.chat = mock_chat

    with patch("app.services.llm_service.llm_service.client", mock_openai):
        response = await client.post(
            "/chat/stream",
            json={
                "conversation_id": "test-conv-1",
                "content": "你好",
            },
        )

        assert response.status_code == 200
        body = response.text

        # SSE 响应应包含 "data:" 前缀
        assert "data:" in body

        # 应包含 done 事件
        assert "done" in body


@pytest.mark.asyncio
async def test_chat_stream_empty_content_rejected(client: AsyncClient):
    """验证空消息被拒绝"""
    response = await client.post(
        "/chat/stream",
        json={
            "conversation_id": "test-conv-1",
            "content": "",
        },
    )

    assert response.status_code == 422