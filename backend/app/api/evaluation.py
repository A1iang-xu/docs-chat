"""v4.3: 评估 API 路由 —— RAGAS 风格的 LLM-as-Judge 离线评估

端点:
- POST /evaluation/run   触发评估任务（同步等待结果）
- GET  /evaluation/latest 获取最新评估报告
- GET  /evaluation/history  获取评估历史列表
"""
import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.services.evaluation_service import evaluation_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


class EvalRequest(BaseModel):
    """评估请求模型"""
    dataset_path: Optional[str] = None  # 自定义数据集路径（相对于 PROJECT_ROOT）
    library: Optional[str] = None       # 指定评估的文档库


class EvalResponse(BaseModel):
    """评估响应模型"""
    status: str
    total_queries: int
    total_evaluated: int
    total_errors: int
    avg_scores: dict


@router.post("/run", response_model=EvalResponse)
async def run_evaluation(request: EvalRequest):
    """触发评估任务，同步返回结果。"""
    if not settings.EVALUATION_ENABLED:
        raise HTTPException(status_code=403, detail="评估功能未启用 (EVALUATION_ENABLED=False)")

    # 解析数据集路径
    dataset_path = request.dataset_path or settings.EVALUATION_DATASET_PATH
    if os.path.isabs(dataset_path):
        full_path = dataset_path
    else:
        full_path = os.path.join(str(settings.PROJECT_ROOT), dataset_path)

    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail=f"评估数据集不存在: {full_path}")

    try:
        with open(full_path, "r", encoding="utf-8") as f:
            dataset = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        raise HTTPException(status_code=400, detail=f"数据集解析失败: {exc}")

    if not isinstance(dataset, list) or len(dataset) == 0:
        raise HTTPException(status_code=400, detail="数据集必须是非空列表")

    logger.info("启动评估: %d 条查询, library=%s", len(dataset), request.library)

    try:
        report = await evaluation_service.evaluate_dataset(dataset, library=request.library)
    except Exception as exc:
        logger.error("评估失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"评估失败: {exc}")

    # 提取汇总指标
    avg_scores = {
        k: v for k, v in report.items()
        if k.startswith("avg_")
    }

    return EvalResponse(
        status="completed",
        total_queries=report.get("dataset_size", len(dataset)),
        total_evaluated=report.get("total_evaluated", 0),
        total_errors=report.get("total_errors", 0),
        avg_scores=avg_scores,
    )


@router.get("/latest")
async def get_latest_report():
    """获取最新的评估报告。无数据时返回 200 + null，避免前端拦截器打印错误。"""
    report = evaluation_service.get_latest_report()
    if report is None:
        return {"status": "empty", "message": "暂无评估报告，请先运行评估"}
    return report


@router.get("/history")
async def get_evaluation_history():
    """获取评估历史列表（最近 20 条）。"""
    results_dir = evaluation_service.results_dir
    if not results_dir.exists():
        return {"history": []}

    report_files = sorted(
        [f for f in os.listdir(results_dir) if f.endswith(".json") and f != "latest.json"],
        reverse=True,
    )

    history = []
    for filename in report_files[:20]:
        filepath = results_dir / filename
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                report = json.load(f)
            history.append({
                "filename": filename,
                "timestamp": report.get("timestamp", ""),
                "dataset_size": report.get("dataset_size", 0),
                "total_evaluated": report.get("total_evaluated", 0),
                "total_errors": report.get("total_errors", 0),
                "avg_faithfulness": report.get("avg_faithfulness", 0),
                "avg_answer_relevancy": report.get("avg_answer_relevancy", 0),
                "library": report.get("library"),
            })
        except Exception:
            continue

    return {"history": history}
