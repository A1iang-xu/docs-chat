<script setup lang="ts">
/**
 * KnowledgeBaseView — 知识库管理页面
 *
 * 功能：
 *  - 查看知识库列表及已入库文档
 *  - 统计卡片（总文档数、总 Chunk 数、知识库数量）
 *  - 搜索 + 状态筛选
 *  - 可折叠的知识库文档分组
 *  - 文档入库弹窗（PDF 上传 / URL 抓取）
 *  - 删除知识库 / 删除文档
 *
 * 数据来源：GET /libraries/  GET /documents/  GET /stats/
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import api from '@/utils/api'
import type { DocumentStatus } from '@/types'

// ═══════════════════════════════════════════
// 类型定义
// ═══════════════════════════════════════════

interface LibraryItem {
  library: string
  version?: string
  chunk_count: number
  source_url?: string
}

interface DocumentItem {
  id: string
  filename: string
  library: string
  status: DocumentStatus
  chunk_count: number
  page_count: number
  created_at: string
  error?: string | null
  job_id?: string
}

interface StatsData {
  total_documents?: number
  total_chunks?: number
  total_libraries?: number
  libraries?: LibraryItem[]
  documents?: DocumentItem[]
}

// ═══════════════════════════════════════════
// 响应式状态
// ═══════════════════════════════════════════

const libraries = ref<LibraryItem[]>([])
const documents = ref<DocumentItem[]>([])
const stats = ref<StatsData | null>(null)
const loading = ref(false)
const error = ref('')

// 搜索和筛选
const searchQuery = ref('')
const statusFilter = ref('全部状态')
const statusSelectOpen = ref(false)

// 折叠状态：记录每个知识库的折叠状态
const collapsedGroups = ref<Record<string, boolean>>({})

// 文档入库弹窗
const ingestModalOpen = ref(false)
const ingestDocName = ref('')
const ingestTargetLibrary = ref('')
const ingestMethod = ref<'pdf' | 'url'>('pdf')
const ingestUrl = ref('')
const ingestFile = ref<File | null>(null)
const ingesting = ref(false)
const ingestError = ref('')

// 新建知识库弹窗
const createKbModalOpen = ref(false)
const createKbName = ref('')
const creatingKb = ref(false)
const createKbError = ref('')

// 模板引用
const fileInput = ref<HTMLInputElement | null>(null)

// 删除中状态
const deletingLibrary = ref<string | null>(null)
const deletingDocument = ref<string | null>(null)

// ═══════════════════════════════════════════
// 计算属性
// ═══════════════════════════════════════════

/** 状态映射：DocumentStatus → 中文标签 */
const statusLabel = (s: DocumentStatus): string => {
  switch (s) {
    case 'ready': return '已就绪'
    case 'processing':
    case 'running':
    case 'queued': return '处理中'
    case 'failed':
    case 'error': return '失败'
    default: return s
  }
}

/** 状态对应的 CSS 类名 */
const statusClass = (s: DocumentStatus): string => {
  switch (s) {
    case 'ready': return 'status-ready'
    case 'processing':
    case 'running':
    case 'queued': return 'status-processing'
    case 'failed':
    case 'error': return 'status-error'
    default: return 'status-ready'
  }
}

/** 统计卡片数据 */
const statCards = computed(() => {
  if (stats.value) {
    return [
      { label: '总文档数', value: stats.value.total_documents ?? documents.value.length, unit: '篇' },
      { label: '总 Chunk 数', value: stats.value.total_chunks ?? 0, unit: '条' },
      { label: '知识库', value: stats.value.total_libraries ?? libraries.value.length, unit: '个' },
    ]
  }
  const totalChunks = documents.value.reduce((sum, d) => sum + (d.chunk_count || 0), 0)
  return [
    { label: '总文档数', value: documents.value.length, unit: '篇' },
    { label: '总 Chunk 数', value: totalChunks, unit: '条' },
    { label: '知识库', value: libraries.value.length, unit: '个' },
  ]
})

