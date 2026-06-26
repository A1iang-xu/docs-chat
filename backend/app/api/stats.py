"""v4.0: 可观测指标 API"""
from fastapi import APIRouter

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/")
async def get_stats():
    """返回实时管线指标（P50/P95 延迟、缓存命中率等）。"""
    from app.services.metrics_service import metrics_service
    return metrics_service.get_stats()
