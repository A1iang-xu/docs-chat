"""v4.0: 用户反馈 API —— 提交反馈 + 获取统计"""
from fastapi import APIRouter

from app.models.schemas import FeedbackRequest

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("/")
async def submit_feedback(request: FeedbackRequest):
    """记录用户对答案的反馈（positive / negative）。"""
    from app.services.feedback_service import feedback_service

    await feedback_service.record(
        message_id=request.message_id,
        query=request.query,
        answer=request.answer,
        sources=request.sources,
        feedback=request.feedback,
    )
    return {"status": "ok"}


@router.get("/stats")
async def get_feedback_stats():
    """反馈统计（总计 / 好评 / 差评 / 好评率）。"""
    from app.services.feedback_service import feedback_service
    return feedback_service.get_stats()
