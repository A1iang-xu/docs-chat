<script setup lang="ts">
import { computed, ref } from 'vue'
import { useMarkdown } from '@/composables/useMarkdown'
import api from '@/utils/api'
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

const displayContent = computed(() => {
  if (isAssistant.value) {
    return renderedContent.value
  }
  return props.message.content
})

// v4.4: 来源卡片展开状态
const expandedSources = ref<Set<number>>(new Set())

function toggleSource(index: number) {
  if (expandedSources.value.has(index)) {
    expandedSources.value.delete(index)
  } else {
    expandedSources.value.add(index)
  }
}

// v4.0: 反馈
const feedbackSubmitted = ref(false)
const lastFeedback = ref<'positive' | 'negative' | null>(null)
const submittingFeedback = ref(false)

async function submitFeedback(choice: 'positive' | 'negative') {
  if (submittingFeedback.value) return
  submittingFeedback.value = true
  try {
    await api.post('/feedback/', {
      message_id: props.message.id,
      query: '',
      answer: props.message.content,
      sources: props.message.sources,
      feedback: choice,
    })
    lastFeedback.value = choice
    feedbackSubmitted.value = true
  } catch {
    // silent fail
  } finally {
    submittingFeedback.value = false
  }
}
</script>

<template>
  <div class="message" :class="{ user: isUser, assistant: isAssistant }">
    <div class="role-label">{{ isUser ? '你' : 'DocsChat' }}</div>
    <div class="content">
      <!-- 用户消息 -->
      <div v-if="isUser" class="text" v-text="displayContent"></div>

      <!-- AI 消息 -->
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
          @click="toggleSource(source.index)"
        >
          [{{ source.index }}]
          <span class="source-tooltip">
            <div class="tooltip-header">
              <a
                v-if="source.sourceUrl"
                :href="source.sourceUrl"
                target="_blank"
                rel="noopener"
                class="source-link"
                @click.stop
              >
                {{ source.headingPath || source.documentName || '未知文档' }}
              </a>
              <template v-else>
                {{ source.documentName || '未知文档' }}
              </template>
              <span v-if="source.page">· 第 {{ source.page }} 页</span>
              <span v-if="source.library" class="tooltip-library">· {{ source.library }}</span>
            </div>
            <div class="tooltip-body">{{ source.content }}</div>
            <div class="tooltip-score">相关度: {{ (source.relevanceScore * 100).toFixed(1) }}%</div>
          </span>
        </span>

        <div
          v-for="source in message.sources.filter(s => expandedSources.has(s.index))"
          :key="'expanded-' + source.index"
          class="source-card"
        >
          <div class="card-header">
            <a
              v-if="source.sourceUrl"
              :href="source.sourceUrl"
              target="_blank"
              rel="noopener"
              class="source-link"
            >
              [{{ source.index }}] {{ source.headingPath || source.documentName || '未知文档' }}
            </a>
            <span v-else>[{{ source.index }}] {{ source.documentName || '未知文档' }}</span>
            <span v-if="source.library" class="card-library">{{ source.library }}</span>
            <span class="card-score">{{ (source.relevanceScore * 100).toFixed(1) }}%</span>
            <button class="card-close" @click="toggleSource(source.index)">×</button>
          </div>
          <div class="card-body">{{ source.content }}</div>
        </div>
      </div>

      <!-- 反馈按钮 -->
      <div v-if="isAssistant && message.id" class="feedback">
        <button
          class="feedback-btn"
          :class="{ active: lastFeedback === 'positive' }"
          :disabled="feedbackSubmitted"
          title="回答有用"
          @click="submitFeedback('positive')"
        >
          👍
        </button>
        <button
          class="feedback-btn"
          :class="{ active: lastFeedback === 'negative' }"
          :disabled="feedbackSubmitted"
          title="回答有误"
          @click="submitFeedback('negative')"
        >
          👎
        </button>
        <span v-if="feedbackSubmitted" class="feedback-done">感谢反馈</span>
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
  background: var(--background);
}

.message.assistant {
  background: var(--muted);
}

.role-label {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--muted-foreground);
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
  color: var(--foreground);
}

.markdown-body :deep(h1) { font-size: 1.3rem; }
.markdown-body :deep(h2) { font-size: 1.15rem; border-bottom: 1px solid var(--border); padding-bottom: 0.25rem; }
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
  border-left: 3px solid var(--primary);
  padding: 0.25rem 1rem;
  margin: 0.75rem 0;
  color: var(--muted-foreground);
  background: var(--brand-subtle);
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
}

.markdown-body :deep(table) {
  border-collapse: collapse;
  margin: 0.75rem 0;
  font-size: 0.85rem;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid var(--border);
  padding: 0.4rem 0.75rem;
  text-align: left;
}

.markdown-body :deep(th) {
  background: var(--muted);
  font-weight: 600;
}

.markdown-body :deep(strong) {
  font-weight: 700;
  color: var(--foreground);
}

