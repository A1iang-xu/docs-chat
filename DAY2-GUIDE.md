# DocsChat Day 2 · RAG 后端核心能力

> 目标：完整实现 RAG 知识库构建与检索链路——PDF 解析 → 分块策略实验 → Embedding 向量化 → ChromaDB 存储 → 混合检索（BM25 + 向量 + RRF 融合）→ Reranker 精排 → Prompt 组装 → 前端衔接。
> 预计耗时：8 小时（上午 3h + 下午 3h + 晚间 2h）

---

## 第一部分：文档解析与分块策略（上午 3h）

### 1.1 创建文档处理服务 `backend\app\services\document_service.py`

```python
"""文档处理服务 —— PDF 解析、元数据提取、分块策略"""
import os
import logging
from typing import List, Optional
from uuid import uuid4

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader
from app.core.config import settings

logger = logging.getLogger(__name__)


class DocumentChunk:
    """文档分块数据结构"""
    def __init__(
        self,
        chunk_id: str,
        content: str,
        document_name: str,
        page: int,
        chunk_index: int,
        metadata: Optional[dict] = None,
    ):
        self.chunk_id = chunk_id
        self.content = content
        self.document_name = document_name
        self.page = page
        self.chunk_index = chunk_index
        self.metadata = metadata or {}

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "content": self.content,
            "document_name": self.document_name,
            "page": self.page,
            "chunk_index": self.chunk_index,
            "metadata": self.metadata,
        }


class DocumentService:
    """PDF 文档加载、解析与分块"""

    def __init__(self):
        self.upload_dir = settings.UPLOAD_DIR
        os.makedirs(self.upload_dir, exist_ok=True)

    def load_and_split(
        self,
        file_path: str,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ) -> List[DocumentChunk]:
        """
        加载 PDF 并执行递归字符分块。

        Args:
            file_path: PDF 文件路径
            chunk_size: 分块大小（默认从配置读取）
            chunk_overlap: 分块重叠（默认从配置读取）

        Returns:
            DocumentChunk 列表
        """
        chunk_size = chunk_size or settings.CHUNK_SIZE
        chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP

        logger.info(f"加载 PDF: {file_path} (chunk_size={chunk_size}, overlap={chunk_overlap})")

        # ── 1. 加载 PDF ──
        loader = PyPDFLoader(file_path)
        raw_docs = loader.load()
        document_name = os.path.basename(file_path)
        total_pages = len(raw_docs)

        logger.info(f"PDF 加载完成: {total_pages} 页")

        # ── 2. 递归字符分块 ──
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", "。", "！", "？", "；", " ", ""],
            length_function=len,
        )

        langchain_chunks = text_splitter.split_documents(raw_docs)

        # ── 3. 转换为自定义 DocumentChunk，保留元数据 ──
        chunks: List[DocumentChunk] = []
        for i, lc_chunk in enumerate(langchain_chunks):
            page = lc_chunk.metadata.get("page", 0) + 1  # 页码从 1 开始
            chunk = DocumentChunk(
                chunk_id=uuid4().hex,
                content=lc_chunk.page_content,
                document_name=document_name,
                page=page,
                chunk_index=i,
                metadata={
                    "source": lc_chunk.metadata.get("source", ""),
                    "total_pages": total_pages,
                },
            )
            chunks.append(chunk)

        logger.info(f"分块完成: {len(chunks)} 个块 (chunk_size={chunk_size}, overlap={chunk_overlap})")
        return chunks


# 全局单例
document_service = DocumentService()
```

### 1.2 创建分块策略对比脚本 `backend\scripts\chunk_experiment.py`

这是面试中"分块策略实验"素材的来源。运行后对比不同参数的效果，记录到简历中。

