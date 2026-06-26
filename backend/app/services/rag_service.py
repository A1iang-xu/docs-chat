"""RAG 对话服务兼容入口。

实际编排逻辑位于 rag_orchestrator，保留 rag_service 单例以兼容现有导入。
"""
from __future__ import annotations

from typing import AsyncGenerator, List, Optional

from app.services.rag_orchestrator import rag_orchestrator


class RAGService:
    async def chat_stream(
        self,
        query: str,
        history: Optional[List[dict]] = None,
        user_id: str = "anonymous",
        library: Optional[str] = None,  # v4.0
    ) -> AsyncGenerator[dict, None]:
        async for chunk in rag_orchestrator.chat_stream(
            query=query, history=history, user_id=user_id, library=library
        ):
            yield chunk


rag_service = RAGService()
