<script setup lang="ts">
/**
 * RAGAS 质量评估页面
 *
 * API:
 *   POST /evaluation/generate-dataset  — 自动生成评估数据集
 *   POST /evaluation/run                — 启动评估
 *   GET  /evaluation/progress           — 轮询评估进度（含 RAG 阶段）
 *   GET  /evaluation/latest             — 获取最新评估结果
 *   GET  /evaluation/history            — 获取评估历史
 */
import { ref, onMounted, onUnmounted, computed } from 'vue'
import api from '@/utils/api'
import type {
  EvaluationResult,
  EvalProgress,
  DatasetItem,
  HistoryResponse,
} from '@/types'

// ═══════════════════════════════════════════
// RAG 六阶段定义
// ═══════════════════════════════════════════
const RAG_STAGES = [
  { key: 'classify', label: '查询分类' },
  { key: 'rewrite', label: '查询改写' },
  { key: 'retrieve', label: '文档检索' },
  { key: 'crag', label: 'CRAG评估' },
  { key: 'generate', label: '生成回答' },
  { key: 'faithfulness_check', label: '忠实度校验' },
] as const

// ═══════════════════════════════════════════
// 状态
// ═══════════════════════════════════════════
const genCount = ref(3)
const datasetItems = ref<DatasetItem[]>([])
const isGenerating = ref(false)
const isRunning = ref(false)
const evalProgress = ref<EvalProgress | null>(null)
const evalResult = ref<EvaluationResult | null>(null)
const evalHistory = ref<EvaluationResult[]>([])
const error = ref('')
const loading = ref(false)
const clearingHistory = ref(false)

let pollTimer: ReturnType<typeof setInterval> | null = null
let hasSeenProgress = false
let pollAttempts = 0
const MAX_POLL_ATTEMPTS = 200  // 最多轮询 200 次 (200 × 3s = 10 分钟)

// ═══════════════════════════════════════════
// 计算属性
// ═══════════════════════════════════════════
const progressPercent = computed(() => {
  if (!evalProgress.value) return 0
  return Math.round((evalProgress.value.current / evalProgress.value.total) * 100)
})

const progressLabel = computed(() => {
  if (!evalProgress.value) return ''
  return `${evalProgress.value.current}/${evalProgress.value.total} (${progressPercent.value}%)`
})

const datasetCount = computed(() => datasetItems.value.length)

// ═══════════════════════════════════════════
// 生成数量控制
// ═══════════════════════════════════════════
function adjustGenCount(delta: number) {
  const val = genCount.value + delta
  if (val < 1) genCount.value = 1
  else if (val > 20) genCount.value = 20
  else genCount.value = val
}

// ═══════════════════════════════════════════
// API 方法
// ═══════════════════════════════════════════
async function generateDataset() {
  isGenerating.value = true
  error.value = ''
  datasetItems.value = []
  try {
    const res = await api.post('/evaluation/generate-dataset', {
      num_queries: genCount.value,
    }, { timeout: 300_000 })
    if (res.data.dataset && Array.isArray(res.data.dataset)) {
      datasetItems.value = res.data.dataset
    }
  } catch (e: any) {
    error.value = e.response?.data?.detail || e.message || '数据集生成失败'
  } finally {
    isGenerating.value = false
  }
}