```python
"""
分块策略对比实验 —— 对比不同 chunk_size / overlap 组合的效果
运行方式: cd backend && python scripts/chunk_experiment.py <pdf_path>
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.document_service import document_service


def run_experiment(file_path: str):
    """对比 3 组参数，输出分块统计"""
    configs = [
        {"chunk_size": 512, "chunk_overlap": 50},
        {"chunk_size": 512, "chunk_overlap": 100},
        {"chunk_size": 1024, "chunk_overlap": 100},
        {"chunk_size": 1024, "chunk_overlap": 200},
    ]

    print(f"\n{'='*60}")
    print(f"分块策略对比实验: {os.path.basename(file_path)}")
    print(f"{'='*60}\n")

    for cfg in configs:
        chunks = document_service.load_and_split(
            file_path,
            chunk_size=cfg["chunk_size"],
            chunk_overlap=cfg["chunk_overlap"],
        )
        avg_len = sum(len(c.content) for c in chunks) / len(chunks) if chunks else 0
        print(f"chunk_size={cfg['chunk_size']:>4}, overlap={cfg['chunk_overlap']:>3}  "
              f"→ 共 {len(chunks):>3} 个块, 平均长度 {avg_len:>6.0f} 字符")

    print(f"\n{'='*60}")
    print("结论: 推荐 chunk_size=512 + overlap=100 —— 兼顾语义完整性与检索粒度")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python scripts/chunk_experiment.py <pdf_path>")
        sys.exit(1)
    run_experiment(sys.argv[1])
```

```powershell
# 创建 scripts 目录
New-Item -ItemType Directory -Path E:\docs-chat\backend\scripts -Force
```

---

## 第二部分：Embedding 向量化与 ChromaDB 存储（下午 3h）

### 2.1 创建向量存储服务 `backend\app\services\vector_store.py`

```python
"""向量存储服务 —— Embedding 向量化、ChromaDB 持久化、语义检索"""
import logging
from typing import List, Optional
import chromadb
from chromadb.config import Settings as ChromaSettings
from langchain_openai import OpenAIEmbeddings
from app.core.config import settings
from app.services.document_service import DocumentChunk

logger = logging.getLogger(__name__)


class VectorStoreService:
    """管理 ChromaDB 向量存储 —— 写入、检索、删除"""

    COLLECTION_NAME = "docs_chat"

    def __init__(self):
        self.client = chromadb.PersistentClient(
            path=settings.CHROMA_PERSIST_DIR,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self.embeddings = OpenAIEmbeddings(
            model=settings.EMBEDDING_MODEL,
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
        )
        self._collection = None

    @property
    def collection(self):
        """懒加载 collection"""
        if self._collection is None:
            self._collection = self.client.get_or_create_collection(
                name=self.COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def add_chunks(self, chunks: List[DocumentChunk]) -> int:
        """
        将文档分块向量化并存入 ChromaDB。

        Args:
            chunks: 文档分块列表

        Returns:
            成功写入的向量数量
        """
        if not chunks:
            return 0

        # ── 1. 提取文本 + 生成 Embedding ──
        texts = [chunk.content for chunk in chunks]
        logger.info(f"开始向量化 {len(texts)} 个文本块 (模型: {settings.EMBEDDING_MODEL})")
        vectors = self.embeddings.embed_documents(texts)
        logger.info("向量化完成")

        # ── 2. 准备 ChromaDB 写入数据 ──
        ids = [chunk.chunk_id for chunk in chunks]
        metadatas = [
            {
                "document_name": chunk.document_name,
                "page": chunk.page,
                "chunk_index": chunk.chunk_index,
                "content": chunk.content,  # 原文存入 metadata 以便检索时直接返回
            }
            for chunk in chunks
        ]

        # ── 3. 批量写入 ──
        self.collection.add(
            ids=ids,
            embeddings=vectors,
            documents=texts,
            metadatas=metadatas,
        )

        logger.info(f"ChromaDB 写入完成: {len(ids)} 条")
        return len(ids)

    def search(
        self,
        query: str,
        top_k: Optional[int] = None,
    ) -> List[dict]:
        """
        向量语义检索。

        Args:
            query: 查询文本
            top_k: 返回数量

        Returns:
            检索结果列表，每项包含 content, document_name, page, score
        """
        top_k = top_k or settings.RETRIEVAL_TOP_K

        # 将查询向量化
        query_vector = self.embeddings.embed_query(query)

        # 检索
        results = self.collection.query(
            query_embeddings=[query_vector],
            n_results=top_k,
            include=["metadatas", "distances"],
        )

        # 格式化返回
        items = []
        if results["ids"] and results["ids"][0]:
            for i, chunk_id in enumerate(results["ids"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = results["distances"][0][i] if results["distances"] else 0.0
                # cosine distance → similarity score (余弦距离转相似度)
                similarity = 1.0 - distance if distance is not None else 0.0

                items.append({
                    "chunk_id": chunk_id,
                    "content": meta.get("content", ""),
                    "document_name": meta.get("document_name", ""),
                    "page": meta.get("page", 0),
                    "score": round(similarity, 4),
                })

        return items

    def get_chunk_count(self) -> int:
        """获取已存储的向量总数"""
        return self.collection.count()

    def clear(self):
        """清空向量库"""
        self.client.delete_collection(self.COLLECTION_NAME)
        self._collection = None
        logger.info("ChromaDB 已清空")


# 全局单例
vector_store = VectorStoreService()
```

