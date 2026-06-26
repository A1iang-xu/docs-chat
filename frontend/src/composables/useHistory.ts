/**
 * v4.4: 查询历史管理 Composable
 * 使用 localStorage 持久化最近 20 条查询
 */
import { ref, watch } from 'vue'

export interface HistoryItem {
  id: string
  query: string
  library: string | null
  timestamp: number
}

const STORAGE_KEY = 'docschat_history'
const MAX_ITEMS = 20

const history = ref<HistoryItem[]>(loadHistory())

function loadHistory(): HistoryItem[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    return JSON.parse(raw) as HistoryItem[]
  } catch {
    return []
  }
}

function saveHistory() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(history.value))
  } catch {
    // localStorage 可能已满或被禁用
  }
}

watch(history, saveHistory, { deep: true })

export function useHistory() {
  function add(query: string, library: string | null = null) {
    if (!query.trim()) return

    // 去重：如果已有相同查询，移除旧的
    const filtered = history.value.filter(
      (item) => !(item.query === query && item.library === library),
    )

    const item: HistoryItem = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      query: query.trim(),
      library,
      timestamp: Date.now(),
    }

    history.value = [item, ...filtered].slice(0, MAX_ITEMS)
  }

  function remove(id: string) {
    history.value = history.value.filter((item) => item.id !== id)
  }

  function clear() {
    history.value = []
  }

  return { history, add, remove, clear }
}