async function runEvaluation() {
  isRunning.value = true
  error.value = ''
  evalProgress.value = null
  evalResult.value = null
  hasSeenProgress = false
  pollAttempts = 0
  try {
    const res = await api.post('/evaluation/run', {}, { timeout: 300_000 })
    if (res.data.status === 'running') {
      startPolling()
    }
  } catch (e: any) {
    isRunning.value = false
    error.value = e.response?.data?.detail || e.message || '评估执行失败'
  }
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(pollProgress, 3000)
  // 立即拉一次
  pollProgress()
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function pollProgress() {
  pollAttempts++
  if (pollAttempts > MAX_POLL_ATTEMPTS) {
    stopPolling()
    isRunning.value = false
    error.value = '评估超时，请稍后查看历史记录'
    return
  }

  try {
    const progressRes = await api.get('/evaluation/progress')
    if (progressRes.data && progressRes.data.status !== 'idle') {
      // 有进度数据，更新 UI
      evalProgress.value = progressRes.data
      hasSeenProgress = true
      return
    }
  } catch {
    // 静默
  }

  // 进度为 idle：如果之前看到过进度 → 评估刚完成，获取结果
  if (hasSeenProgress) {
    stopPolling()
    // 保留进度栏 2 秒让用户看到完成状态
    if (evalProgress.value) {
      // 标记所有 item 为完成
      const completedItems = (evalProgress.value.per_item || []).map(item => ({
        ...item,
        status: 'done',
        current_stage: 'complete',
      }))
      evalProgress.value = { ...evalProgress.value, per_item: completedItems }
    }
    setTimeout(async () => {
      evalProgress.value = null
      isRunning.value = false
      try {
        const res = await api.get('/evaluation/latest')
        if (res.data && res.data.status !== 'empty') {
          if (
            res.data.avg_faithfulness !== undefined ||
            res.data.faithfulness !== undefined
          ) {
            evalResult.value = res.data
            fetchHistory()
          }
        }
      } catch {
        // 静默
      }
    }, 2000)
    return
  }
  // 还没看到进度 → 继续等待（后台任务可能还未启动）
}

async function fetchLatest() {
  loading.value = true
  try {
    const res = await api.get('/evaluation/latest')
    if (res.data && res.data.status !== 'empty') {
      evalResult.value = res.data
    } else {
      evalResult.value = null
    }
  } catch {
    // 尚无评估记录时静默
  } finally {
    loading.value = false
  }
}

async function fetchHistory() {
  try {
    const res = await api.get<HistoryResponse>('/evaluation/history')
    const list = res.data.history ?? (Array.isArray(res.data) ? res.data : [])
    evalHistory.value = list
  } catch {
    // 静默
  }
}

async function clearHistory() {
  clearingHistory.value = true
  try {
    await api.delete('/evaluation/history')
    evalHistory.value = []
    evalResult.value = null
  } catch (e: any) {
    error.value = e.response?.data?.detail || e.message || '清空历史失败'
  } finally {
    clearingHistory.value = false
  }
}

// ═══════════════════════════════════════════
// 辅助函数
// ═══════════════════════════════════════════
function getScore(result: EvaluationResult, key: 'faithfulness' | 'context_precision' | 'context_recall' | 'answer_relevancy' | 'keyword_coverage'): number | undefined {
  const avgKey = `avg_${key}` as keyof EvaluationResult
  return (result[avgKey] as number | undefined) ?? (result[key] as number | undefined)
}

function formatScore(val?: number): string {
  if (val === undefined || val === null) return '--'
  return val.toFixed(3)
}

function formatDate(val?: string): string {
  if (!val) return ''
  try {
    const normalized = val.replace(/(\.\d{3})\d+/, '$1')
    const d = new Date(normalized)
    if (isNaN(d.getTime())) return val
    return d.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      year: 'numeric',
    })
  } catch {
    return val
  }
}

function scoreBarWidth(score?: number): string {
  if (score === undefined || score === null) return '0%'
  return `${Math.min(score * 100, 100)}%`
}

function getStageClass(item: NonNullable<EvalProgress>['per_item'][number], stageKey: string): string {
  if (item.stages_completed?.includes(stageKey)) return 'completed'
  if (item.current_stage === stageKey) return 'active'
  return 'pending'
}

function getStatusClass(status: string): string {
  if (status === 'done') return 'done'
  if (status === 'running') return 'running'
  if (status === 'error') return 'error'
  return 'pending'
}

function getStatusLabel(status: string): string {
  if (status === 'done') return '已完成'
  if (status === 'running') return '评估中'
  if (status === 'error') return '失败'
  return '等待中'
}

// ═══════════════════════════════════════════
// 生命周期
// ═══════════════════════════════════════════
onMounted(() => {
  fetchLatest()
  fetchHistory()
})

onUnmounted(() => {
  stopPolling()
})
</script>

