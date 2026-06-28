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
  // v4.0: URL 引用溯源
  /** 来源 URL（可点击跳转回原文） */
  sourceUrl?: string
  /** 标题路径（如 "Guide > Reactivity"） */
  headingPath?: string
  /** 所属文档库 */
  library?: string
  /** 文档版本 */
  version?: string
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
  conversation_id: string
  content: string
  library?: string | null
  history?: Array<{ role: MessageRole; content: string }>  // v4.1: 多轮对话历史
}

// ═══════════════════════════════════════════
// 文档
// ═══════════════════════════════════════════

export type DocumentStatus = 'queued' | 'running' | 'processing' | 'ready' | 'failed' | 'error'

export interface DocumentMeta {
  id: string
  filename: string
  pageCount: number
  chunkCount: number
  uploadedAt: string
  status: DocumentStatus
  error?: string | null
  jobId?: string
}

export interface DocumentJob {
  job_id: string
  filename: string
  status: 'queued' | 'running' | 'ready' | 'failed'
  page_count: number
  chunk_count: number
  error?: string | null
  created_at: string
  updated_at: string
}

// ═══════════════════════════════════════════
// SSE 事件
// ═══════════════════════════════════════════

export type SSEEventType = 'token' | 'source' | 'done' | 'error' | 'cache' | 'faithfulness_warning' | 'stage' | 'replace'

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

// ═══════════════════════════════════════════
// RAGAS 评估
// ═══════════════════════════════════════════

export interface EvaluationResult {
  avg_faithfulness?: number
  avg_context_precision?: number
  avg_context_recall?: number
  avg_answer_relevancy?: number
  avg_keyword_coverage?: number
  faithfulness?: number
  context_precision?: number
  context_recall?: number
  answer_relevancy?: number
  keyword_coverage?: number
  dataset_size?: number
  total_evaluated?: number
  total_errors?: number
  created_at?: string
  timestamp?: string
  library?: string
  status?: string
}

export interface PerItem {
  query: string
  status: string
  current_stage: string
  stages_completed: string[]
  error?: string | null
}

export interface EvalProgress {
  current: number
  total: number
  current_query: string
  per_item: PerItem[]
  status?: string
}

export interface DatasetItem {
  query: string
  expected_keywords: string[]
  source_doc?: string
}

export interface GenerateDatasetResponse {
  total_queries: number
  dataset: DatasetItem[]
}

export interface HistoryResponse {
  history: EvaluationResult[]
}
