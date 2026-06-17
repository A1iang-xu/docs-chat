<script setup lang="ts">
import ChatView from '@/views/ChatView.vue'
</script>

<template>
  <ChatView />
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