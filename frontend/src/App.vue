<script setup lang="ts">
import { useConversationStore } from '@/stores/conversation'

const conversationStore = useConversationStore()
</script>

<template>
  <div class="app">
    <h1>DocsChat</h1>
    <p>RAG 智能对话系统 — 准备就绪</p>
    <p class="muted">Day 1 将实现完整的流式对话功能</p>
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
}

*,
*::before,
*::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: var(--bg);
  color: var(--ink);
  min-height: 100vh;
}

.app {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  text-align: center;
}

h1 {
  font-size: 2.5rem;
  margin-bottom: 0.5rem;
  color: var(--accent);
}

.muted {
  color: var(--muted);
  font-size: 0.9rem;
  margin-top: 0.5rem;
}
</style>