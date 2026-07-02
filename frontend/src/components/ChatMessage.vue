<script setup lang="ts">
import type { ChatMessage } from '@/types'

const props = defineProps<{
  message: ChatMessage
  isStreaming?: boolean
}>()
</script>

<template>
  <div
    class="chat-message"
    :class="[message.role, { streaming: isStreaming }]"
  >
    <!-- Avatar -->
    <div class="msg-avatar">
      <template v-if="message.role === 'user'">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/>
          <circle cx="12" cy="7" r="4"/>
        </svg>
      </template>
      <template v-else>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Z"/>
          <path d="M12 16v-4M12 8h.01"/>
        </svg>
      </template>
    </div>

    <!-- Content -->
    <div class="msg-body">
      <div class="msg-role-name">
        {{ message.role === 'user' ? '你' : 'DocsChat' }}
      </div>
      <div class="msg-content markdown-body" v-html="message.content" />
    </div>
  </div>
</template>

<style scoped>
.chat-message {
  display: flex;
  gap: 0.75rem;
  padding: 1rem 0;
  max-width: 768px;
  margin: 0 auto;
  width: 100%;
}

.chat-message.assistant {
  flex-direction: row;
}

.chat-message.user {
  flex-direction: row-reverse;
}

.msg-avatar {
  width: 32px;
  height: 32px;
  min-width: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.chat-message.user .msg-avatar {
  background: var(--primary);
  color: var(--primary-foreground);
}

.chat-message.assistant .msg-avatar {
  background: var(--muted);
  color: var(--muted-foreground);
  border: 1px solid var(--border);
}

.msg-avatar svg {
  width: 16px;
  height: 16px;
}

.msg-body {
  min-width: 0;
  flex: 1;
}

.chat-message.user .msg-body {
  text-align: right;
}

.msg-role-name {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--muted-foreground);
  margin-bottom: 0.25rem;
}

.msg-content {
  font-size: 0.9rem;
  line-height: 1.65;
  color: var(--foreground);
  word-break: break-word;
}

/* Markdown-like styling inside message content */
.msg-content :deep(p) {
  margin: 0 0 0.5rem;
}

.msg-content :deep(p:last-child) {
  margin-bottom: 0;
}

.msg-content :deep(pre) {
  background: var(--muted);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 0.75rem;
  overflow-x: auto;
  font-size: 0.82rem;
  line-height: 1.5;
  margin: 0.5rem 0;
}

.msg-content :deep(code) {
  font-family: var(--font-mono);
  font-size: 0.82rem;
  background: var(--muted);
  padding: 0.1em 0.35em;
  border-radius: 3px;
  border: 1px solid var(--border);
}

.msg-content :deep(pre code) {
  background: none;
  padding: 0;
  border: none;
  font-size: inherit;
}

.msg-content :deep(ul),
.msg-content :deep(ol) {
  padding-left: 1.25rem;
  margin: 0.25rem 0;
}

.msg-content :deep(li) {
  margin: 0.125rem 0;
}

.msg-content :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 0.5rem 0;
  font-size: 0.85rem;
}

.msg-content :deep(th),
.msg-content :deep(td) {
  border: 1px solid var(--border);
  padding: 0.4rem 0.6rem;
  text-align: left;
}

.msg-content :deep(th) {
  background: var(--muted);
  font-weight: 600;
}

.msg-content :deep(blockquote) {
  border-left: 3px solid var(--primary);
  padding-left: 0.75rem;
  color: var(--muted-foreground);
  margin: 0.5rem 0;
}

.msg-content :deep(hr) {
  border: none;
  border-top: 1px solid var(--border);
  margin: 0.75rem 0;
}

.msg-content :deep(a) {
  color: var(--primary);
  text-decoration: underline;
  text-underline-offset: 2px;
}

/* Source citations */
.msg-content :deep(.source-citation) {
  display: inline-block;
  background: var(--muted);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 0.1em 0.4em;
  font-size: 0.78rem;
  color: var(--muted-foreground);
  cursor: default;
  vertical-align: middle;
}

/* Streaming animation */
.chat-message.streaming .msg-content::after {
  content: '▍';
  animation: blink 1s step-end infinite;
  color: var(--primary);
  font-weight: 400;
}

@keyframes blink {
  50% { opacity: 0; }
}
</style>