/** 按知识库分组的文档（含筛选） */
const groupedDocuments = computed(() => {
  const groups: Record<string, DocumentItem[]> = {}

  for (const doc of documents.value) {
    const lib = doc.library || '未分类'
    if (!groups[lib]) groups[lib] = []
    groups[lib].push(doc)
  }

  // 确保所有已知知识库都在分组中（即使没有文档）
  for (const lib of libraries.value) {
    if (!groups[lib.library]) {
      groups[lib.library] = []
    }
  }

  // 应用搜索和状态筛选
  const result: Record<string, DocumentItem[]> = {}
  for (const [lib, docs] of Object.entries(groups)) {
    const filtered = docs.filter((doc) => {
      const matchesSearch = !searchQuery.value ||
        doc.filename.toLowerCase().includes(searchQuery.value.toLowerCase())
      const matchesStatus = statusFilter.value === '全部状态' ||
        statusLabel(doc.status) === statusFilter.value
      return matchesSearch && matchesStatus
    })
    result[lib] = filtered
  }

  return result
})

/** 知识库分组列表（用于渲染），包含元数据 */
const groupEntries = computed(() => {
  return Object.entries(groupedDocuments.value).map(([lib, docs]) => {
    const libInfo = libraries.value.find((l) => l.library === lib)
    const chunkCount = docs.reduce((sum, d) => sum + (d.chunk_count || 0), 0)
    return {
      name: lib,
      documents: docs,
      chunkCount,
      documentCount: docs.length,
      version: libInfo?.version,
      sourceUrl: libInfo?.source_url,
    }
  })
})

/** 筛选选项 */
const statusOptions = ['全部状态', '已就绪', '处理中', '失败']

// ═══════════════════════════════════════════
// 数据获取
// ═══════════════════════════════════════════

const fetchLibraries = async () => {
  try {
    const { data } = await api.get('/libraries/')
    libraries.value = Array.isArray(data) ? data : []
  } catch {
    libraries.value = []
  }
}

const fetchDocuments = async () => {
  try {
    const { data } = await api.get('/documents/')
    documents.value = Array.isArray(data) ? data : []
  } catch {
    documents.value = []
  }
}

const fetchStats = async () => {
  try {
    const { data } = await api.get('/stats/')
    stats.value = data
  } catch {
    stats.value = null
  }
}

const fetchAll = async () => {
  loading.value = true
  error.value = ''
  try {
    await Promise.all([fetchLibraries(), fetchDocuments(), fetchStats()])
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e.message || '加载数据失败'
  } finally {
    loading.value = false
  }
}

// ═══════════════════════════════════════════
// 知识库操作
// ═══════════════════════════════════════════

const deleteLibrary = async (library: string) => {
  if (!confirm(`确定要删除知识库「${library}」吗？该操作会同时删除库内所有文档，且不可撤销。`)) return
  deletingLibrary.value = library
  try {
    await api.delete(`/libraries/${library}`)
    await fetchAll()
  } catch (e: any) {
    alert(e?.response?.data?.detail || e.message || '删除知识库失败')
  } finally {
    deletingLibrary.value = null
  }
}

const deleteDocument = async (docId: string, filename: string) => {
  if (!confirm(`确定要删除文档「${filename}」吗？此操作不可撤销。`)) return
  deletingDocument.value = docId
  try {
    await api.delete(`/documents/${docId}`)
    await fetchAll()
  } catch (e: any) {
    alert(e?.response?.data?.detail || e.message || '删除文档失败')
  } finally {
    deletingDocument.value = null
  }
}

const showCreateKbForm = () => {
  createKbName.value = ''
  createKbError.value = ''
  createKbModalOpen.value = true
}

const hideCreateKbForm = () => {
  createKbModalOpen.value = false
}

const submitCreateKb = async () => {
  const name = createKbName.value.trim()
  if (!name) {
    createKbError.value = '请输入知识库名称'
    return
  }
  creatingKb.value = true
  createKbError.value = ''
  try {
    await api.post('/libraries/', { library: name })
    hideCreateKbForm()
    await fetchAll()
  } catch (e: any) {
    createKbError.value = e?.response?.data?.detail || e.message || '创建知识库失败'
  } finally {
    creatingKb.value = false
  }
}

// ═══════════════════════════════════════════
// 折叠控制
// ═══════════════════════════════════════════

const toggleGroup = (libName: string) => {
  collapsedGroups.value[libName] = !collapsedGroups.value[libName]
}

// ═══════════════════════════════════════════
// 状态筛选下拉
// ═══════════════════════════════════════════

const toggleStatusSelect = () => {
  statusSelectOpen.value = !statusSelectOpen.value
}

const selectStatus = (option: string) => {
  statusFilter.value = option
  statusSelectOpen.value = false
}

const closeStatusSelect = (e: MouseEvent) => {
  const target = e.target as HTMLElement
  if (!target.closest('.custom-select')) {
    statusSelectOpen.value = false
  }
}

