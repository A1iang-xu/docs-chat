# 评估超时修复与评估过程可视化方案

## 1. 概述

**问题**: 点击"运行评估"后，前端轮询 10 分钟仍超时，显示"评估超时，请稍后手动刷新查看结果"。

**根因**: 之前的两项修改（轻量 LLM 答案生成 + API max_items）用户要求撤回。需要在保持完整 RAG 管道的前提下，通过缩小数据集规模 + 可视化进度来解决超时问题。

**核心原则**: 必须走完整 RAG 管道（`rag_orchestrator.chat_stream()`），不能跳过任何环节。

---

## 2. 当前状态分析

### 2.1 需要撤回的修改

| 文件 | 修改内容 | 撤回方式 |
|------|---------|---------|
| `backend/app/services/evaluation_service.py` L134-156 | `_generate_answer()` 轻量 LLM 答案生成方法 | 删除整个方法 |
| `backend/app/services/evaluation_service.py` L98-99 | `evaluate_dataset()` 中调用 `_generate_answer()` 替代完整 RAG | 改回 `rag_orchestrator.chat_stream()` |
| `backend/app/api/evaluation.py` L30 | `EvalRequest.max_items: int = 5` 字段 | 删除该字段 |
| `backend/app/api/evaluation.py` L104 | `run_evaluation()` 中传递 `max_items` 参数 | 删除该参数传递 |
| `frontend/src/views/StatsView.vue` L133 | `runEvaluation()` 中 `api.post('/evaluation/run', {})` 无 max_items | 无需修改（本来就没传 max_items） |

### 2.2 需要保留的修改

- `evaluation_service.py` 中的 `evaluate_single()` 并行评估（`asyncio.gather`）—— 保留
- `evaluation_service.py` 中的 `_llm_score()` 60s 超时 —— 保留
- `evaluation_service.py` 中的 `_write_progress()` / `get_progress()` —— 保留并增强
- `evaluation_service.py` 中 `evaluate_dataset()` 的 `max_items` 参数 —— 保留（改为默认 3，用于内部截断）
- `evaluation.py` 中的 `BackgroundTasks` 异步执行 —— 保留
- `llm_service.py` 中的 `httpx.Timeout(120.0)` —— 保留

---

## 3. 方案设计

### 3.1 整体策略

```
数据集生成（3条）→ 完整 RAG 管道（3次）→ 并行 LLM 评分（3×3=9次）→ 汇总报告
                    ↓
              进度文件实时写入 → 前端轮询 /progress → 可视化进度条
```

**预估耗时**: 3 条 × (RAG管道 ~30-60s + 3×LLM评分 ~5-15s) ≈ 2-5 分钟，在 10 分钟轮询窗口内可完成。

### 3.2 评估流程对比

| 环节 | 旧方案（轻量） | 新方案（完整 RAG） |
|------|--------------|-------------------|
| 检索 | `retrieval_service.search()` 直接调用 | 完整 RAG: 查询分类 → 改写 → HyDE → 并行检索 → RRF 融合 → CRAG |
| 生成 | `llm_service.chat()` 直接 LLM | 完整 RAG: 上下文组装 → LLM 流式生成 → 忠实度验证 |
| 评分 | 3 个 LLM 评分（并行） | 3 个 LLM 评分（并行，不变） |

### 3.3 前端进度可视化设计

在评估面板中增加进度区域，**每个查询显示当前所处的 RAG 阶段**：

```
┌──────────────────────────────────────────────────┐
│  RAGAS 质量评估                                   │
│  [生成数据集] [运行评估]                           │
│                                                  │
│  ⏳ 评估进度: 2/3                                 │
│  ████████████░░░░░░░░ 67%                        │
│                                                  │
│  ✓ 查询1: "Vue3响应式原理是什么？"                 │
│     └─ 已完成: 分类→改写→检索→CRAG→生成→忠实度校验  │
│  ⏳ 查询2: "如何使用Pinia进行状态管理？"            │
│     └─ 阶段: ████░░░░ 生成中...                   │
│        分类 ✓  改写 ✓  检索 ✓  CRAG ✓  生成 ⏳       │
│  ○ 查询3: "Vite配置代理..."                       │
│     └─ 等待中                                     │
└──────────────────────────────────────────────────┘
```