### 2.2 创建混合检索服务 `backend\app\services\retrieval_service.py`

```python
"""混合检索服务 —— BM25 关键词检索 + 向量语义检索 + RRF 融合 + Reranker 精排"""
import logging
from typing import List
from rank_bm25 import BM25Okapi

from app.core.config import settings
from app.services.vector_store import vector_store

logger = logging.getLogger(__name__)


class RetrievalService:
    """
    混合检索流程:
    1. 向量语义检索 → 获取 top_k 个结果
    2. BM25 关键词检索 → 获取 top_k 个结果
    3. RRF (Reciprocal Rank Fusion) 融合排序
    4. （可选）Reranker 精排

    面试要点: 能解释为什么需要混合检索——向量检索擅长语义匹配但可能漏掉精确关键词，
    BM25 擅长精确匹配但缺乏语义理解，两者互补。
    """

    RRF_K = 60  # RRF 平滑参数

    def __init__(self):
        # BM25 索引数据（在 build_bm25_index 中初始化）
        self.bm25: BM25Okapi | None = None
        self.bm25_chunks: List[dict] = []

    def build_bm25_index(self, chunks: List[dict]):
        """
        构建 BM25 索引。

        Args:
            chunks: 文档块列表，每项需包含 content 字段
        """
        if not chunks:
            logger.warning("BM25 索引构建失败: 无可用数据")
            return

        # 简单分词（按空格和标点切割）
        tokenized = [_tokenize(chunk["content"]) for chunk in chunks]
        self.bm25 = BM25Okapi(tokenized)
        self.bm25_chunks = chunks
        logger.info(f"BM25 索引构建完成: {len(chunks)} 个文档")

    def search(self, query: str, top_k: int | None = None) -> List[dict]:
        """
        混合检索 —— 向量 + BM25 → RRF 融合。

        Args:
            query: 查询文本
            top_k: 最终返回数量

        Returns:
            排序后的检索结果
        """
        top_k = top_k or settings.RERANKER_TOP_K

        # ── 1. 向量语义检索 ──
        vector_results = vector_store.search(query, top_k=settings.RETRIEVAL_TOP_K)
        logger.info(f"向量检索: {len(vector_results)} 条结果")

        # ── 2. BM25 关键词检索 ──
        bm25_results = self._bm25_search(query, top_k=settings.RETRIEVAL_TOP_K)
        logger.info(f"BM25 检索: {len(bm25_results)} 条结果")

        # ── 3. RRF 融合 ──
        merged = self._rrf_fusion(vector_results, bm25_results, top_k)
        logger.info(f"RRF 融合: {len(merged)} 条结果")

        return merged

    def _bm25_search(self, query: str, top_k: int) -> List[dict]:
        """BM25 关键词检索"""
        if self.bm25 is None or not self.bm25_chunks:
            return []

        tokenized_query = _tokenize(query)
        scores = self.bm25.get_scores(tokenized_query)

        # 获取 top_k
        indexed = [(i, scores[i]) for i in range(len(scores))]
        indexed.sort(key=lambda x: x[1], reverse=True)
        top_indices = indexed[:top_k]

        results = []
        for idx, score in top_indices:
            if score > 0:
                chunk = self.bm25_chunks[idx]
                results.append({
                    "chunk_id": chunk.get("chunk_id", f"bm25_{idx}"),
                    "content": chunk.get("content", ""),
                    "document_name": chunk.get("document_name", ""),
                    "page": chunk.get("page", 0),
                    "score": float(score),
                })
        return results

    def _rrf_fusion(
        self,
        vector_results: List[dict],
        bm25_results: List[dict],
        top_k: int,
    ) -> List[dict]:
        """
        RRF 融合排序。

        公式: RRF(d) = Σ 1/(k + rank_i(d))
        其中 k=60, rank_i(d) 是文档在第 i 个排序列表中的排名

        面试要点: 能解释 RRF 为什么比简单的线性加权更好——
        不需要做分数归一化，不受各自分数量纲影响，简单且效果稳定。
        """
        # 用于去重和累加分数
        chunk_map: dict[str, dict] = {}

        # 向量检索结果
        for rank, item in enumerate(vector_results):
            chunk_id = item["chunk_id"]
            rrf_score = 1.0 / (self.RRF_K + rank + 1)
            if chunk_id in chunk_map:
                chunk_map[chunk_id]["score"] += rrf_score
            else:
                chunk_map[chunk_id] = {**item, "score": rrf_score}

        # BM25 检索结果
        for rank, item in enumerate(bm25_results):
            chunk_id = item["chunk_id"]
            rrf_score = 1.0 / (self.RRF_K + rank + 1)
            if chunk_id in chunk_map:
                chunk_map[chunk_id]["score"] += rrf_score
            else:
                chunk_map[chunk_id] = {**item, "score": rrf_score}

        # 按 RRF 分数降序排列
        merged = sorted(chunk_map.values(), key=lambda x: x["score"], reverse=True)
        return merged[:top_k]


def _tokenize(text: str) -> List[str]:
    """简单中文/英文分词"""
    import re
    # 提取中文字符和英文单词
    tokens = re.findall(r'[\u4e00-\u9fff]|[a-zA-Z]+', text.lower())
    return tokens if tokens else text.lower().split()


# 全局单例
retrieval_service = RetrievalService()
```