<template>
  <div class="eval-view">
    <!-- Page Header -->
    <header class="page-header">
      <h1 class="page-title">RAGAS 质量评估</h1>
      <div class="page-actions">
        <div class="gen-count-control">
          <label class="gen-count-label">生成数量</label>
          <div class="gen-count-input">
            <button class="gen-count-btn" @click="adjustGenCount(-1)" :disabled="isGenerating">-</button>
            <span class="gen-count-value">{{ genCount }}</span>
            <button class="gen-count-btn" @click="adjustGenCount(1)" :disabled="isGenerating">+</button>
          </div>
        </div>
        <button class="btn btn-outline" :disabled="isGenerating" @click="generateDataset">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/><path d="M16 16h5v5"/></svg>
          {{ isGenerating ? '生成中...' : '生成数据集' }}
        </button>
        <button class="btn btn-primary" :disabled="isRunning" @click="runEvaluation">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
          {{ isRunning ? '评估中...' : '运行评估' }}
        </button>
      </div>
    </header>

    <!-- Error -->
    <div v-if="error" class="error-banner">{{ error }}</div>

    <!-- Loading -->
    <div v-if="loading" class="loading-state">加载中...</div>

    <!-- Test Set Preview -->
    <section v-if="datasetItems.length > 0" class="card">
      <div class="card-title">
        测试集
        <span class="badge">{{ datasetCount }} 条</span>
      </div>
      <div
        v-for="(item, idx) in datasetItems"
        :key="idx"
        class="test-item"
      >
        <div class="test-item-num">{{ idx + 1 }}</div>
        <div class="test-item-body">
          <div class="test-item-query">{{ item.query }}</div>
          <div class="test-item-keywords">
            <span
              v-for="(kw, kwIdx) in item.expected_keywords"
              :key="kwIdx"
              class="keyword-tag"
            >{{ kw }}</span>
          </div>
        </div>
      </div>
    </section>

    <!-- Evaluation Progress -->
    <section v-if="isRunning || evalProgress" class="card">
      <div class="card-title">评估进度</div>
      <div v-if="evalProgress" class="eval-progress-header">
        <span class="eval-progress-label">{{ progressLabel }}</span>
        <span class="eval-progress-pct">进行中</span>
      </div>
      <div class="progress-bar-track">
        <div class="progress-bar-fill" :style="{ width: progressPercent + '%' }"></div>
      </div>

      <!-- Per-item pipeline -->
      <div
        v-if="evalProgress && evalProgress.per_item"
        class="eval-items"
      >
        <div
          v-for="(item, idx) in evalProgress.per_item"
          :key="idx"
          class="eval-item"
        >
          <div class="eval-item-header">
            <div :class="['eval-item-status', getStatusClass(item.status)]">
              <svg v-if="item.status === 'done'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
            </div>
            <span class="eval-item-query">{{ item.query }}</span>
            <span class="eval-item-label">{{ getStatusLabel(item.status) }}</span>
          </div>
          <div v-if="item.error" class="eval-item-error">{{ item.error }}</div>
          <div class="pipeline">
            <template v-for="(stage, si) in RAG_STAGES" :key="stage.key">
              <div class="stage">
                <div :class="['stage-circle', getStageClass(item, stage.key)]">
                  <svg v-if="getStageClass(item, stage.key) === 'completed'" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                  <svg v-else-if="getStageClass(item, stage.key) === 'active'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="1"/></svg>
                </div>
                <div :class="['stage-label', getStageClass(item, stage.key)]">{{ stage.label }}</div>
              </div>
              <div v-if="si < RAG_STAGES.length - 1" :class="['stage-line', getStageClass(item, RAG_STAGES[si + 1].key)]"></div>
            </template>
          </div>
        </div>
      </div>
    </section>

    <!-- Latest Results -->
    <section v-if="evalResult" class="card">
      <div class="card-title">最新评估结果</div>
      <div class="score-summary">
        <span v-if="evalResult.total_evaluated !== undefined">
          已评估 <strong>{{ evalResult.total_evaluated }}/{{ evalResult.dataset_size ?? '?' }}</strong> 条
          <span v-if="(evalResult.total_errors ?? 0) > 0" class="score-summary-error">
            ({{ evalResult.total_errors }} 条错误)
          </span>
        </span>
      </div>

      <div class="score-row">
        <div class="score-metric">
          <div class="score-metric-name">忠实度</div>
          <div class="score-metric-en">Faithfulness</div>
        </div>
        <div class="score-bar-track">
          <div class="score-bar-fill" :style="{ width: scoreBarWidth(getScore(evalResult, 'faithfulness')) }"></div>
        </div>
        <div class="score-value">{{ formatScore(getScore(evalResult, 'faithfulness')) }}</div>
      </div>

      <div class="score-row">
        <div class="score-metric">
          <div class="score-metric-name">上下文精确率</div>
          <div class="score-metric-en">Context Precision</div>
        </div>
        <div class="score-bar-track">
          <div class="score-bar-fill" :style="{ width: scoreBarWidth(getScore(evalResult, 'context_precision')) }"></div>
        </div>
        <div class="score-value">{{ formatScore(getScore(evalResult, 'context_precision')) }}</div>
      </div>

      <div class="score-row">
        <div class="score-metric">
          <div class="score-metric-name">上下文召回率</div>
          <div class="score-metric-en">Context Recall</div>
        </div>
        <div class="score-bar-track">
          <div class="score-bar-fill" :style="{ width: scoreBarWidth(getScore(evalResult, 'context_recall')) }"></div>
        </div>
        <div class="score-value">{{ formatScore(getScore(evalResult, 'context_recall')) }}</div>
      </div>

      <div class="score-row">
        <div class="score-metric">
          <div class="score-metric-name">答案相关性</div>
          <div class="score-metric-en">Answer Relevancy</div>
        </div>
        <div class="score-bar-track">
          <div class="score-bar-fill" :style="{ width: scoreBarWidth(getScore(evalResult, 'answer_relevancy')) }"></div>
        </div>
        <div class="score-value">{{ formatScore(getScore(evalResult, 'answer_relevancy')) }}</div>
      </div>

      <div class="score-row">
        <div class="score-metric">
          <div class="score-metric-name">关键词覆盖率</div>
          <div class="score-metric-en">Keyword Coverage</div>
        </div>
        <div class="score-bar-track">
          <div class="score-bar-fill" :style="{ width: scoreBarWidth(getScore(evalResult, 'keyword_coverage')) }"></div>
        </div>
        <div class="score-value">{{ formatScore(getScore(evalResult, 'keyword_coverage')) }}</div>
      </div>

      <div v-if="evalResult.created_at || evalResult.timestamp" class="eval-time">
        评估时间: {{ formatDate(evalResult.created_at || evalResult.timestamp) }}
      </div>
    </section>

    <!-- Empty state -->
    <section v-if="!evalResult && !isRunning && !evalProgress && !loading" class="card">
      <div class="card-title">最新评估结果</div>
      <div class="eval-empty">暂无评估数据，请先生成数据集并点击"运行评估"</div>
    </section>

    <!-- Evaluation History -->
    <section v-if="evalHistory.length > 0" class="card">
      <div class="card-title">
        评估历史
        <button
          class="btn btn-ghost btn-sm"
          :disabled="clearingHistory"
          @click="clearHistory"
          style="margin-left: auto;"
        >{{ clearingHistory ? '清空中...' : '清空历史' }}</button>
      </div>
      <table class="history-table">
        <thead>
          <tr>
            <th>时间</th>
            <th>F</th>
            <th>P</th>
            <th>R</th>
            <th>A</th>
            <th>K</th>
            <th>条数</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(item, idx) in evalHistory" :key="idx">
            <td>{{ formatDate(item.created_at || item.timestamp) }}</td>
            <td>{{ formatScore(getScore(item, 'faithfulness')) }}</td>
            <td>{{ formatScore(getScore(item, 'context_precision')) }}</td>
            <td>{{ formatScore(getScore(item, 'context_recall')) }}</td>
            <td>{{ formatScore(getScore(item, 'answer_relevancy')) }}</td>
            <td>{{ formatScore(getScore(item, 'keyword_coverage')) }}</td>
            <td>{{ (item.total_evaluated ?? item.dataset_size ?? '?') }}条</td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<style scoped>