**RAG 阶段映射**（从 `chat_stream()` 的 `perf` 和 `stage` 事件捕获）：

| 事件 key | 中文标签 | 图标 |
|---------|---------|------|
| `classify` | 查询分类 | 🏷️ |
| `rewrite` / `plan` | 查询改写/规划 | ✏️ |
| `retrieve` / `retrieving` | 检索 | 🔍 |
| `crag` | CRAG评估 | 📊 |
| `generate` / `generating` | 生成回答 | 🤖 |
| `faithfulness_check` | 忠实度校验 | ✅ |
| `complete` / `pipeline` | 完成 | ✓ |

每个查询的 `per_item` 结构：
```json
{
  "query": "Vue3响应式原理是什么？",
  "status": "running",
  "current_stage": "generate",
  "stages_completed": ["classify", "rewrite", "retrieve", "crag"],
  "error": null
}
```

---

## 4. 详细实施步骤

### 步骤 1: 撤回 `_generate_answer()` + 实现完整 RAG 管道调用 + 捕获阶段事件

**文件**: `backend/app/services/evaluation_service.py`

**操作**:
1. 删除 `_generate_answer()` 方法（L134-156）
2. 在 `evaluate_dataset()` 中，将 `answer = await self._generate_answer(query, contexts)` 替换为完整 RAG 管道调用，同时捕获每个阶段事件用于进度追踪

**新代码逻辑**（在 `evaluate_dataset()` 的 for 循环中）:

```python
# 完整 RAG 管道生成答案，同时捕获阶段事件
from app.services.rag_orchestrator import rag_orchestrator

# 更新 per_item 状态为 running
per_item[i]["status"] = "running"
per_item[i]["current_stage"] = "classify"
per_item[i]["stages_completed"] = []
self._write_progress(progress_file, i + 1, len(dataset),
                     current_query=query, per_item=per_item)

answer_parts = []
contexts = []
sources_data = []

# 阶段名称映射（perf/stage 事件 → 标准化阶段名）
STAGE_MAP = {
    "classify": "classify",
    "rewrite": "rewrite",
    "plan": "rewrite",
    "retrieve": "retrieve",
    "retrieving": "retrieve",
    "crag": "crag",
    "crag_skipped": "crag",
    "generate": "generate",
    "generating": "generate",
    "faithfulness_check": "faithfulness_check",
    "complete": "complete",
    "pipeline": "complete",
}

async for event in rag_orchestrator.chat_stream(query=query, library=library):
    evt_type = event.get("type", "")

    if evt_type == "token":
        answer_parts.append(event.get("data", ""))

    elif evt_type == "source":
        sources_data = json.loads(event.get("data", "[]"))
        contexts = [s.get("content", "") for s in sources_data]

    elif evt_type in ("perf", "stage"):
        data = json.loads(event.get("data", "{}"))
        stage_key = data.get("stage", "")
        normalized = STAGE_MAP.get(stage_key, "")
        if normalized and normalized not in per_item[i]["stages_completed"]:
            per_item[i]["current_stage"] = normalized
            # 实时写入进度（每阶段更新）
            self._write_progress(progress_file, i + 1, len(dataset),
                                 current_query=query, per_item=per_item)

answer = "".join(answer_parts)
per_item[i]["stages_completed"].append("complete")
per_item[i]["current_stage"] = "complete"
```