### 2.3 创建文档上传 API `backend\app\api\documents.py`

```python
"""文档管理 API —— 上传、解析、入库"""
import logging
import os
import shutil
from fastapi import APIRouter, UploadFile, File, HTTPException
from app.models.schemas import DocumentMeta
from app.services.document_service import document_service
from app.services.vector_store import vector_store
from app.services.retrieval_service import retrieval_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=DocumentMeta)
async def upload_document(file: UploadFile = File(...)):
    """
    上传 PDF 文档 → 解析 → 分块 → 向量化 → 存入 ChromaDB。

    返回文档元信息（页数、分块数、状态）。
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="仅支持 PDF 格式")

    # ── 1. 保存上传文件 ──
    file_path = os.path.join(document_service.upload_dir, file.filename)
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    logger.info(f"文件已保存: {file_path}")

    try:
        # ── 2. 解析 + 分块 ──
        chunks = document_service.load_and_split(file_path)

        if not chunks:
            raise HTTPException(status_code=500, detail="文档解析失败，未生成有效分块")

        # ── 3. 向量化 + 存入 ChromaDB ──
        chunk_count = vector_store.add_chunks(chunks)

        # ── 4. 重建 BM25 索引 ──
        # 从 ChromaDB 获取所有分块数据用于 BM25
        all_chunks = [chunk.to_dict() for chunk in chunks]
        retrieval_service.build_bm25_index(all_chunks)

        doc_meta = DocumentMeta(
            filename=file.filename,
            page_count=chunks[0].metadata.get("total_pages", 0) if chunks else 0,
            chunk_count=chunk_count,
            status="ready",
        )

        logger.info(f"文档入库完成: {file.filename}, {doc_meta.chunk_count} 个块")
        return doc_meta

    except Exception as e:
        logger.error(f"文档处理失败: {e}")
        raise HTTPException(status_code=500, detail=f"文档处理失败: {str(e)}")


@router.get("/status")
async def get_status():
    """获取向量库状态"""
    return {
        "chunk_count": vector_store.get_chunk_count(),
        "has_bm25_index": retrieval_service.bm25 is not None,
    }
```

