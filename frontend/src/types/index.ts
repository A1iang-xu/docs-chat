/**
 * DocsChat 全局类型定义
 * 覆盖对话、消息、文档、SSE 事件等核心领域模型
 */

// ═══════════════════════════════════════════
// 对话会话
// ═══════════════════════════════════════════

export interface Conversation {
  id: string
  title: string
  createdAt: string
  updatedAt: string
}

export interface ConversationCreate {
  title: string
}

// ═══════════════════════════════════════════
// 消息
// ═══════════════════════════════════════════

export type MessageRole = 'user' | 'assistant' | 'system'

export interface SourceCitation {
  /** 角标编号 [1], [2], ... */
  index: number
  /** 原文片段 */
  content: string
  /** 页码 */
  page?: number
  /** 文档名称 */
  documentName?: string
  /** 相关性分数 */
  relevanceScore: number
}

export interface Message {
  id: string
  conversationId: string
  role: MessageRole
  content: string
  sources: SourceCitation[]
  createdAt: string
}

export interface MessageCreate {
  conversationId: string
  content: string
}

// ═══════════════════════════════════════════
// 文档
// ═══════════════════════════════════════════

export type DocumentStatus = 'processing' | 'ready' | 'error'

export interface DocumentMeta {
  id: string
  filename: string
  pageCount: number
  chunkCount: number
  uploadedAt: string
  status: DocumentStatus
}

// ═══════════════════════════════════════════
// SSE 事件
// ═══════════════════════════════════════════

export type SSEEventType = 'token' | 'source' | 'done' | 'error'

export interface SSEEvent {
  event: SSEEventType
  data: string
}

export interface StreamState {
  content: string
  sources: SourceCitation[]
  isStreaming: boolean
  error: string | null
}

// ═══════════════════════════════════════════
// 通用响应
// ═══════════════════════════════════════════

export interface ApiError {
  detail: string
  code: string
}

// ═══════════════════════════════════════════
// Store 状态
// ═══════════════════════════════════════════

export interface ConversationsState {
  conversations: Conversation[]
  activeId: string | null
  loading: boolean
}

export interface MessagesState {
  messages: Record<string, Message[]>
  streamState: Record<string, StreamState>
  loading: boolean
}