.eval-view {
  padding: 32px 40px 60px;
  max-width: 960px;
}

/* ═══════════════ Page Header ═══════════════ */
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 28px;
}

.page-title {
  font-size: 22px;
  font-weight: 600;
  letter-spacing: var(--tracking-tight);
  color: var(--foreground);
}

.page-actions {
  display: flex;
  gap: 10px;
}

/* ═══════════════ Buttons ═══════════════ */
.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 500;
  font-family: var(--font-sans);
  cursor: pointer;
  border: 1px solid transparent;
  transition: all 0.15s;
  text-decoration: none;
}

.btn svg {
  width: 15px;
  height: 15px;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-outline {
  background: var(--card);
  color: var(--foreground);
  border-color: var(--border);
}

.btn-outline:hover:not(:disabled) {
  background: var(--muted);
  border-color: var(--border-strong);
}

.btn-primary {
  background: var(--primary);
  color: var(--primary-foreground);
  border-color: var(--primary);
}

.btn-primary:hover:not(:disabled) {
  background: var(--brand-800);
}

/* ═══════════════ Generation Count Control ═══════════════ */
.gen-count-control {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-right: 4px;
}

.gen-count-label {
  font-size: 12px;
  color: var(--muted-foreground);
  white-space: nowrap;
}

.gen-count-input {
  display: flex;
  align-items: center;
  border: 1px solid var(--input);
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.gen-count-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--card);
  border: none;
  color: var(--foreground);
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
}