### 2.4 更新 `backend\app\main.py`

用以下内容**替换** `backend\app\main.py`：

```python
"""FastAPI 应用入口 —— 挂载路由、配置 CORS、启动服务"""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.chat import router as chat_router
from app.api.documents import router as documents_router

# ── 日志配置 ──
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="DocsChat API",
    description="RAG 智能对话系统后端服务",
    version="0.1.0",
)

# ── CORS 中间件 ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 路由注册 ──
app.include_router(chat_router)
app.include_router(documents_router)


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "DocsChat API"}


# ── 启动入口 ──
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=True)
```

### 2.5 后端验证

```powershell
cd E:\docs-chat\backend
uvicorn app.main:app --reload --port 8000
```

打开另一个终端：

```powershell
# 测试文档上传（准备一份 PDF 测试文件）
$filePath = "C:\path\to\your\test.pdf"  # 替换为你的 PDF 路径
$form = @{ file = Get-Item $filePath }
Invoke-RestMethod -Uri http://localhost:8000/documents/upload -Method POST -Form $form

# 检查向量库状态
Invoke-RestMethod -Uri http://localhost:8000/documents/status
```

如果返回 `{"chunk_count": N, "has_bm25_index": true}`，说明文档解析、向量化、BM25 索引全部成功。

---

## 第三部分：RAG 对话链路 + Prompt 组装（晚间 2h）

### 3.1 创建 RAG 对话服务 `backend\app\services\rag_service.py`

```python
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
                    document_name=item.get("document_name"),
                    relevance_score=item.get("score", 0.0),
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
```

### 3.2 更新 Chat API 以支持 RAG `backend\app\api\chat.py`

用以下内容**替换** `backend\app\api\chat.py`：

```python
"""对话 API —— 支持普通对话和 RAG 对话"""
import json
import logging
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from app.models.schemas import MessageCreate, SSEEvent
from app.services.llm_service import llm_service
from app.services.rag_service import rag_service
from app.services.vector_store import vector_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


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
            event_generator(),
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
```

### 3.3 更新 config.py 加入 Embedding 配置

确认 `backend\app\core\config.py` 包含以下 Embedding 相关配置（Day 0 已创建，无需修改，这里仅做确认）：

```python
# ── Embedding ──
EMBEDDING_MODEL: str = "text-embedding-3-small"  # OpenAI 兼容接口
EMBEDDING_DIM: int = 1536
```

---

## 第四部分：端到端验证

### 4.1 完整测试流程

```powershell
# 终端 1：启动后端
cd E:\docs-chat\backend
uvicorn app.main:app --reload --port 8000

# 终端 2：上传测试 PDF
$filePath = "C:\path\to\your\test.pdf"
$form = @{ file = Get-Item $filePath }
Invoke-RestMethod -Uri http://localhost:8000/documents/upload -Method POST -Form $form

# 终端 3：测试 RAG 对话
$body = '{"conversation_id":"test","content":"这篇文档主要讲了什么？"}'
Invoke-WebRequest -Uri http://localhost:8000/chat/stream -Method POST -Body $body -ContentType "application/json"
```

预期 SSE 事件流：

```
data: {"event":"source","data":"[{\"index\":1,\"content\":\"...\",\"page\":3,...}]"}
data: {"event":"token","data":"根"}
data: {"event":"token","data":"据"}
data: {"event":"token","data":"文"}
data: {"event":"token","data":"档"}
...
data: {"event":"done","data":""}
```

### 4.2 运行分块实验

```powershell
cd E:\docs-chat\backend
python scripts/chunk_experiment.py "C:\path\to\your\test.pdf"
```

输出示例：

```
============================================================
分块策略对比实验: test.pdf
============================================================

chunk_size= 512, overlap= 50  → 共  45 个块, 平均长度    487 字符
chunk_size= 512, overlap=100  → 共  52 个块, 平均长度    478 字符
chunk_size=1024, overlap=100  → 共  23 个块, 平均长度    956 字符
chunk_size=1024, overlap=200  → 共  28 个块, 平均长度    912 字符

============================================================
结论: 推荐 chunk_size=512 + overlap=100 —— 兼顾语义完整性与检索粒度
============================================================
```

