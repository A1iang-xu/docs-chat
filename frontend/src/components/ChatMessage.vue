<script setup lang="ts">
import { computed, ref } from 'vue'
import { useMarkdown } from '@/composables/useMarkdown'
import type { Message } from '@/types'

const props = defineProps<{
  message: Message
}>()

const { render } = useMarkdown()

const isUser = computed(() => props.message.role === 'user')
const isAssistant = computed(() => props.message.role === 'assistant')

const renderedContent = computed(() => {
  return isAssistant.value ? render(props.message.content) : props.message.content
})

// 用户消息通过 v-text 渲染，v-text 内部设置 textContent，
// 天然具备 XSS 防护（浏览器不会将 textContent 解析为 HTML），
// 无需额外 escapeHtml，避免与 v-text 的双重转义。
const displayContent = computed(() => {
  if (isAssistant.value) {
    return renderedContent.value
  }
  return props.message.content
})
</script>

<template>
  <div class="message" :class="{ user: isUser, assistant: isAssistant }">
    <div class="role-label">{{ isUser ? '你' : 'DocsChat' }}</div>
    <div class="content">
      <!-- 用户消息：纯文本 -->
      <div v-if="isUser" class="text" v-text="displayContent"></div>

      <!-- AI 消息：Markdown 渲染 -->
      <div
        v-else
        class="text markdown-body"
        v-html="displayContent"
      ></div>

      <!-- 引用来源 -->
      <div v-if="message.sources.length > 0" class="sources">
        <span class="sources-label">参考来源：</span>
        <span
          v-for="source in message.sources"
          :key="source.index"
          class="source-badge"
        >
          [{{ source.index }}]
          <span class="source-tooltip">
            <div class="tooltip-header">
              {{ source.documentName || '未知文档' }}
              <span v-if="source.page">· 第 {{ source.page }} 页</span>
            </div>
            <div class="tooltip-body">{{ source.content }}</div>
            <div class="tooltip-score">相关度: {{ (source.relevanceScore * 100).toFixed(1) }}%</div>
          </span>
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.message {
  display: flex;
  flex-direction: column;
  padding: 1rem 1.5rem;
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
  margin-bottom: 0.4rem;
}

.content {
  line-height: 1.75;
}

.text {
  white-space: pre-wrap;
  word-break: break-word;
}

/* ── Markdown 渲染样式 ── */
.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3) {
  margin: 1rem 0 0.5rem;
  font-weight: 700;
  color: var(--ink);
}

.markdown-body :deep(h1) { font-size: 1.3rem; }
.markdown-body :deep(h2) { font-size: 1.15rem; border-bottom: 1px solid var(--rule); padding-bottom: 0.25rem; }
.markdown-body :deep(h3) { font-size: 1.05rem; }

.markdown-body :deep(p) {
  margin: 0.5rem 0;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 1.5rem;
  margin: 0.5rem 0;
}

.markdown-body :deep(li) {
  margin: 0.25rem 0;
}

.markdown-body :deep(blockquote) {
  border-left: 3px solid var(--accent);
  padding: 0.25rem 1rem;
  margin: 0.75rem 0;
  color: var(--muted);
  background: rgba(88, 166, 255, 0.05);
  border-radius: 0 4px 4px 0;
}

.markdown-body :deep(table) {
  border-collapse: collapse;
  margin: 0.75rem 0;
  font-size: 0.85rem;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid var(--rule);
  padding: 0.4rem 0.75rem;
  text-align: left;
}

.markdown-body :deep(th) {
  background: var(--bg);
  font-weight: 600;
}

.markdown-body :deep(strong) {
  font-weight: 700;
  color: var(--ink);
}

.markdown-body :deep(a) {
  color: var(--accent);
  text-decoration: none;
}

.markdown-body :deep(a:hover) {
  text-decoration: underline;
}

/* ── 行内代码 ── */
:deep(.inline-code) {
  background: rgba(88, 166, 255, 0.1);
  color: var(--accent);
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 0.88em;
  font-family: 'Consolas', 'Courier New', monospace;
}

/* ── 代码块容器（含语言标签 + 复制按钮） ── */
:deep(.code-block-wrapper) {
  position: relative;
  margin: 0.75rem 0 1rem;
}

:deep(.code-lang-label) {
  position: absolute;
  top: 0;
  right: 0;
  padding: 2px 10px;
  font-size: 0.7rem;
  color: var(--muted);
  background: var(--bg2);
  border-radius: 0 8px 0 4px;
  z-index: 2;
  pointer-events: none;
}

:deep(.copy-btn) {
  position: absolute;
  top: 4px;
  right: 4px;
  padding: 3px 10px;
  font-size: 0.7rem;
  color: var(--muted);
  background: var(--bg2);
  border: 1px solid var(--rule);
  border-radius: 4px;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.2s, color 0.2s;
  z-index: 3;
}

:deep(.code-block-wrapper:hover .copy-btn) {
  opacity: 1;
}

:deep(.copy-btn:hover) {
  color: var(--accent);
  border-color: var(--accent);
}

/* 当语言标签存在时，复制按钮右移避免重叠 */
:deep(.code-lang-label ~ .copy-btn) {
  right: 70px;
}

/* ── 代码块（highlight.js） ── */
:deep(pre) {
  background: #0d1117;
  border: 1px solid var(--rule);
  border-radius: 8px;
  padding: 0;
  margin: 0;
  overflow-x: auto;
  position: relative;
}

:deep(pre::before) {
  content: attr(data-lang);
  position: absolute;
  top: 0;
  right: 0;
  padding: 2px 10px;
  font-size: 0.7rem;
  color: var(--muted);
  background: var(--bg2);
  border-radius: 0 8px 0 4px;
}

:deep(pre code) {
  display: block;
  padding: 1rem 1.25rem;
  font-size: 0.85rem;
  line-height: 1.6;
  font-family: 'Consolas', 'Courier New', monospace;
  overflow-x: auto;
}

:deep(pre code.hljs) {
  background: transparent;
  color: #e6edf3;
}

/* ── 引用角标 ── */
:deep(sup.citation) {
  color: var(--accent);
  font-weight: 700;
  font-size: 0.78em;
  cursor: pointer;
  margin: 0 1px;
  vertical-align: super;
  transition: background 0.15s;
  padding: 0 2px;
  border-radius: 2px;
}

:deep(sup.citation:hover) {
  background: rgba(88, 166, 255, 0.15);
}

/* ── 来源引用悬浮卡片 ── */
.sources {
  margin-top: 1rem;
  padding-top: 0.65rem;
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
  bottom: 130%;
  left: 50%;
  transform: translateX(-50%);
  width: 320px;
  background: var(--bg);
  border: 1px solid var(--rule);
  border-radius: 8px;
  font-size: 0.8rem;
  font-weight: 400;
  color: var(--ink);
  white-space: normal;
  word-break: break-word;
  z-index: 100;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
  overflow: hidden;
}

.source-badge:hover .source-tooltip {
  display: block;
}

.tooltip-header {
  padding: 0.5rem 0.75rem;
  background: var(--bg2);
  border-bottom: 1px solid var(--rule);
  font-weight: 600;
  font-size: 0.78rem;
  color: var(--accent);
}

.tooltip-body {
  padding: 0.65rem 0.75rem;
  line-height: 1.6;
  max-height: 180px;
  overflow-y: auto;
}

.tooltip-score {
  padding: 0.35rem 0.75rem;
  background: var(--bg2);
  border-top: 1px solid var(--rule);
  font-size: 0.72rem;
  color: var(--accent2);
}
</style>