**注意事项**:
- `rag_orchestrator.chat_stream()` 是异步生成器，遍历过程中同时收集 token、sources 和阶段事件
- 通过 `perf` 和 `stage` 事件捕获当前 RAG 阶段，实时写入进度文件
- 阶段映射表 `STAGE_MAP` 将 `chat_stream()` 的各种事件 key 标准化为 6 个阶段
- `crag` 和 `crag_skipped` 都映射到 `crag` 阶段（CRAG 评估）
- `plan`（多跳规划）和 `rewrite`（查询改写）都映射到 `rewrite` 阶段

### 步骤 2: 撤回 API 端点中的 `max_items`

**文件**: `backend/app/api/evaluation.py`

**操作**:
1. 从 `EvalRequest` 模型中删除 `max_items: int = 5` 字段
2. 在 `run_evaluation()` 的 `_run_in_background()` 中，调用 `evaluate_dataset()` 时不传 `max_items`（使用默认值 3）

### 步骤 3: 缩小数据集默认大小

**文件**: `backend/app/services/evaluation_service.py`

**操作**:
1. `evaluate_dataset()` 的 `max_items` 参数默认值从 5 改为 3
2. `generate_dataset_from_knowledge_base()` 的 `num_queries` 参数默认值从 10 改为 3

**文件**: `frontend/src/views/StatsView.vue`

**操作**:
1. `generateDataset()` 函数中 `num_queries: 10` 改为 `num_queries: 3`

### 步骤 4: 增强进度追踪（含 RAG 阶段信息）

**文件**: `backend/app/services/evaluation_service.py`

**操作**: 增强 `_write_progress()` 和 `get_progress()`，增加每个 item 的 RAG 阶段状态

**增强后的 `_write_progress()`**:

```python
def _write_progress(
    self, filepath: Path, current: int, total: int,
    current_query: str = "",
    per_item: list[dict] | None = None,
) -> None:
    """写入评估进度文件，包含每个 item 的详细状态和 RAG 阶段。"""
    progress = {
        "current": current,
        "total": total,
        "current_query": current_query,
        "per_item": per_item or [],
    }
    filepath.write_text(json.dumps(progress, ensure_ascii=False), encoding="utf-8")
```

**per_item 结构**（每个元素包含）:
```json
{
  "query": "Vue3响应式原理是什么？",
  "status": "running",          // pending | running | done | error
  "current_stage": "generate",  // classify | rewrite | retrieve | crag | generate | faithfulness_check | complete
  "stages_completed": ["classify", "rewrite", "retrieve", "crag"],
  "error": null
}
```

**在 `evaluate_dataset()` 中的使用**:
1. 循环开始前初始化 `per_item` 列表，每个 item 初始 `status: "pending"`, `current_stage: ""`, `stages_completed: []`
2. 对于当前 item (i)，写入 `status: "running"`，逐步更新 `current_stage` 和 `stages_completed`
3. 当前 item 完成后写入 `status: "done"`
4. 出错时写入 `status: "error"` 和 `error` 信息

**文件**: `backend/app/api/evaluation.py`

**操作**: 添加 `GET /evaluation/progress` 端点

```python
@router.get("/progress")
async def get_progress():
    """获取当前评估进度，包含每个查询的 RAG 阶段信息。"""
    progress = evaluation_service.get_progress()
    if progress is None:
        return {"status": "idle", "message": "暂无运行中的评估任务"}
    return progress
```

### 步骤 5: 前端进度可视化（含 RAG 阶段）

**文件**: `frontend/src/views/StatsView.vue`

**操作**:

