<script setup lang="ts">
import { ref } from 'vue'
import api from '@/utils/api'
import type { DocumentMeta } from '@/types'

const emit = defineEmits<{
  uploaded: [doc: DocumentMeta]
}>()

const isUploading = ref(false)
const error = ref<string | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)

async function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  if (!file.name.toLowerCase().endsWith('.pdf')) {
    error.value = '仅支持 PDF 文件'
    return
  }

  isUploading.value = true
  error.value = null

  try {
    const formData = new FormData()
    formData.append('file', file)

    const { data } = await api.post<DocumentMeta>('/documents/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120_000, // 大文件上传可能需要较长时间
    })

    emit('uploaded', data)
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
</script>

<template>
  <div class="uploader">
    <input
      ref="fileInput"
      type="file"
      accept=".pdf"
      style="display:none"
      @change="handleFileChange"
    />

    <button
      class="upload-btn"
      :disabled="isUploading"
      @click="triggerUpload"
    >
      {{ isUploading ? '上传中...' : '上传 PDF' }}
    </button>

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

.upload-btn {
  padding: 0.45rem 1rem;
  background: var(--bg2);
  color: var(--accent);
  border: 1px solid var(--rule);
  border-radius: 6px;
  font-size: 0.85rem;
  cursor: pointer;
  transition: background 0.2s;
}

.upload-btn:hover:not(:disabled) {
  background: var(--rule);
}

.upload-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.upload-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.4rem 0.65rem;
  background: rgba(248, 81, 73, 0.1);
  border: 1px solid var(--danger);
  border-radius: 6px;
  color: var(--danger);
  font-size: 0.8rem;
}

.dismiss-btn {
  background: none;
  border: none;
  color: var(--danger);
  font-weight: 600;
  cursor: pointer;
  font-size: 0.8rem;
}
</style>