// ═══════════════════════════════════════════
// 文档入库弹窗
// ═══════════════════════════════════════════

const showIngestModal = () => {
  ingestDocName.value = ''
  ingestTargetLibrary.value = libraries.value[0]?.library || ''
  ingestMethod.value = 'pdf'
  ingestUrl.value = ''
  ingestFile.value = null
  ingestError.value = ''
  ingestModalOpen.value = true
}

const hideIngestModal = () => {
  ingestModalOpen.value = false
}

const selectMethod = (method: 'pdf' | 'url') => {
  ingestMethod.value = method
}

const handleFileDrop = (e: DragEvent) => {
  e.preventDefault()
  const file = e.dataTransfer?.files?.[0]
  if (file) {
    ingestFile.value = file
  }
}

const handleFileSelect = (e: Event) => {
  const target = e.target as HTMLInputElement
  const file = target.files?.[0]
  if (file) {
    ingestFile.value = file
  }
}

const startIngest = async () => {
  ingestError.value = ''

  if (!ingestDocName.value.trim()) {
    ingestError.value = '请输入文档名称'
    return
  }
  if (!ingestTargetLibrary.value) {
    ingestError.value = '请选择目标知识库'
    return
  }

  ingesting.value = true
  try {
    if (ingestMethod.value === 'pdf') {
      if (!ingestFile.value) {
        ingestError.value = '请选择要上传的 PDF 文件'
        ingesting.value = false
        return
      }
      const formData = new FormData()
      formData.append('file', ingestFile.value)
      formData.append('filename', ingestDocName.value.trim())
      formData.append('library', ingestTargetLibrary.value)
      await api.post('/documents/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
    } else {
      if (!ingestUrl.value.trim()) {
        ingestError.value = '请输入文档 URL'
        ingesting.value = false
        return
      }
      await api.post('/documents/fetch', {
        filename: ingestDocName.value.trim(),
        library: ingestTargetLibrary.value,
        url: ingestUrl.value.trim(),
      })
    }
    hideIngestModal()
    await fetchAll()
  } catch (e: any) {
    ingestError.value = e?.response?.data?.detail || e.message || '入库失败'
  } finally {
    ingesting.value = false
  }
}

// ═══════════════════════════════════════════
// 工具函数
// ═══════════════════════════════════════════

const formatDate = (val?: string) => {
  if (!val) return '--'
  try {
    const d = new Date(val)
    if (isNaN(d.getTime())) return val
    return d.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return val
  }
}

const formatChunkCount = (doc: DocumentItem): string => {
  if (doc.status === 'ready') return String(doc.chunk_count || 0)
  return '--'
}

const formatPageCount = (doc: DocumentItem): string => {
  if (doc.status === 'ready') return String(doc.page_count || 0)
  return '--'
}

const fileExt = (filename: string): string => {
  const idx = filename.lastIndexOf('.')
  return idx > 0 ? filename.slice(idx) : ''
}

const fileBase = (filename: string): string => {
  const idx = filename.lastIndexOf('.')
  return idx > 0 ? filename.slice(0, idx) : filename
}

// ═══════════════════════════════════════════
// 生命周期
// ═══════════════════════════════════════════

onMounted(() => {
  fetchAll()
  document.addEventListener('click', closeStatusSelect)
})

onUnmounted(() => {
  document.removeEventListener('click', closeStatusSelect)
})
</script>

<template>
  <div class="kb-view">
    <div class="kb-inner">
      <!-- Page Header -->
      <header class="page-header">
        <div class="page-header-text">
          <h1>知识库</h1>
          <p>管理知识库及已入库的文档</p>
        </div>
        <div class="page-header-actions">
          <button class="btn btn-outline" @click="showCreateKbForm">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:16px;height:16px;"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            新建知识库
          </button>
          <button class="btn btn-primary" @click="showIngestModal">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:16px;height:16px;">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="17 8 12 3 7 8"/>
              <line x1="12" y1="3" x2="12" y2="15"/>
            </svg>
            文档入库
          </button>
        </div>
      </header>

      <!-- Stats Cards -->
      <section class="stats-row">
        <div class="stat-card" v-for="card in statCards" :key="card.label">
          <div class="stat-card-label">{{ card.label }}</div>
          <div class="stat-card-value">{{ card.value }} <span>{{ card.unit }}</span></div>
        </div>
      </section>

      <!-- Filter Bar -->
      <div class="kb-filter-bar">
        <div class="kb-filter-left">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:14px;height:14px;color:var(--muted-foreground);"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
          <input
            class="kb-search-input"
            type="text"
            v-model="searchQuery"
            placeholder="搜索文档名称..."
          />
        </div>
        <div class="kb-filter-right">
          <div class="custom-select">
            <button class="custom-select-trigger" @click="toggleStatusSelect">
              <span class="custom-select-value">{{ statusFilter }}</span>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:14px;height:14px;"><path d="m6 9 6 6 6-6"/></svg>
            </button>
            <div class="custom-select-menu" :class="{ open: statusSelectOpen }">
              <div
                v-for="option in statusOptions"
                :key="option"
                class="custom-select-option"
                :class="{ active: statusFilter === option }"
                @click="selectStatus(option)"
              >{{ option }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Loading / Error States -->
      <div v-if="loading" class="kb-state">
        <p>加载中...</p>
      </div>
      <div v-else-if="error" class="kb-state kb-state-error">
        <p>{{ error }}</p>
        <button class="btn btn-outline" @click="fetchAll">重试</button>
      </div>

      <!-- Knowledge Base Document Groups -->
      <div v-else class="kb-doc-groups">
        <div
          v-for="group in groupEntries"
          :key="group.name"
          class="kb-doc-group"
          :class="{ collapsed: collapsedGroups[group.name] }"
        >
          <div class="kb-doc-group-header" @click="toggleGroup(group.name)">
            <div class="kb-doc-group-info">
              <svg class="kb-doc-group-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6"/></svg>
              <span class="kb-doc-group-name">{{ group.name }}</span>
              <span v-if="group.version && group.version !== 'latest'" class="kb-doc-group-version">@{{ group.version }}</span>
              <span class="kb-doc-group-meta">{{ group.documentCount }} 篇文档 · {{ group.chunkCount }} 条 chunks</span>
            </div>
            <div class="kb-doc-group-actions" @click.stop>
              <button
                class="btn btn-ghost btn-sm"
                :disabled="deletingLibrary === group.name"
                @click="deleteLibrary(group.name)"
              >{{ deletingLibrary === group.name ? '删除中...' : '删除知识库' }}</button>
            </div>
          </div>
          <div class="kb-doc-group-body">
            <table class="kb-doc-table" v-if="group.documents.length > 0">
              <thead>
                <tr>
                  <th>文档名</th>
                  <th>状态</th>
                  <th>Chunk 数</th>
                  <th>页数</th>
                  <th>入库时间</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="doc in group.documents" :key="doc.id">
                  <td>
                    <span class="file-name">
                      <svg class="file-name-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/></svg>
                      {{ fileBase(doc.filename) }}<span class="file-name-ext">{{ fileExt(doc.filename) }}</span>
                    </span>
                  </td>
                  <td>
                    <span class="status-pill" :class="statusClass(doc.status)">
                      <span class="dot"></span>{{ statusLabel(doc.status) }}
                    </span>
                  </td>
                  <td class="mono" :class="{ 'muted-cell': doc.status !== 'ready' }">{{ formatChunkCount(doc) }}</td>
                  <td class="mono" :class="{ 'muted-cell': doc.status !== 'ready' }">{{ formatPageCount(doc) }}</td>
                  <td class="date-cell">{{ formatDate(doc.created_at) }}</td>
                  <td>
                    <div class="action-links">
                      <a
                        v-if="doc.status === 'ready'"
                        class="action-link"
                        href="#"
                        @click.prevent
                      >查看</a>
                      <span v-if="doc.status === 'ready'" class="action-divider"></span>
                      <a
                        v-if="doc.status === 'processing' || doc.status === 'running' || doc.status === 'queued'"
                        class="action-link action-link-cancel"
                        href="#"
                        @click.prevent="deleteDocument(doc.id, doc.filename)"
                      >取消</a>
                      <a
                        v-else
                        class="action-link action-link-destructive"
                        href="#"
                        @click.prevent="deleteDocument(doc.id, doc.filename)"
                      >删除</a>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
            <div v-else class="kb-doc-group-empty">
              暂无文档
            </div>
          </div>
        </div>

        <!-- 空状态：没有任何知识库分组 -->
        <div v-if="groupEntries.length === 0" class="kb-state">
          <p>暂无知识库，点击"新建知识库"开始</p>
        </div>
      </div>

      <!-- Document Ingest Modal -->
      <div v-if="ingestModalOpen" class="ingest-modal">
        <div class="ingest-modal-header">
          <h3>文档入库</h3>
          <button class="ingest-modal-close" @click="hideIngestModal">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:16px;height:16px;"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <div class="ingest-modal-body">
          <!-- Step 1: Basic Info -->
          <div class="ingest-step">
            <div class="ingest-field">
              <label class="form-label">文档名称</label>
              <input
                class="form-input"
                type="text"
                v-model="ingestDocName"
                placeholder="例如: vue3-official-guide"
              />
            </div>
            <div class="ingest-field">
              <label class="form-label">目标知识库</label>
              <select class="form-input" v-model="ingestTargetLibrary">
                <option v-for="lib in libraries" :key="lib.library" :value="lib.library">{{ lib.library }}</option>
              </select>
            </div>
            <div class="ingest-field">
              <label class="form-label">入库方式</label>
              <div class="ingest-method-tabs">
                <button
                  class="method-tab"
                  :class="{ active: ingestMethod === 'pdf' }"
                  @click="selectMethod('pdf')"
                >PDF 上传</button>
                <button
                  class="method-tab"
                  :class="{ active: ingestMethod === 'url' }"
                  @click="selectMethod('url')"
                >URL 抓取</button>
              </div>
            </div>
          </div>

          <!-- PDF Upload Area -->
          <div v-if="ingestMethod === 'pdf'" class="ingest-method-content">
            <div
              class="ingest-upload-area"
              @dragover.prevent
              @drop="handleFileDrop"
              @click="fileInput?.click()"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="width:24px;height:24px;color:var(--muted-foreground);">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                <polyline points="17 8 12 3 7 8"/>
                <line x1="12" y1="3" x2="12" y2="15"/>
              </svg>
              <span v-if="ingestFile">已选择: {{ ingestFile.name }}</span>
              <span v-else>拖拽 PDF 文件到此处，或点击选择</span>
              <input
                ref="fileInput"
                type="file"
                accept=".pdf"
                style="display:none"
                @change="handleFileSelect"
              />
            </div>
          </div>

          <!-- URL Fetch Input -->
          <div v-if="ingestMethod === 'url'" class="ingest-method-content">
            <div class="ingest-field">
              <input
                class="form-input"
                type="url"
                v-model="ingestUrl"
                placeholder="https://example.com/docs"
              />
            </div>
          </div>

          <!-- Ingest Pipeline Preview -->
          <div class="ingest-pipeline">
            <div class="ingest-pipeline-title">入库流程预览</div>
            <div class="ingest-pipeline-stages">
              <div class="ingest-stage">
                <div class="ingest-stage-dot completed"></div>
                <span>文档接收</span>
              </div>
              <div class="ingest-stage-line completed"></div>
              <div class="ingest-stage">
                <div class="ingest-stage-dot completed"></div>
                <span>文本提取</span>
              </div>
              <div class="ingest-stage-line active"></div>
              <div class="ingest-stage">
                <div class="ingest-stage-dot active"></div>
                <span>分块处理</span>
              </div>
              <div class="ingest-stage-line pending"></div>
              <div class="ingest-stage">
                <div class="ingest-stage-dot pending"></div>
                <span>向量化</span>
              </div>
              <div class="ingest-stage-line pending"></div>
              <div class="ingest-stage">
                <div class="ingest-stage-dot pending"></div>
                <span>入库完成</span>
              </div>
            </div>
          </div>

          <div v-if="ingestError" class="ingest-error">{{ ingestError }}</div>

          <div class="ingest-modal-actions">
            <button class="btn btn-primary" :disabled="ingesting" @click="startIngest">
              {{ ingesting ? '入库中...' : '开始入库' }}
            </button>
            <button class="btn btn-outline" @click="hideIngestModal">取消</button>
          </div>
        </div>
      </div>

      <!-- Create Knowledge Base Modal -->
      <div v-if="createKbModalOpen" class="ingest-modal">
        <div class="ingest-modal-header">
          <h3>新建知识库</h3>
          <button class="ingest-modal-close" @click="hideCreateKbForm">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:16px;height:16px;"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <div class="ingest-modal-body">
          <div class="ingest-field" style="margin-bottom: 16px;">
            <label class="form-label">知识库名称</label>
            <input
              class="form-input"
              type="text"
              v-model="createKbName"
              placeholder="例如: vue-docs"
              @keyup.enter="submitCreateKb"
            />
          </div>
          <div v-if="createKbError" class="ingest-error">{{ createKbError }}</div>
          <div class="ingest-modal-actions">
            <button class="btn btn-primary" :disabled="creatingKb" @click="submitCreateKb">
              {{ creatingKb ? '创建中...' : '创建' }}
            </button>
            <button class="btn btn-outline" @click="hideCreateKbForm">取消</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ═══════════════════════════════════════════
   KnowledgeBaseView — Scoped Styles
   Based on docs-chat-redesign design system
   ═══════════════════════════════════════════ */

.kb-view {
  flex: 1;
  min-height: 100vh;
  overflow-y: auto;
  background: var(--background);
}

.kb-inner {
  max-width: 1120px;
  margin: 0 auto;
  padding: 32px 40px 60px;
}

/* ---- Page Header ---- */
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 28px;
}

.page-header-text h1 {
  font-size: 22px;
  font-weight: 600;
  color: var(--foreground);
  letter-spacing: -0.012em;
  margin: 0 0 4px;
  font-family: var(--font-sans);
}

.page-header-text p {
  font-size: 13.5px;
  color: var(--muted-foreground);
  margin: 0;
}

.page-header-actions {
  display: flex;
  gap: 10px;
  flex-shrink: 0;
  margin-top: 2px;
}

/* ---- Buttons ---- */
.btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 8px 16px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 500;
  font-family: var(--font-sans);
  cursor: pointer;
  transition: opacity 0.15s;
  border: 1px solid transparent;
  text-decoration: none;
  line-height: 1.4;
  background: none;
  color: inherit;
}

