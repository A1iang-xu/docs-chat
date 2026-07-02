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

import asyncio

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


class GenerateDatasetRequest(BaseModel):
    """v4.5: 自动生成评估数据集请求"""
    library: Optional[str] = None       # 指定文档库（None 则全库采样）
    num_queries: int = 10               # 生成问题数量


class EvalResponse(BaseModel):
    """评估响应模型"""
    status: str
    total_queries: int
    total_evaluated: int
    total_errors: int
    avg_scores: dict


@router.post("/generate-dataset")
async def generate_dataset(request: GenerateDatasetRequest):
    """v4.5: 根据已有知识库内容自动生成评估数据集。

    从向量库中采样 chunks，用 LLM 为每个 chunk 生成测试问题和期望关键词。
    生成后保存为 eval_dataset.json，可直接用于 POST /evaluation/run。
    """
    if not settings.EVALUATION_ENABLED:
        raise HTTPException(status_code=403, detail="评估功能未启用")

    try:
        dataset = await evaluation_service.generate_dataset_from_knowledge_base(
            library=request.library,
            num_queries=request.num_queries,
        )
        return {
            "status": "completed",
            "total_queries": len(dataset),
            "message": f"已生成 {len(dataset)} 条评估查询",
            "dataset": dataset,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("数据集生成失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"数据集生成失败: {exc}")


@router.post("/run")
async def run_evaluation(request: EvalRequest):
    """v4.5: 触发评估任务，在后台异步执行，API 立即返回。

    评估在后台运行，不阻塞事件循环。前端通过 GET /evaluation/latest 轮询结果。
    """
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

    logger.info("启动后台评估: %d 条查询, library=%s", len(dataset), request.library)

    # v4.5: 在当前事件循环中创建后台任务，不阻塞响应返回
    async def _run_in_background():
        try:
            await evaluation_service.evaluate_dataset(
                dataset, library=request.library,
            )
            logger.info("后台评估完成")
        except Exception as exc:
            logger.error("后台评估失败: %s", exc, exc_info=True)

    asyncio.create_task(_run_in_background())

    return {
        "status": "running",
        "total_queries": len(dataset),
        "message": "评估已在后台启动，请通过 GET /evaluation/latest 查看结果",
    }


@router.get("/latest")
async def get_latest_report():
    """获取最新的评估报告。无数据时返回 200 + null，避免前端拦截器打印错误。"""
    report = evaluation_service.get_latest_report()
    if report is None:
        return {"status": "empty", "message": "暂无评估报告，请先运行评估"}
    return report


@router.get("/progress")
async def get_progress():
    """获取当前评估进度，包含每个查询的 RAG 阶段信息。"""
    progress = evaluation_service.get_progress()
    if progress is None:
        return {"status": "idle", "message": "暂无运行中的评估任务"}
    return progress


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
                "avg_context_precision": report.get("avg_context_precision", 0),
                "avg_context_recall": report.get("avg_context_recall", 0),
                "avg_answer_relevancy": report.get("avg_answer_relevancy", 0),
                "avg_keyword_coverage": report.get("avg_keyword_coverage", 0),
                "library": report.get("library"),
            })
        except Exception:
            continue

    return {"history": history}


@router.delete("/history")
async def clear_evaluation_history():
    """清空所有评估历史记录。"""
    results_dir = evaluation_service.results_dir
    if not results_dir.exists():
        return {"status": "ok", "deleted": 0}

    deleted = 0
    for f in os.listdir(results_dir):
        if f.endswith(".json"):
            try:
                (results_dir / f).unlink()
                deleted += 1
            except Exception:
                pass

    logger.info("评估历史已清空: %d 个文件", deleted)
    return {"status": "ok", "deleted": deleted}
