<script setup lang="ts">
import { onUnmounted, ref } from 'vue'
import api from '@/utils/api'
import type { DocumentJob, DocumentMeta } from '@/types'
import { useLibraryStore } from '@/stores/libraryStore'

const emit = defineEmits<{
  uploaded: [doc: DocumentMeta]
}>()

const isUploading = ref(false)
const error = ref<string | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const timers = new Set<ReturnType<typeof setTimeout>>()
const libraryStore = useLibraryStore()

// v4.5: URL 导入状态
const showUrlImport = ref(false)
const urlInput = ref('')
const urlLibrarySlug = ref('')
const urlVersion = ref('latest')
const isImportingUrl = ref(false)
const urlImportResult = ref<string | null>(null)

// v4.5: 支持的文件格式
const ALLOWED_EXTENSIONS = ['.pdf', '.txt', '.md', '.html', '.json']

function isAllowedFile(filename: string): boolean {
  const lower = filename.toLowerCase()
  return ALLOWED_EXTENSIONS.some((ext) => lower.endsWith(ext))
}

async function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  if (!isAllowedFile(file.name)) {
    error.value = `仅支持以下格式: ${ALLOWED_EXTENSIONS.join(', ')}`
    return
  }

  isUploading.value = true
  error.value = null

  try {
    const formData = new FormData()
    formData.append('file', file)

    // v4.5: 传入选中的 library，使文档入对应库
    const uploadUrl = libraryStore.selectedLibrary
      ? `/documents/upload?library=${encodeURIComponent(libraryStore.selectedLibrary)}`
      : '/documents/upload'

    const { data } = await api.post<DocumentJob>(uploadUrl, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 60_000,
    })

    const doc = mapJobToDocument(data)
    emit('uploaded', doc)
    pollJob(data.job_id)
  } catch (e: unknown) {
    const msg = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
      || (e as Error).message
      || '上传失败'
    error.value = msg
  } finally {
    isUploading.value = false
    // 重置 input 以支持重复上传同一文件
    if (fileInput.value) fileInput.value.value = ''
  }
}

function triggerUpload() {
  fileInput.value?.click()
}

async function pollJob(jobId: string) {
  try {
    const { data } = await api.get<DocumentJob>(`/documents/jobs/${jobId}`)
    emit('uploaded', mapJobToDocument(data))

    if (data.status === 'queued' || data.status === 'running') {
      const timer = setTimeout(() => {
        timers.delete(timer)
        pollJob(jobId)
      }, 1500)
      timers.add(timer)
    }
  } catch (e: unknown) {
    error.value = (e as Error).message || '获取解析状态失败'
  }
}

// v4.5: URL 导入功能
async function handleUrlImport() {
  if (!urlInput.value.trim()) {
    error.value = '请输入有效的 URL'
    return
  }

  const slug = urlLibrarySlug.value.trim() || libraryStore.selectedLibrary || 'default'
  isImportingUrl.value = true
  error.value = null
  urlImportResult.value = null

  try {
    const { data } = await api.post('/libraries/ingest-url', {
      url: urlInput.value.trim(),
      library_slug: slug,
      version: urlVersion.value.trim() || 'latest',
    }, {
      timeout: 300_000, // URL 抓取可能较慢
    })

    urlImportResult.value = `导入任务已创建 (Job ID: ${data.job_id || 'unknown'})`

    // 轮询 URL 导入任务状态
    if (data.job_id) {
      pollUrlJob(data.job_id)
    }

    // 导入完成后刷新库列表
    libraryStore.fetchLibraries()

    // 清空输入
    urlInput.value = ''
  } catch (e: unknown) {
    const msg = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
      || (e as Error).message
      || 'URL 导入失败'
    error.value = msg
  } finally {
    isImportingUrl.value = false
  }
}

async function pollUrlJob(jobId: string) {
  try {
    const { data } = await api.get(`/libraries/ingest-jobs/${jobId}`)

    if (data.status === 'ready') {
      urlImportResult.value = `导入完成: ${data.chunk_count || 0} 个分块`
      libraryStore.fetchLibraries()
    } else if (data.status === 'failed') {
      urlImportResult.value = `导入失败: ${data.error || '未知错误'}`
    } else if (data.status === 'running' || data.status === 'queued') {
      urlImportResult.value = `导入中... (${data.status})`
      const timer = setTimeout(() => {
        timers.delete(timer)
        pollUrlJob(jobId)
      }, 3000)
      timers.add(timer)
    }
  } catch (e: unknown) {
    error.value = (e as Error).message || '获取导入状态失败'
  }
}

function toggleUrlImport() {
  showUrlImport.value = !showUrlImport.value
  if (!showUrlImport.value) {
    urlImportResult.value = null
    error.value = null
  }
}