.btn:hover {
  opacity: 0.85;
}

.btn svg {
  width: 15px;
  height: 15px;
}

.btn-primary {
  background: var(--primary);
  color: var(--primary-foreground);
  border-color: var(--primary);
}

.btn-outline {
  background: var(--background);
  color: var(--foreground);
  border-color: var(--border);
}

.btn-outline:hover {
  background: var(--muted);
}

.btn-sm {
  padding: 5px 10px;
  font-size: 12.5px;
}

.btn-ghost {
  background: none;
  border: none;
  color: var(--muted-foreground);
  cursor: pointer;
  padding: 5px 10px;
  font-size: 12px;
  border-radius: var(--radius-sm);
}

.btn-ghost:hover {
  color: var(--destructive);
  background: rgba(220, 38, 38, 0.05);
}

.btn-ghost:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ---- Stats Cards ---- */
.stats-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 28px;
}

.stat-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-top: 2px solid var(--primary);
  border-radius: var(--radius);
  padding: 18px 20px;
}

.stat-card-label {
  font-size: 12.5px;
  color: var(--muted-foreground);
  margin-bottom: 6px;
  font-weight: 450;
}

.stat-card-value {
  font-size: 28px;
  font-weight: 600;
  color: var(--foreground);
  letter-spacing: -0.02em;
  line-height: 1.2;
}

