"""对话 API —— 支持普通对话和 RAG 对话"""
import asyncio
import json
import logging
from typing import AsyncGenerator
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from app.models.schemas import MessageCreate, SSEEvent
from app.services.llm_service import llm_service
from app.services.rag_service import rag_service
from app.services.vector_store import vector_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


async def _with_heartbeat(generator: AsyncGenerator, interval: int = 10):
    """
    包装异步生成器，在等待期间定期发送 SSE 心跳注释。
    防止 CDN / 代理 / 前端因长时间无数据而断开连接。
    """
    gen = generator.__aiter__()
    task: asyncio.Task | None = None
    while True:
        if task is None:
            task = asyncio.ensure_future(gen.__anext__())
        done, _ = await asyncio.wait([task], timeout=interval)
        if task in done:
            try:
                yield task.result()
                task = None
            except StopAsyncIteration:
                break
        else:
            yield ": heartbeat\n\n"


@router.post("/stream")
async def chat_stream(body: MessageCreate, rag: bool = Query(default=True)):
    """
    SSE 流式对话端点。

    Args:
        body: 消息内容
        rag: 是否启用 RAG 检索（默认开启）

    SSE 事件格式：
        data: {"event":"token","data":"文本片段"}
        data: {"event":"source","data":"[{\"index\":1,\"content\":\"...\"}]"}
        data: {"event":"done","data":""}
        data: {"event":"error","data":"错误信息"}
    """
    try:
        async def event_generator():
            try:
                # 立即发送启动心跳，告知前端连接已建立
                yield ": heartbeat\n\n"

                if rag and vector_store.get_chunk_count() > 0:
                    # ── RAG 模式 ──
                    async for chunk in rag_service.chat_stream(query=body.content):
                        if chunk["type"] == "source":
                            event = SSEEvent(event="source", data=chunk["data"])
                            yield f"data: {event.model_dump_json()}\n\n"
                        elif chunk["type"] == "token":
                            event = SSEEvent(event="token", data=chunk["data"])
                            yield f"data: {event.model_dump_json()}\n\n"
                        elif chunk["type"] == "done":
                            done_event = SSEEvent(event="done", data="")
                            yield f"data: {done_event.model_dump_json()}\n\n"
                else:
                    # ── 普通对话模式（无知识库时） ──
                    messages = [{"role": "user", "content": body.content}]
                    async for token in llm_service.chat_stream(messages):
                        event = SSEEvent(event="token", data=token)
                        yield f"data: {event.model_dump_json()}\n\n"

                    done_event = SSEEvent(event="done", data="")
                    yield f"data: {done_event.model_dump_json()}\n\n"

            except Exception as e:
                logger.error(f"流式对话异常: {e}")
                error_event = SSEEvent(event="error", data=str(e))
                yield f"data: {error_event.model_dump_json()}\n\n"

        return StreamingResponse(
            _with_heartbeat(event_generator(), interval=10),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    except Exception as e:
        logger.error(f"对话请求失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))