.markdown-body :deep(a) {
  color: var(--primary);
  text-decoration: none;
}

.markdown-body :deep(a:hover) {
  text-decoration: underline;
}

/* ── 行内代码 ── */
:deep(.inline-code) {
  background: var(--brand-subtle);
  color: var(--primary);
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  font-size: 0.88em;
  font-family: var(--font-mono);
}

/* ── 代码块容器 ── */
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
  color: var(--muted-foreground);
  background: var(--muted);
  border-radius: 0 var(--radius-sm) 0 var(--radius-sm);
  z-index: 2;
  pointer-events: none;
}

:deep(.copy-btn) {
  position: absolute;
  top: 4px;
  right: 4px;
  padding: 3px 10px;
  font-size: 0.7rem;
  color: var(--muted-foreground);
  background: var(--muted);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.2s, color 0.2s;
  z-index: 3;
}

:deep(.code-block-wrapper:hover .copy-btn) {
  opacity: 1;
}

:deep(.copy-btn:hover) {
  color: var(--primary);
  border-color: var(--primary);
}

:deep(.code-lang-label ~ .copy-btn) {
  right: 70px;
}

/* ── 代码块 ── */
:deep(pre) {
  background: #0d1117;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 0;
  margin: 0;
  overflow-x: auto;
  position: relative;
}

:deep(pre code) {
  display: block;
  padding: 1rem 1.25rem;
  font-size: 0.85rem;
  line-height: 1.6;
  font-family: var(--font-mono);
  overflow-x: auto;
}

:deep(pre code.hljs) {
  background: transparent;
  color: #e6edf3;
}

/* ── 引用角标 ── */
:deep(sup.citation) {
  color: var(--primary);
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
  background: var(--brand-subtle);
}

/* ── 来源引用悬浮卡片 ── */
.sources {
  margin-top: 1rem;
  padding-top: 0.65rem;
  border-top: 1px solid var(--border);
  font-size: 0.8rem;
  color: var(--muted-foreground);
}

.sources-label {
  margin-right: 0.25rem;
}

.source-badge {
  display: inline-block;
  position: relative;
  color: var(--primary);
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
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 0.8rem;
  font-weight: 400;
  color: var(--foreground);
  white-space: normal;
  word-break: break-word;
  z-index: 100;
  box-shadow: var(--shadow-lg);
  overflow: hidden;
}

.source-badge:hover .source-tooltip {
  display: block;
}

.tooltip-header {
  padding: 0.5rem 0.75rem;
  background: var(--muted);
  border-bottom: 1px solid var(--border);
  font-weight: 600;
  font-size: 0.78rem;
  color: var(--primary);
}

.tooltip-body {
  padding: 0.65rem 0.75rem;
  line-height: 1.6;
  max-height: 180px;
  overflow-y: auto;
}

.tooltip-score {
  padding: 0.35rem 0.75rem;
  background: var(--muted);
  border-top: 1px solid var(--border);
  font-size: 0.72rem;
  color: var(--success-text);
}

.source-link {
  color: var(--primary);
  text-decoration: none;
}
.source-link:hover {
  text-decoration: underline;
}

.tooltip-library {
  font-size: 0.72rem;
  color: var(--muted-foreground);
}

.source-card {
  margin-top: 0.5rem;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  overflow: hidden;
}
.card-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.4rem 0.6rem;
  background: var(--muted);
  border-bottom: 1px solid var(--border);
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--primary);
}
.card-library {
  padding: 1px 6px;
  background: var(--brand-subtle);
  border-radius: 3px;
  font-size: 0.65rem;
  color: var(--primary);
}
.card-score {
  margin-left: auto;
  font-size: 0.7rem;
  color: var(--success-text);
  font-weight: 400;
}
.card-close {
  background: none;
  border: none;
  color: var(--muted-foreground);
  cursor: pointer;
  font-size: 1rem;
  line-height: 1;
  padding: 0;
  transition: color 0.15s;
}
.card-close:hover {
  color: var(--destructive);
}
.card-body {
  padding: 0.5rem 0.6rem;
  font-size: 0.78rem;
  line-height: 1.6;
  color: var(--foreground);
  max-height: 200px;
  overflow-y: auto;
}

.feedback {
  margin-top: 0.65rem;
  display: flex;
  align-items: center;
  gap: 0.4rem;
}
.feedback-btn {
  background: none;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 2px 8px;
  cursor: pointer;
  font-size: 0.85rem;
  opacity: 0.5;
  transition: opacity 0.15s, border-color 0.15s;
}
.feedback-btn:hover:not(:disabled) {
  opacity: 1;
  border-color: var(--primary);
}
.feedback-btn.active {
  opacity: 1;
  border-color: var(--success);
  background: var(--success-subtle);
}
.feedback-btn:disabled {
  cursor: default;
}
.feedback-done {
  font-size: 0.72rem;
  color: var(--success-text);
}
</style>