.stat-card-value span {
  font-size: 14px;
  font-weight: 450;
  color: var(--muted-foreground);
  margin-left: 4px;
}

/* ---- Filter Bar ---- */
.kb-filter-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.kb-filter-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}

.kb-search-input {
  flex: 1;
  padding: 7px 12px;
  border: 1px solid var(--input);
  border-radius: var(--radius-sm);
  font-size: 13px;
  background: var(--card);
  color: var(--foreground);
  outline: none;
  max-width: 300px;
  font-family: var(--font-sans);
}

.kb-search-input:focus {
  border-color: var(--foreground);
}

.kb-search-input::placeholder {
  color: var(--muted-foreground);
}

.kb-filter-right {
  flex-shrink: 0;
}

/* ---- Custom Select ---- */
.custom-select {
  position: relative;
}

.custom-select-trigger {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 12px;
  border: 1px solid var(--input);
  border-radius: var(--radius-sm);
  background: var(--card);
  color: var(--foreground);
  font-size: 13px;
  cursor: pointer;
  white-space: nowrap;
  min-width: 100px;
  font-family: var(--font-sans);
}

.custom-select-trigger:hover {
  border-color: var(--foreground);
}

.custom-select-value {
  flex: 1;
}

.custom-select-trigger svg {
  flex-shrink: 0;
  color: var(--muted-foreground);
}

