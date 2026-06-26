<script setup lang="ts">
import { ref } from 'vue'
import ChatView from '@/views/ChatView.vue'
import StatsView from '@/views/StatsView.vue'
import HistorySidebar from '@/components/HistorySidebar.vue'
import { useTheme } from '@/composables/useTheme'  // v4.5

const currentView = ref<'chat' | 'stats'>('chat')
const showHistory = ref(false)
const replayQuery = ref<{ query: string; library: string | null } | null>(null)

// v4.5: 主题切换
const { themeIcon, themeLabel, toggleTheme } = useTheme()

function handleHistorySelect(query: string, library: string | null) {
  replayQuery.value = { query, library }
  showHistory.value = false
}
</script>

<template>
  <nav class="nav-bar">
    <div class="nav-left">
      <button
        :class="['nav-btn', { active: currentView === 'chat' }]"
        @click="currentView = 'chat'"
      >
        对话
      </button>
      <button
        :class="['nav-btn', { active: currentView === 'stats' }]"
        @click="currentView = 'stats'"
      >
        监控
      </button>
    </div>
    <div class="nav-right">
      <button
        v-if="currentView === 'chat'"
        :class="['nav-btn', { active: showHistory }]"
        @click="showHistory = !showHistory"
      >
        历史
      </button>
      <button
        class="nav-btn theme-btn"
        @click="toggleTheme"
        :title="`当前: ${themeLabel}（点击切换）`"
      >
        {{ themeIcon }}
      </button>
    </div>
  </nav>
  <div class="main-content">
    <HistorySidebar
      v-if="showHistory && currentView === 'chat'"
      @select="handleHistorySelect"
    />
    <ChatView
      v-if="currentView === 'chat'"
      :replay="replayQuery"
      @replay-consumed="replayQuery = null"
    />
    <StatsView v-else />
  </div>
</template>

<style>
:root {
  --bg: #0d1117;
  --bg2: #161b22;
  --ink: #e6edf3;
  --muted: #8b949e;
  --rule: #30363d;
  --accent: #58a6ff;
  --accent2: #3fb950;
  --danger: #f85149;
}

*,
*::before,
*::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', sans-serif;
  background: var(--bg);
  color: var(--ink);
  min-height: 100vh;
  overflow: hidden;
}

/* ── v4.3: 导航栏 ── */
.nav-bar {
  display: flex;
  justify-content: space-between;
  padding: 6px 16px;
  background: var(--bg2);
  border-bottom: 1px solid var(--rule);
  height: 40px;
  align-items: center;
}

.nav-left, .nav-right {
  display: flex;
  gap: 4px;
}

.main-content {
  display: flex;
  height: calc(100vh - 40px);
  overflow: hidden;
}

.nav-btn {
  padding: 4px 14px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  font-size: 0.85rem;
  transition: all 0.15s;
}

.nav-btn:hover {
  color: var(--ink);
  background: var(--bg);
}

.nav-btn.active {
  color: var(--accent);
  border-color: var(--rule);
  background: var(--bg);
}

::-webkit-scrollbar {
  width: 6px;
}

::-webkit-scrollbar-track {
  background: transparent;
}

::-webkit-scrollbar-thumb {
  background: var(--rule);
  border-radius: 3px;
}

::-webkit-scrollbar-thumb:hover {
  background: var(--muted);
}

/* ── highlight.js GitHub Dark 主题 ── */
.hljs {
  color: #e6edf3;
  background: #0d1117;
}

.hljs-keyword,
.hljs-selector-tag,
.hljs-literal,
.hljs-section,
.hljs-link {
  color: #ff7b72;
}

.hljs-string,
.hljs-title,
.hljs-name,
.hljs-type,
.hljs-attribute,
.hljs-symbol,
.hljs-bullet,
.hljs-addition,
.hljs-variable,
.hljs-template-tag,
.hljs-template-variable {
  color: #a5d6ff;
}

.hljs-comment,
.hljs-quote,
.hljs-deletion,
.hljs-meta {
  color: #8b949e;
}

.hljs-number,
.hljs-regexp,
.hljs-built_in {
  color: #79c0ff;
}

.hljs-function .hljs-title,
.hljs-title.function_,
.hljs-title.class_,
.hljs-attr,
.hljs-params {
  color: #d2a8ff;
}

.hljs-class .hljs-title {
  color: #ffa657;
}

.hljs-attr,
.hljs-selector-attr,
.hljs-selector-class,
.hljs-selector-pseudo {
  color: #79c0ff;
}

.hljs-tag {
  color: #7ee787;
}

.hljs-tag .hljs-name {
  color: #7ee787;
}

.hljs-tag .hljs-attr {
  color: #79c0ff;
}

/* ── 选择文字颜色 ── */
::selection {
  background: rgba(88, 166, 255, 0.25);
}
</style>