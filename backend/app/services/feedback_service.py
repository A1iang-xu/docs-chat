"""v4.0: 反馈存储服务 —— 用户对答案的 👍/👎 反馈落库 + 统计"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)


class FeedbackService:
    """反馈存储：JSONL 文件追加（免外部数据库依赖）。"""

    def __init__(self) -> None:
        self._path = settings.PROJECT_ROOT / "feedback.jsonl"
        self._lock = __import__("threading").Lock()

    # ── public ──

    async def record(
        self,
        message_id: str,
        query: str,
        answer: str,
        sources: list[dict],
        feedback: str,
    ) -> None:
        """记录一条用户反馈。feedback ∈ {"positive", "negative"}"""
        entry = {
            "message_id": message_id,
            "query": query[:500],
            "answer": answer[:2000],
            "sources": sources[:10],
            "feedback": feedback,
            "timestamp": datetime.now().isoformat(),
        }
        import asyncio
        await asyncio.to_thread(self._write_entry, entry)
        logger.info("反馈已记录: %s %s", message_id[:12], feedback)

    def get_stats(self) -> dict:
        """统计正负反馈分布。"""
        total = 0
        positive = 0
        negative = 0

        if self._path.exists():
            with open(self._path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        total += 1
                        if entry.get("feedback") == "positive":
                            positive += 1
                        elif entry.get("feedback") == "negative":
                            negative += 1
                    except json.JSONDecodeError:
                        continue
        return {
            "total": total,
            "positive": positive,
            "negative": negative,
            "positive_rate": round(positive / max(total, 1), 3),
        }

    # ── internal ──

    def _write_entry(self, entry: dict) -> None:
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# 全局单例
feedback_service = FeedbackService()