.custom-select-menu {
  display: none;
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  min-width: 120px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  z-index: 50;
  padding: 4px;
}

.custom-select-menu.open {
  display: block;
}

.custom-select-option {
  padding: 6px 10px;
  font-size: 13px;
  color: var(--foreground);
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.1s;
}

.custom-select-option:hover {
  background: var(--muted);
}

.custom-select-option.active {
  background: var(--sidebar-accent);
  font-weight: 500;
}

/* ---- KB Document Groups ---- */
.kb-doc-groups {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 20px;
}

.kb-doc-group {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}

.kb-doc-group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--muted);
  cursor: pointer;
  user-select: none;
  transition: background 0.15s;
}

.kb-doc-group-header:hover {
  background: var(--border);
}

.kb-doc-group-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.kb-doc-group-chevron {
  width: 16px;
  height: 16px;
  color: var(--muted-foreground);
  transition: transform 0.2s ease;
  flex-shrink: 0;
}

.kb-doc-group.collapsed .kb-doc-group-chevron {
  transform: rotate(-90deg);
}

.kb-doc-group-name {
  font-family: var(--font-mono);
  font-weight: 500;
  font-size: 14px;
  color: var(--foreground);
}

.kb-doc-group-version {
  font-size: 11px;
  color: var(--muted-foreground);
  font-family: var(--font-mono);
}