1. **新增响应式变量和类型**:
```typescript
// RAG 阶段定义
const RAG_STAGES = [
  { key: 'classify', label: '查询分类', icon: '🏷️' },
  { key: 'rewrite', label: '查询改写', icon: '✏️' },
  { key: 'retrieve', label: '文档检索', icon: '🔍' },
  { key: 'crag', label: 'CRAG评估', icon: '📊' },
  { key: 'generate', label: '生成回答', icon: '🤖' },
  { key: 'faithfulness_check', label: '忠实度校验', icon: '✅' },
]

interface PerItem {
  query: string
  status: string          // pending | running | done | error
  current_stage: string   // classify | rewrite | retrieve | crag | generate | faithfulness_check | complete
  stages_completed: string[]
  error?: string | null
}

interface EvalProgress {
  current: number
  total: number
  current_query: string
  per_item: PerItem[]
}

const evalProgress = ref<EvalProgress | null>(null)
```

2. **修改 `pollEvaluationResult()`**: 同时轮询进度和结果
```typescript
const pollEvaluationResult = async () => {
  const maxAttempts = 120
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    await new Promise(resolve => setTimeout(resolve, 5000))
    
    // 轮询进度（含 RAG 阶段信息）
    try {
      const progressRes = await api.get('/evaluation/progress')
      if (progressRes.data && progressRes.data.status !== 'idle') {
        evalProgress.value = progressRes.data
      }
    } catch { /* 静默 */ }
    
    // 轮询结果
    try {
      const res = await api.get('/evaluation/latest')
      if (res.data && res.data.status !== 'empty') {
        if (res.data.avg_faithfulness !== undefined || res.data.faithfulness !== undefined) {
          evaluationResult.value = res.data
          evalProgress.value = null  // 清除进度
          fetchEvaluationHistory()
          return
        }
      }
    } catch { /* 继续轮询 */ }
  }
  evalError.value = '评估超时，请稍后手动刷新查看结果'
  fetchLatestEvaluation()
}
```

3. **模板**: 在评估面板中 `eval-running` 下方添加进度区域（含 RAG 阶段指示器）

```html
<!-- 评估进度可视化（含 RAG 阶段） -->
<div v-if="evalProgress" class="eval-progress">
  <!-- 总体进度条 -->
  <div class="progress-header">
    <span>评估进度: {{ evalProgress.current }}/{{ evalProgress.total }}</span>
    <span>{{ Math.round((evalProgress.current / evalProgress.total) * 100) }}%</span>
  </div>
  <div class="progress-bar-track">
    <div class="progress-bar-fill" :style="{ width: (evalProgress.current / evalProgress.total * 100) + '%' }"></div>
  </div>

  <!-- 每个查询的详细状态 -->
  <div class="progress-items">
    <div v-for="(item, idx) in evalProgress.per_item" :key="idx" class="progress-item" :class="'item-' + item.status">
      <!-- 查询标题行 -->
      <div class="progress-item-header">
        <span class="progress-item-status" :class="item.status">
          {{ item.status === 'done' ? '✓' : item.status === 'running' ? '⏳' : item.status === 'error' ? '✗' : '○' }}
        </span>
        <span class="progress-item-query">{{ item.query }}</span>
        <span v-if="item.error" class="progress-item-error">{{ item.error }}</span>
      </div>

      <!-- RAG 阶段指示器（仅 running 或 done 状态显示） -->
      <div v-if="item.status === 'running' || item.status === 'done'" class="rag-stages">
        <span
          v-for="stage in RAG_STAGES"
          :key="stage.key"
          class="rag-stage"
          :class="{
            'stage-done': item.stages_completed?.includes(stage.key),
            'stage-active': item.current_stage === stage.key,
            'stage-pending': !item.stages_completed?.includes(stage.key) && item.current_stage !== stage.key
          }"
          :title="stage.label"
        >
          {{ stage.icon }}
        </span>
      </div>
    </div>
  </div>
</div>
```

4. **CSS 样式**: 添加进度条、阶段指示器样式