function mapJobToDocument(job: DocumentJob): DocumentMeta {
  return {
    id: job.job_id,
    jobId: job.job_id,
    filename: job.filename,
    pageCount: job.page_count || 0,
    chunkCount: job.chunk_count || 0,
    uploadedAt: job.created_at,
    status: job.status === 'failed' ? 'error' : job.status,
    error: job.error || null,
  }
}

onUnmounted(() => {
  for (const timer of timers) clearTimeout(timer)
  timers.clear()
})
</script>

<template>
  <div class="uploader">
    <input
      ref="fileInput"
      type="file"
      :accept="ALLOWED_EXTENSIONS.join(',')"
      style="display:none"
      @change="handleFileChange"
    />

    <div class="upload-buttons">
      <button
        class="upload-btn"
        :disabled="isUploading"
        @click="triggerUpload"
      >
        {{ isUploading ? '上传中...' : '上传文档' }}
      </button>

      <button
        class="url-import-btn"
        :class="{ active: showUrlImport }"
        @click="toggleUrlImport"
        title="从 URL 导入文档站"
      >
        {{ showUrlImport ? '收起' : 'URL 导入' }}
      </button>
    </div>

    <!-- URL 导入面板 -->
    <div v-if="showUrlImport" class="url-import-panel">
      <div class="form-row">
        <input
          v-model="urlInput"
          type="url"
          placeholder="https://docs.example.com/"
          class="url-input"
          @keyup.enter="handleUrlImport"
        />
      </div>
      <div class="form-row compact">
        <input
          v-model="urlLibrarySlug"
          type="text"
          placeholder="库标识 (如: vue-docs)"
          class="slug-input"
        />
        <input
          v-model="urlVersion"
          type="text"
          placeholder="版本"
          class="version-input"
        />
        <button
          class="import-btn"
          :disabled="isImportingUrl"
          @click="handleUrlImport"
        >
          {{ isImportingUrl ? '导入中...' : '开始导入' }}
        </button>
      </div>
      <div v-if="urlImportResult" class="import-result">
        {{ urlImportResult }}
      </div>
    </div>

    <div v-if="error" class="upload-error">
      {{ error }}
      <button class="dismiss-btn" @click="error = null">关闭</button>
    </div>
  </div>
</template>

<style scoped>
.uploader {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.upload-buttons {
  display: flex;
  gap: 0.4rem;
}

.upload-btn {
  padding: 0.45rem 1rem;
  background: var(--muted);
  color: var(--primary);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 0.85rem;
  cursor: pointer;
  transition: background 0.2s;
  white-space: nowrap;
}

.upload-btn:hover:not(:disabled) {
  background: var(--border);
}

.upload-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.url-import-btn {
  padding: 0.45rem 0.75rem;
  background: var(--muted);
  color: var(--muted-foreground);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 0.85rem;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.url-import-btn:hover {
  border-color: var(--primary);
  color: var(--primary);
}

.url-import-btn.active {
  background: var(--primary);
  color: var(--primary-foreground);
  border-color: var(--primary);
}

.url-import-panel {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.75rem;
  background: var(--muted);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  max-width: 400px;
}

.form-row {
  display: flex;
  gap: 0.4rem;
}

.form-row.compact {
  align-items: center;
}

.url-input,
.slug-input,
.version-input {
  flex: 1;
  padding: 0.4rem 0.6rem;
  background: var(--background);
  color: var(--foreground);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 0.82rem;
}

.url-input:focus,
.slug-input:focus,
.version-input:focus {
  outline: none;
  border-color: var(--primary);
}

.slug-input {
  max-width: 140px;
}

.version-input {
  max-width: 80px;
}

.import-btn {
  padding: 0.4rem 0.8rem;
  background: var(--primary);
  color: var(--primary-foreground);
  border: none;
  border-radius: var(--radius-sm);
  font-size: 0.82rem;
  cursor: pointer;
  white-space: nowrap;
  transition: opacity 0.2s;
}

.import-btn:hover:not(:disabled) {
  opacity: 0.9;
}

.import-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.import-result {
  font-size: 0.8rem;
  color: var(--success-text);
  padding: 0.3rem 0.5rem;
  background: var(--success-subtle);
  border-radius: var(--radius-sm);
}

.upload-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.4rem 0.65rem;
  background: var(--destructive-subtle);
  border: 1px solid var(--destructive-border);
  border-radius: var(--radius-sm);
  color: var(--destructive-text);
  font-size: 0.8rem;
  max-width: 400px;
}

.dismiss-btn {
  background: none;
  border: none;
  color: var(--destructive-text);
  font-weight: 600;
  cursor: pointer;
  font-size: 0.8rem;
}
</style>