.kb-doc-group-meta {
  font-size: 12px;
  color: var(--muted-foreground);
}

.kb-doc-group-actions {
  flex-shrink: 0;
}

.kb-doc-group-body {
  transition: max-height 0.2s ease;
}

.kb-doc-group.collapsed .kb-doc-group-body {
  display: none;
}

.kb-doc-group-empty {
  padding: 24px;
  text-align: center;
  font-size: 13px;
  color: var(--muted-foreground);
}

/* ---- Doc Table ---- */
.kb-doc-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.kb-doc-table thead th {
  text-align: left;
  padding: 10px 16px;
  font-size: 11px;
  font-weight: 500;
  color: var(--muted-foreground);
  text-transform: uppercase;
  letter-spacing: 0.03em;
  border-bottom: 1px solid var(--border);
  background: var(--card);
}

.kb-doc-table tbody td {
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  color: var(--foreground);
}

.kb-doc-table tbody tr:last-child td {
  border-bottom: none;
}

.kb-doc-table tbody tr:hover {
  background: var(--muted);
}

/* ---- Status Pills ---- */
.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 500;
}

.status-pill .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-ready {
  background: var(--success-subtle);
  color: var(--success-text);
}

.status-ready .dot {
  background: var(--success);
}

.status-processing {
  background: var(--warning-subtle);
  color: var(--warning-text);
}

.status-processing .dot {
  background: var(--warning);
  animation: pulse-dot 1.4s ease-in-out infinite;
}

.status-error {
  background: var(--destructive-subtle);
  color: var(--destructive-text);
}

.status-error .dot {
  background: var(--destructive);
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* ---- Action Links ---- */
.action-links {
  display: flex;
  align-items: center;
  gap: 4px;
}

.action-link {
  font-size: 12.5px;
  color: var(--muted-foreground);
  text-decoration: none;
  cursor: pointer;
  padding: 3px 8px;
  border-radius: var(--radius-sm);
  transition: color 0.15s, background 0.15s;
  font-weight: 450;
}

.action-link:hover {
  color: var(--foreground);
  background: var(--muted);
}

.action-link-destructive:hover {
  color: var(--destructive);
  background: var(--destructive-subtle);
}

.action-divider {
  width: 1px;
  height: 14px;
  background: var(--border);
  margin: 0 2px;
}

.action-link-cancel {
  color: var(--warning);
}

.action-link-cancel:hover {
  color: var(--warning-text);
  background: var(--warning-subtle);
}

/* ---- File Name ---- */
.file-name {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-weight: 500;
  font-size: 13.5px;
}

.file-name-icon {
  width: 16px;
  height: 16px;
  color: var(--muted-foreground);
  flex-shrink: 0;
}

.file-name-ext {
  font-family: var(--font-mono);
  font-size: 11.5px;
  color: var(--muted-foreground);
  margin-left: 2px;
}

/* ---- Monospace / Muted cells ---- */
.mono {
  font-family: var(--font-mono);
  font-size: 13px;
}

.muted-cell {
  color: var(--muted-foreground);
}

.date-cell {
  color: var(--muted-foreground);
  font-size: 13px;
}

/* ---- State Messages ---- */
.kb-state {
  text-align: center;
  padding: 40px;
  color: var(--muted-foreground);
  font-size: 14px;
}

.kb-state-error {
  color: var(--destructive-text);
}

.kb-state-error p {
  margin-bottom: 12px;
}

/* ---- Ingest Modal ---- */
.ingest-modal {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  margin-bottom: 20px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
}

.ingest-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border);
}

