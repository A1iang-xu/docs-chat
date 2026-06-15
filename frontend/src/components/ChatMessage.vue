<script setup lang="ts">
import { computed } from 'vue'
import type { Message } from '@/types'

const props = defineProps<{
  message: Message
}>()

const isUser = computed(() => props.message.role === 'user')
const isAssistant = computed(() => props.message.role === 'assistant')
</script>

<template>
  <div class="message" :class="{ user: isUser, assistant: isAssistant }">
    <div class="role-label">{{ isUser ? '你' : 'DocsChat' }}</div>
    <div class="content">
      <div class="text" v-text="message.content"></div>

      <!-- 引用来源 -->
      <div v-if="message.sources.length > 0" class="sources">
        <span class="sources-label">参考来源：</span>
        <span
          v-for="source in message.sources"
          :key="source.index"
          class="source-badge"
          :title="source.content"
        >
          [{{ source.index }}]
          <span class="source-tooltip">{{ source.content }}</span>
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.message {
  display: flex;
  flex-direction: column;
  padding: 0.75rem 1.5rem;
  max-width: 100%;
}

.message.user {
  background: var(--bg);
}

.message.assistant {
  background: var(--bg2);
}

.role-label {
  font-size: 0.8rem;
  font-weight: 700;
  color: var(--muted);
  margin-bottom: 0.3rem;
}

.content {
  line-height: 1.7;
}

.text {
  white-space: pre-wrap;
  word-break: break-word;
}

/* 来源引用 */
.sources {
  margin-top: 0.75rem;
  padding-top: 0.5rem;
  border-top: 1px solid var(--rule);
  font-size: 0.8rem;
  color: var(--muted);
}

.sources-label {
  margin-right: 0.25rem;
}

.source-badge {
  display: inline-block;
  position: relative;
  color: var(--accent);
  font-weight: 600;
  cursor: pointer;
  margin-right: 0.35rem;
}

.source-badge .source-tooltip {
  display: none;
  position: absolute;
  bottom: 120%;
  left: 50%;
  transform: translateX(-50%);
  width: 280px;
  padding: 0.5rem 0.75rem;
  background: var(--bg);
  border: 1px solid var(--rule);
  border-radius: 6px;
  font-size: 0.78rem;
  font-weight: 400;
  color: var(--ink);
  white-space: normal;
  word-break: break-word;
  z-index: 10;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

.source-badge:hover .source-tooltip {
  display: block;
}
</style>