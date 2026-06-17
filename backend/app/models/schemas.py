"""Pydantic 数据模型 —— 定义 API 请求/响应、对话、文档等核心数据结构"""
from pydantic import BaseModel, Field
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
    conversation_id: str
    content: str = Field(..., min_length=1, max_length=10000)


class SourceCitation(BaseModel):
    """检索到的来源引用（字段名与前端 TypeScript 接口对齐）"""
    index: int
    content: str
    page: Optional[int] = None
    documentName: Optional[str] = None
    relevanceScore: float = 0.0


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
    status: Literal["processing", "ready", "error"] = "processing"


# ═══════════════════════════════════════════
# SSE 事件
# ═══════════════════════════════════════════

class SSEEvent(BaseModel):
    """SSE 流式响应的单次事件"""
    event: Literal["token", "source", "done", "error"]
    data: str


# ═══════════════════════════════════════════
# 通用响应
# ═══════════════════════════════════════════

class ErrorResponse(BaseModel):
    detail: str
    code: str = "internal_error"