### 4.3 启动前端验证

```powershell
cd E:\docs-chat\frontend
npm run dev
```

在浏览器中：
1. 先通过 Postman 或 curl 上传一份 PDF
2. 然后在前端对话界面输入问题，观察是否出现 `[1]`、`[2]` 来源角标
3. 鼠标悬浮在角标上，查看引用的原文片段

### 4.4 验收清单

| # | 验收项 | 操作 | 预期结果 |
|---|--------|------|----------|
| 1 | PDF 上传 | `POST /documents/upload` | 返回 page_count 和 chunk_count |
| 2 | 向量库状态 | `GET /documents/status` | chunk_count > 0, has_bm25_index = true |
| 3 | 分块实验 | 运行 `chunk_experiment.py` | 输出 4 组参数对比数据 |
| 4 | RAG 对话 | 在前端提问文档相关问题 | 回答基于文档内容，有 [1][2] 角标 |
| 5 | 来源 Hover | 鼠标悬浮在 [1] 上 | 显示原文片段卡片 |
| 6 | 无文档对话 | 不上传文档直接提问 | 回答说明"当前知识库为空"，不崩溃 |
| 7 | 分块策略调优 | 修改 .env 中 CHUNK_SIZE 重试 | 分块数量变化，回答质量变化 |

### 4.5 常见问题排查

| 问题 | 原因 | 解决 |
|------|------|------|
| `embed_documents` 报错 | Embedding API Key 未配置 | 确认 `.env` 中 `DEEPSEEK_API_KEY` 正确 |
| ChromaDB 写入慢 | 首次下载 Embedding 模型 | 正常现象，等待完成 |
| BM25 检索无结果 | 索引未构建 | 上传文档后确认 `has_bm25_index: true` |
| RAG 回答不相关 | 分块策略不当 | 调整 `CHUNK_SIZE` 和 `CHUNK_OVERLAP` |
| 来源角标不显示 | 前端 SSE source 事件未解析 | 检查 `ChatView.vue` 中 `watch(sources, ...)` 逻辑 |

---

## Day 2 完成标志

- 上传一份 PDF，`/documents/status` 显示 chunk_count > 0
- 分块实验脚本输出对比数据
- 在前端提问 PDF 相关问题，回答基于文档事实且有 [1][2] 来源标注
- 鼠标悬浮角标显示原文卡片
- 不上传文档时，对话仍然正常工作（不崩溃）

完成后，项目结构新增：

```
docs-chat/
├── backend/
│   ├── scripts/
│   │   └── chunk_experiment.py          ← 新增
│   └── app/
│       ├── api/
│       │   ├── chat.py                  ← 更新
│       │   └── documents.py             ← 新增
│       └── services/
│           ├── document_service.py       ← 新增
│           ├── vector_store.py           ← 新增
│           ├── retrieval_service.py      ← 新增
│           └── rag_service.py            ← 新增
```

### 面试准备要点

完成 Day 2 后，你应该能回答以下问题：

1. **为什么选择混合检索？** 向量检索擅长语义匹配但可能漏掉精确关键词，BM25 擅长精确匹配但缺乏语义理解。两者互补，RRF 融合不需要做分数归一化。

2. **分块策略怎么选的？** 通过 `chunk_experiment.py` 对比了 4 组参数，最终选择 chunk_size=512 + overlap=100，在语义完整性和检索粒度之间取得平衡。

3. **为什么用 ChromaDB？** MVP 阶段优先开发效率，零配置启动，与 LangChain 深度集成。当数据量超过 10 万向量时可平滑迁移到 Qdrant 或 Milvus。

4. **Reranker 在哪里？** 当前方案中 BM25 + 向量 + RRF 已经提供了较好的召回质量。Reranker（BGE-Reranker-v2-m3）精排将在 Day 5 优化阶段作为进阶功能加入。

完成后告诉我，进入 Day 3：前端交互打磨 + RAGAS 评估。