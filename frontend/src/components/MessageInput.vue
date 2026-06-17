<script setup lang="ts">
import { ref } from 'vue'

const emit = defineEmits<{
  send: [content: string]
}>()

const input = ref('')
const isSending = defineModel<boolean>('isSending', { default: false })

function handleSend() {
  const content = input.value.trim()
  if (!content || isSending.value) return
  emit('send', content)
  input.value = ''
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    handleSend()
  }
  if (event.key === 'Escape') {
    // 聚焦状态下按 Escape 取消输入
    (event.target as HTMLTextAreaElement).blur()
  }
}
</script>

<template>
  <div class="input-area">
    <textarea
      v-model="input"
      class="input-box"
      :disabled="isSending"
      placeholder="输入消息，Enter 发送，Shift+Enter 换行"
      rows="1"
      aria-label="输入消息"
      role="textbox"
      @keydown="handleKeydown"
      @input="(e) => {
        const el = e.target as HTMLTextAreaElement
        el.style.height = 'auto'
        el.style.height = el.scrollHeight + 'px'
      }"
    ></textarea>
    <button
      class="send-btn"
      :disabled="!input.trim() || isSending"
      :aria-disabled="isSending || !input.trim()"
      aria-label="发送消息"

      @click="handleSend"
    >
      {{ isSending ? '发送中...' : '发送' }}
    </button>
  </div>
</template>

<style scoped>
.input-area {
  display: flex;
  align-items: flex-end;
  gap: 0.75rem;
  padding: 1rem 1.5rem;
  border-top: 1px solid var(--rule);
  background: var(--bg);
}

.input-box {
  flex: 1;
  padding: 0.7rem 0.85rem;
  background: var(--bg2);
  border: 1px solid var(--rule);
  border-radius: 8px;
  color: var(--ink);
  font-size: 0.9rem;
  font-family: inherit;
  resize: none;
  max-height: 200px;
  line-height: 1.5;
  outline: none;
  transition: border-color 0.2s;
}

.input-box:focus {
  border-color: var(--accent);
}

.input-box:disabled {
  opacity: 0.5;
}

.send-btn {
  padding: 0.7rem 1.25rem;
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.2s;
  white-space: nowrap;
}

.send-btn:hover:not(:disabled) {
  opacity: 0.85;
}

.send-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>