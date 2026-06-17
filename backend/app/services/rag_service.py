"""RAG 对话服务 —— 检索 → Prompt 组装 → LLM 生成"""
import logging
import json
from typing import AsyncGenerator, List, Optional

from app.core.config import settings
from app.services.vector_store import vector_store
from app.services.retrieval_service import retrieval_service
from app.services.llm_service import llm_service
from app.models.schemas import SourceCitation

logger = logging.getLogger(__name__)


class RAGService:
    """
    RAG 全链路：
    1. 混合检索 → 获取相关文档片段
    2. 组装 Prompt（System Prompt + 检索上下文 + 历史对话 + 用户问题）
    3. 调用 LLM 流式生成
    4. 返回 SourceCitation 供前端标注来源
    """

    SYSTEM_PROMPT = """你是一个基于知识库的智能问答助手。请根据以下规则回答问题：

1. 优先使用下方提供的【参考文档】来回答问题，确保回答基于文档事实
2. 如果【参考文档】中没有相关信息，请明确说明"根据已有文档，我无法回答这个问题"
3. 回答时请在关键信息后标注引用来源，格式为 [1]、[2] 等
4. 回答应清晰、简洁、有条理
5. 不要编造文档中没有的信息"""

    async def chat_stream(
        self,
        query: str,
        history: Optional[List[dict]] = None,
    ) -> AsyncGenerator[dict, None]:
        """
        流式 RAG 对话。

        Args:
            query: 用户问题
            history: 历史对话 [{"role": "user", "content": "..."}, ...]

        Yields:
            {"type": "source", "data": [SourceCitation, ...]}
            {"type": "token", "data": "文本片段"}
            {"type": "done", "data": ""}
        """
        # ── 1. 混合检索 ──
        retrieval_results = retrieval_service.search(query)

        if retrieval_results:
            # 构建 SourceCitation 列表
            sources = []
            contexts = []
            for i, item in enumerate(retrieval_results):
                sources.append(SourceCitation(
                    index=i + 1,
                    content=item["content"][:300],  # 截断展示
                    page=item.get("page"),
                    documentName=item.get("document_name"),
                    relevanceScore=item.get("score", 0.0),
                ))
                contexts.append(f"[{i + 1}] (来源: {item.get('document_name', '未知')}, "
                               f"第{item.get('page', '?')}页)\n{item['content']}")

            # 先发送来源信息
            sources_json = json.dumps([s.model_dump() for s in sources], ensure_ascii=False)
            yield {"type": "source", "data": sources_json}

            # 构建检索上下文
            context_text = "\n\n---\n\n".join(contexts)
        else:
            yield {"type": "source", "data": json.dumps([])}
            context_text = "（暂无参考文档，请基于通用知识回答，并告知用户当前知识库为空）"

        # ── 2. 组装 Prompt ──
        system_prompt = self.SYSTEM_PROMPT

        user_prompt = f"""【参考文档】
{context_text}

【用户问题】
{query}

请基于以上参考文档回答问题，并在关键信息后标注引用来源（如 [1], [2]）。"""

        # ── 3. 构建完整消息列表 ──
        messages = []
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_prompt})

        # ── 4. LLM 流式生成 ──
        async for token in llm_service.chat_stream(
            messages=messages,
            system_prompt=system_prompt,
        ):
            yield {"type": "token", "data": token}

        yield {"type": "done", "data": ""}


# 全局单例
rag_service = RAGService()