.gen-count-btn:hover:not(:disabled) {
  background: var(--muted);
}

.gen-count-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.gen-count-value {
  width: 32px;
  text-align: center;
  font-family: var(--font-mono);
  font-size: 13px;
  font-weight: 500;
  color: var(--foreground);
  border-left: 1px solid var(--input);
  border-right: 1px solid var(--input);
  line-height: 28px;
}

/* ═══════════════ Card ═══════════════ */
.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px 24px;
  margin-bottom: 20px;
}

.card-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--foreground);
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.card-title .badge {
  font-size: 11px;
  font-weight: 500;
  color: var(--muted-foreground);
  background: var(--muted);
  padding: 2px 8px;
  border-radius: 999px;
}

/* ═══════════════ Error / Loading ═══════════════ */
.error-banner {
  padding: 10px 16px;
  background: var(--destructive-subtle);
  border: 1px solid var(--destructive-border);
  border-radius: var(--radius-sm);
  color: var(--destructive-text);
  font-size: 13px;
  margin-bottom: 20px;
}

.loading-state {
  text-align: center;
  padding: 40px;
  color: var(--muted-foreground);
  font-size: 14px;
}

/* ═══════════════ Test Set Items ═══════════════ */
.test-item {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 12px 0;
  border-bottom: 1px solid var(--border);
}

.test-item:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.test-item:first-child {
  padding-top: 0;
}

.test-item-num {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--muted);
  color: var(--muted-foreground);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 600;
  flex-shrink: 0;
  margin-top: 1px;
}

.test-item-body {
  flex: 1;
  min-width: 0;
}

.test-item-query {
  font-size: 13.5px;
  font-weight: 500;
  color: var(--foreground);
  margin-bottom: 4px;
}

.test-item-keywords {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.keyword-tag {
  font-size: 11px;
  font-family: var(--font-mono);
  color: var(--muted-foreground);
  background: var(--muted);
  padding: 1px 7px;
  border-radius: var(--radius-sm);
}

/* ═══════════════ Evaluation Progress ═══════════════ */
.eval-progress-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.eval-progress-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--foreground);
}

.eval-progress-pct {
  font-size: 13px;
  font-family: var(--font-mono);
  font-weight: 500;
  color: var(--muted-foreground);
}

.progress-bar-track {
  width: 100%;
  height: 6px;
  background: var(--muted);
  border-radius: 999px;
  overflow: hidden;
  margin-bottom: 24px;
}

.progress-bar-fill {
  height: 100%;
  background: var(--primary);
  border-radius: 999px;
  transition: width 0.4s ease;
}

/* ═══════════════ Per-Item Pipeline ═══════════════ */
.eval-items {
  display: flex;
  flex-direction: column;
}

.eval-item {
  padding: 16px 0;
  border-bottom: 1px solid var(--border);
}

.eval-item:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.eval-item:first-child {
  padding-top: 0;
}

.eval-item-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
}

.eval-item-status {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.eval-item-status.done {
  background: var(--success);
}

.eval-item-status.done svg {
  width: 12px;
  height: 12px;
  color: var(--success-foreground);
}

.eval-item-status.running {
  background: transparent;
  border: 2px solid var(--primary);
  animation: pulse-ring 1.8s ease-in-out infinite;
}

.eval-item-status.running::after {
  content: '';
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--primary);
  animation: pulse-dot 1.8s ease-in-out infinite;
}

.eval-item-status.pending {
  background: transparent;
  border: 2px solid var(--border);
}

.eval-item-status.error {
  background: var(--destructive);
  border: 2px solid var(--destructive);
}

.eval-item-status.error::after {
  content: '';
  width: 10px;
  height: 2px;
  background: var(--destructive-foreground);
  border-radius: 1px;
}