```css
/* 评估进度 */
.eval-progress {
  margin-bottom: 16px;
}

.progress-header {
  display: flex;
  justify-content: space-between;
  font-size: 0.85rem;
  color: var(--ink);
  margin-bottom: 8px;
}

.progress-bar-track {
  height: 8px;
  background: var(--bg);
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 16px;
}

.progress-bar-fill {
  height: 100%;
  background: var(--accent);
  border-radius: 4px;
  transition: width 0.5s ease;
}

.progress-items {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.progress-item {
  padding: 10px 12px;
  background: var(--bg);
  border-radius: 6px;
  border-left: 3px solid var(--rule);
  transition: border-color 0.3s;
}

.progress-item.item-running {
  border-left-color: var(--accent);
}

.progress-item.item-done {
  border-left-color: var(--accent2);
}

.progress-item.item-error {
  border-left-color: var(--danger);
}

.progress-item-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.progress-item-status {
  font-size: 0.9rem;
  width: 20px;
  text-align: center;
}

.progress-item-status.running {
  color: var(--accent);
}

.progress-item-status.done {
  color: var(--accent2);
}

.progress-item-status.error {
  color: var(--danger);
}

.progress-item-query {
  font-size: 0.85rem;
  color: var(--ink);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.progress-item-error {
  font-size: 0.75rem;
  color: var(--danger);
}

/* RAG 阶段指示器 */
.rag-stages {
  display: flex;
  gap: 8px;
  padding-left: 28px;
}

.rag-stage {
  font-size: 0.8rem;
  opacity: 0.3;
  transition: opacity 0.3s;
}

.rag-stage.stage-done {
  opacity: 1;
}

.rag-stage.stage-active {
  opacity: 1;
  animation: stage-pulse 1s infinite;
}

.rag-stage.stage-pending {
  opacity: 0.25;
}

@keyframes stage-pulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.2); }
}
```

### 步骤 6: 评估期间禁用不必要的开关

**文件**: `backend/app/services/evaluation_service.py`

在 `evaluate_dataset()` 中，评估期间临时禁用：
- 语义缓存写入（避免评估结果污染缓存）
- 忠实度反馈闭环（评估不需要二次生成修正）

通过在 `rag_orchestrator.chat_stream()` 调用前设置标志位，但考虑到复杂度，此步骤可选。如果 3 条数据在 10 分钟内能完成，可跳过此优化。

---

## 5. 文件变更清单

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `backend/app/services/evaluation_service.py` | 修改 | 删除 `_generate_answer()`，替换为完整 RAG 管道；`max_items` 默认 3；增强进度追踪 |
| `backend/app/api/evaluation.py` | 修改 | 删除 `EvalRequest.max_items`；添加 `GET /progress` 端点 |
| `frontend/src/views/StatsView.vue` | 修改 | `num_queries` 改为 3；添加进度轮询和可视化 UI |
| `backend/app/services/rag_orchestrator.py` | 不改 | 仅作为依赖被调用 |
| `backend/app/core/config.py` | 不改 | 配置已就绪 |
| `frontend/src/utils/api.ts` | 不改 | 已配置代理 |

---

## 6. 验证步骤

1. 启动后端（`cd backend && .venv\Scripts\python -m uvicorn app.main:app --port 8001`）
2. 启动前端（`cd frontend && npm run dev`）
3. 打开 http://localhost:5173 → 系统监控面板
4. 点击"生成数据集" → 确认生成 3 条查询
5. 点击"运行评估" → 观察进度条实时更新
6. 等待评估完成 → 确认 5 项评分指标正确显示
7. 检查评估历史是否记录本次结果

---

## 7. 假设与决策

- **假设**: 3 条数据集 × 完整 RAG 管道能在 10 分钟内完成（预估 2-5 分钟）
- **假设**: DeepSeek API 并发 3 个评分请求不会触发限流
- **决策**: 不修改 `rag_orchestrator.chat_stream()` 的逻辑，保持评估与生产环境一致
- **决策**: 评估期间不禁用缓存和忠实度验证（保持完整管道），若仍超时再考虑精简
- **决策**: 前端轮询间隔保持 5 秒，轮询上限保持 120 次（10 分钟）