.ingest-modal-header h3 {
  font-size: 15px;
  font-weight: 600;
  margin: 0;
  color: var(--foreground);
}

.ingest-modal-close {
  background: none;
  border: none;
  color: var(--muted-foreground);
  cursor: pointer;
  padding: 4px;
  display: flex;
  border-radius: var(--radius-sm);
}

.ingest-modal-close:hover {
  background: var(--muted);
}

.ingest-modal-body {
  padding: 18px;
}

.ingest-step {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
}

.ingest-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1;
  min-width: 180px;
}

.ingest-field .form-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--muted-foreground);
}

.ingest-field .form-input {
  padding: 7px 10px;
  border: 1px solid var(--input);
  border-radius: var(--radius-sm);
  font-size: 13px;
  background: var(--card);
  color: var(--foreground);
  outline: none;
  font-family: var(--font-sans);
}

.ingest-field .form-input:focus {
  border-color: var(--foreground);
}

.ingest-field .form-input::placeholder {
  color: var(--muted-foreground);
}

.ingest-method-tabs {
  display: flex;
  gap: 4px;
}

.method-tab {
  padding: 6px 14px;
  border: 1px solid var(--input);
  border-radius: var(--radius-sm);
  background: var(--card);
  color: var(--muted-foreground);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
  font-family: var(--font-sans);
}

.method-tab.active {
  background: var(--foreground);
  color: var(--background);
  border-color: var(--foreground);
}

/* ---- Upload Area ---- */
.ingest-upload-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 24px;
  border: 2px dashed var(--border);
  border-radius: var(--radius);
  color: var(--muted-foreground);
  font-size: 13px;
  cursor: pointer;
  margin-bottom: 16px;
  transition: border-color 0.15s, background 0.15s;
}

.ingest-upload-area:hover {
  border-color: var(--foreground);
  background: var(--muted);
}

.ingest-method-content {
  margin-bottom: 16px;
}

/* ---- Ingest Pipeline ---- */
.ingest-pipeline {
  padding: 12px 16px;
  background: var(--muted);
  border-radius: var(--radius-sm);
  margin-bottom: 16px;
}

.ingest-pipeline-title {
  font-size: 12px;
  font-weight: 500;
  color: var(--muted-foreground);
  margin-bottom: 10px;
}

.ingest-pipeline-stages {
  display: flex;
  align-items: center;
  gap: 0;
}

.ingest-stage {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.ingest-stage span {
  font-size: 10px;
  color: var(--muted-foreground);
}

.ingest-stage-dot {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 2px solid var(--border);
  background: var(--card);
  flex-shrink: 0;
}

.ingest-stage-dot.completed {
  background: var(--foreground);
  border-color: var(--foreground);
}

.ingest-stage-dot.active {
  background: var(--foreground);
  border-color: var(--foreground);
  animation: ingest-pulse 1.5s ease-in-out infinite;
}

.ingest-stage-dot.pending {
  background: var(--card);
  border-color: var(--border);
}

@keyframes ingest-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(24, 24, 27, 0.3); }
  50% { box-shadow: 0 0 0 4px rgba(24, 24, 27, 0.1); }
}

.ingest-stage-line {
  width: 30px;
  height: 2px;
  background: var(--border);
  flex-shrink: 0;
}

.ingest-stage-line.completed {
  background: var(--foreground);
}

.ingest-stage-line.active {
  background: var(--foreground);
}

/* ---- Ingest Modal Actions ---- */
.ingest-modal-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.ingest-error {
  padding: 8px 12px;
  background: var(--destructive-subtle);
  border: 1px solid var(--destructive-border);
  border-radius: var(--radius-sm);
  color: var(--destructive-text);
  font-size: 13px;
  margin-bottom: 12px;
}

/* ---- Responsive ---- */
@media (max-width: 768px) {
  .kb-inner {
    padding: 20px;
  }

  .stats-row {
    grid-template-columns: 1fr;
  }

  .page-header {
    flex-direction: column;
    gap: 16px;
  }

  .kb-filter-bar {
    flex-direction: column;
  }

  .kb-search-input {
    max-width: 100%;
  }
}
</style>