@keyframes pulse-ring {
  0%, 100% { border-color: var(--primary); transform: scale(1); }
  50% { border-color: var(--brand-400); transform: scale(1.15); }
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.eval-item-query {
  font-size: 13px;
  font-weight: 500;
  color: var(--foreground);
}

.eval-item-label {
  font-size: 11px;
  color: var(--muted-foreground);
  margin-left: auto;
  flex-shrink: 0;
}

.eval-item-error {
  font-size: 11px;
  color: var(--destructive-text);
  margin-bottom: 10px;
  padding-left: 30px;
}

/* Pipeline stages */
.pipeline {
  display: flex;
  align-items: flex-start;
  gap: 0;
  padding-left: 30px;
}

.stage {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: 1;
  min-width: 0;
}

.stage-circle {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.stage-circle svg {
  width: 12px;
  height: 12px;
}

.stage-circle.completed {
  background: var(--foreground);
  border-color: var(--foreground);
}

.stage-circle.pending {
  background: var(--card);
  border: 1.5px solid var(--border);
}

.stage-circle.active {
  background: var(--foreground);
  border-color: var(--foreground);
  animation: stage-pulse 1.5s ease-in-out infinite;
}

.stage-circle.active svg {
  width: 8px;
  height: 8px;
  fill: white;
  stroke: white;
}

@keyframes stage-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(24, 24, 27, 0.3); }
  50% { box-shadow: 0 0 0 4px rgba(24, 24, 27, 0.08); }
}

.stage-label {
  margin-top: 6px;
  text-align: center;
  font-size: 10px;
  color: var(--muted-foreground);
  line-height: 1.3;
  white-space: nowrap;
}

.stage-label.completed {
  color: var(--foreground);
  font-weight: 500;
}

.stage-label.active {
  color: var(--foreground);
  font-weight: 500;
}

.stage-line {
  width: 100%;
  max-width: 40px;
  height: 2px;
  flex-shrink: 0;
  margin-top: 10px;
}

.stage-line.completed {
  background: var(--primary);
}

.stage-line.active {
  background: var(--primary);
}

.stage-line.pending {
  background: var(--border);
}

/* ═══════════════ Score Bars ═══════════════ */
.score-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 18px;
  font-size: 13px;
  color: var(--muted-foreground);
}

.score-summary strong {
  color: var(--foreground);
  font-weight: 600;
}

.score-summary-error {
  color: var(--destructive-text);
  margin-left: 6px;
  font-size: 12px;
}

.score-row {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 14px;
}

.score-row:last-child {
  margin-bottom: 0;
}

.score-metric {
  width: 150px;
  flex-shrink: 0;
}

.score-metric-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--foreground);
}

.score-metric-en {
  font-size: 11px;
  color: var(--muted-foreground);
  font-family: var(--font-mono);
}

.score-bar-track {
  flex: 1;
  height: 6px;
  background: var(--muted);
  border-radius: 999px;
  overflow: hidden;
}

.score-bar-fill {
  height: 100%;
  background: var(--primary);
  border-radius: 999px;
  transition: width 0.6s ease;
}

.score-value {
  width: 52px;
  text-align: right;
  font-size: 13px;
  font-family: var(--font-mono);
  font-weight: 500;
  color: var(--foreground);
  flex-shrink: 0;
}

.eval-time {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--border);
  font-size: 12px;
  color: var(--muted-foreground);
}

.eval-empty {
  text-align: center;
  padding: 24px;
  color: var(--muted-foreground);
  font-size: 13px;
}

/* ═══════════════ History Table ═══════════════ */
.history-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.history-table thead th {
  text-align: left;
  padding: 8px 12px;
  font-size: 11px;
  font-weight: 600;
  color: var(--muted-foreground);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  border-bottom: 1px solid var(--border-strong);
}

.history-table thead th:not(:first-child) {
  text-align: right;
}

.history-table tbody td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  color: var(--foreground);
}

.history-table tbody td:not(:first-child) {
  text-align: right;
  font-family: var(--font-mono);
  font-size: 12.5px;
}

.history-table tbody td:first-child {
  font-family: var(--font-mono);
  font-size: 12.5px;
  color: var(--muted-foreground);
}

.history-table tbody tr:last-child td {
  border-bottom: none;
}

.history-table tbody tr:hover {
  background: var(--muted);
}
</style>