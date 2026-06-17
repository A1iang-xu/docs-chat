/**
 * useVirtualScroll — 虚拟滚动管理
 * 在消息列表过长时只渲染可视区域，避免 DOM 节点过多导致卡顿
 */
import { ref, computed, onMounted, onUnmounted, type Ref } from 'vue'

export interface VirtualScrollOptions {
  /** 每项估计高度 (px) */
  itemHeight: number
  /** 缓冲区项数（渲染区外的额外项） */
  overscan: number
}

export function useVirtualScroll(
  containerRef: Ref<HTMLElement | null>,
  totalItems: Ref<number>,
  options: VirtualScrollOptions = { itemHeight: 80, overscan: 5 },
) {
  const { itemHeight, overscan } = options

  const scrollTop = ref(0)
  const containerHeight = ref(0)

  // 可视区域能容纳的项数
  const visibleCount = computed(() => Math.ceil(containerHeight.value / itemHeight) + overscan * 2)

  // 起始索引
  const startIndex = computed(() => {
    const raw = Math.floor(scrollTop.value / itemHeight) - overscan
    return Math.max(0, raw)
  })

  // 结束索引
  const endIndex = computed(() => {
    const raw = startIndex.value + visibleCount.value
    return Math.min(totalItems.value, raw)
  })

  // 可见项索引范围
  const visibleRange = computed(() => ({
    start: startIndex.value,
    end: endIndex.value,
  }))

  // 总高度偏移（上方隐藏项的高度）
  const offsetY = computed(() => startIndex.value * itemHeight)

  function onScroll(event: Event) {
    scrollTop.value = (event.target as HTMLElement).scrollTop
  }

  function updateContainerHeight() {
    if (containerRef.value) {
      containerHeight.value = containerRef.value.clientHeight
    }
  }

  onMounted(() => {
    updateContainerHeight()
    window.addEventListener('resize', updateContainerHeight)
  })

  onUnmounted(() => {
    window.removeEventListener('resize', updateContainerHeight)
  })

  return {
    scrollTop,
    containerHeight,
    visibleRange,
    offsetY,
    totalHeight: computed(() => totalItems.value * itemHeight),
    onScroll,
  }
}