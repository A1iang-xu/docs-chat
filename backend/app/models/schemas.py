"""Pydantic 数据模型 —— 定义 API 请求/响应、对话、文档等核心数据结构"""
from pydantic import BaseModel, Field, field_validator
from typing import Literal, Optional
from datetime import datetime
from uuid import uuid4


# ═══════════════════════════════════════════
# 对话会话
# ═══════════════════════════════════════════

class ConversationCreate(BaseModel):
    title: str = Field(default="新对话", max_length=100)


class Conversation(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    title: str
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


# ═══════════════════════════════════════════
# 消息
# ═══════════════════════════════════════════

class MessageCreate(BaseModel):
    conversation_id: str = ""  # v4.5: 改为可选，避免前端未传时 422
    content: str = Field(..., min_length=1, max_length=10000)
    library: Optional[str] = None  # v4.0: 库过滤
    history: list[dict] = Field(default_factory=list)  # v4.1: 多轮对话历史


class SourceCitation(BaseModel):
    """检索到的来源引用（字段名与前端 TypeScript 接口对齐）"""
    index: int
    content: str
    page: Optional[int] = None
    documentName: Optional[str] = None
    relevanceScore: float = 0.0
    # v4.0: URL 引用溯源
    sourceUrl: Optional[str] = None
    headingPath: Optional[str] = None
    library: Optional[str] = None
    version: Optional[str] = None


class Message(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    conversation_id: str
    role: Literal["user", "assistant", "system"]
    content: str
    sources: list[SourceCitation] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)


# ═══════════════════════════════════════════
# 文档
# ═══════════════════════════════════════════

class DocumentMeta(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    filename: str
    page_count: int = 0
    chunk_count: int = 0
    uploaded_at: datetime = Field(default_factory=datetime.now)
    status: Literal["queued", "running", "processing", "ready", "failed", "error"] = "processing"
    error: Optional[str] = None


class DocumentJob(BaseModel):
    """异步文档摄取任务状态"""
    job_id: str
    filename: str
    status: Literal["queued", "running", "ready", "failed"]
    page_count: int = 0
    chunk_count: int = 0
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# ═══════════════════════════════════════════
# SSE 事件
# ═══════════════════════════════════════════

class SSEEvent(BaseModel):
    """SSE 流式响应的单次事件"""
    event: Literal["token", "source", "done", "error", "cache", "faithfulness_warning", "stage"]
    data: str


# ═══════════════════════════════════════════
# 通用响应
# ═══════════════════════════════════════════

class ErrorResponse(BaseModel):
    detail: str
    code: str = "internal_error"


# ═══════════════════════════════════════════
# v4.0: URL 摄取 & 多库
# ═══════════════════════════════════════════

class IngestUrlRequest(BaseModel):
    """提交文档站 URL 抓取入库请求"""
    url: str
    library_slug: str = Field(..., pattern=r"^[a-z0-9-]+$")
    version: str = "latest"

    @field_validator("library_slug", mode="before")
    @classmethod
    def normalize_slug(cls, v: str) -> str:
        return v.lower().strip()


class LibraryInfo(BaseModel):
    """文档库信息"""
    library: str
    version: str
    chunk_count: int
    source_url: Optional[str] = None


# ═══════════════════════════════════════════
# v4.0: 用户反馈
# ═══════════════════════════════════════════

class FeedbackRequest(BaseModel):
    """用户对答案的反馈"""
    message_id: str = Field(..., min_length=1)
    query: str = Field(default="")  # v4.5: 允许空（前端可能未持久化原始查询）
    answer: str = Field(..., min_length=1)
    sources: list[dict] = Field(default_factory=list)
    feedback: Literal["positive", "negative"]
