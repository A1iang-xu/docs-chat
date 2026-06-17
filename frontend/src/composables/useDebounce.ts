/**
 * useDebounce —— 防抖 Composable
 * 用于搜索输入、窗口 resize 等高频事件
 */
import { ref, watch, onUnmounted } from 'vue'

export function useDebounce<T>(source: () => T, delay: number = 300) {
  const debounced = ref(source()) as { value: T }
  let timer: ReturnType<typeof setTimeout> | null = null

  watch(
    source,
    (val) => {
      if (timer) clearTimeout(timer)
      timer = setTimeout(() => {
        debounced.value = val
      }, delay)
    },
    { immediate: true },
  )

  onUnmounted(() => {
    if (timer) clearTimeout(timer)
  })

  return debounced
}