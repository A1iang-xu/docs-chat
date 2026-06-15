"""对话 API —— SSE 流式端点"""
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from app.models.schemas import MessageCreate, SSEEvent
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/stream")
async def chat_stream(body: MessageCreate):
    """
    SSE 流式对话端点。

    前端通过 EventSource 或 fetch + ReadableStream 消费此端点。
    事件格式：
        data: {"event":"token","data":"你"}
        data: {"event":"token","data":"好"}
        data: {"event":"source","data":"[{\"index\":1,\"content\":\"...\"}]"}
        data: {"event":"done","data":""}
        data: {"event":"error","data":"错误信息"}
    """
    try:
        messages = [{"role": "user", "content": body.content}]

        async def event_generator():
            try:
                async for token in llm_service.chat_stream(messages):
                    event = SSEEvent(event="token", data=token)
                    yield f"data: {event.model_dump_json()}\n\n"

                # 发送完成信号
                done_event = SSEEvent(event="done", data="")
                yield f"data: {done_event.model_dump_json()}\n\n"

            except Exception as e:
                logger.error(f"流式对话异常: {e}")
                error_event = SSEEvent(event="error", data=str(e))
                yield f"data: {error_event.model_dump_json()}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
            },
        )

    except Exception as e:
        logger.error(f"对话请求失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))