/**
 * v4.5: 主题管理 Composable
 * 支持 暗色/亮色/跟随系统 三种模式
 * localStorage 持久化用户选择
 */
import { ref, watch, computed } from 'vue'

type ThemeMode = 'dark' | 'light' | 'system'

const STORAGE_KEY = 'docschat_theme'
const themeMode = ref<ThemeMode>(loadThemeMode())
const resolvedTheme = ref<'dark' | 'light'>(resolveTheme(themeMode.value))

function loadThemeMode(): ThemeMode {
  try {
    const saved = localStorage.getItem(STORAGE_KEY) as ThemeMode | null
    if (saved && ['dark', 'light', 'system'].includes(saved)) {
      return saved
    }
  } catch {
    // localStorage 不可用
  }
  return 'dark' // 默认暗色（项目原有风格）
}

function resolveTheme(mode: ThemeMode): 'dark' | 'light' {
  if (mode === 'system') {
    return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
  }
  return mode
}

function applyTheme(theme: 'dark' | 'light') {
  document.documentElement.classList.toggle('dark', theme === 'dark')
}

// 监听系统主题变化（当 mode=system 时）
if (window.matchMedia) {
  window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', (e) => {
    if (themeMode.value === 'system') {
      resolvedTheme.value = e.matches ? 'light' : 'dark'
    }
  })
}

// 监听主题变化，应用到 DOM
watch(resolvedTheme, (newTheme) => {
  applyTheme(newTheme)
}, { immediate: true })

// 监听模式变化，持久化并重新解析
watch(themeMode, (newMode) => {
  try {
    localStorage.setItem(STORAGE_KEY, newMode)
  } catch {
    // ignore
  }
  resolvedTheme.value = resolveTheme(newMode)
})

export function useTheme() {
  function setTheme(mode: ThemeMode) {
    themeMode.value = mode
  }

  function toggleTheme() {
    const next: Record<ThemeMode, ThemeMode> = {
      dark: 'light',
      light: 'system',
      system: 'dark',
    }
    themeMode.value = next[themeMode.value]
  }

  const themeIcon = computed(() => {
    switch (themeMode.value) {
      case 'dark': return '🌙'
      case 'light': return '☀️'
      case 'system': return '💻'
    }
  })

  const themeLabel = computed(() => {
    switch (themeMode.value) {
      case 'dark': return '暗色'
      case 'light': return '亮色'
      case 'system': return '跟随系统'
    }
  })

  return {
    themeMode,
    resolvedTheme,
    themeIcon,
    themeLabel,
    setTheme,
    toggleTheme,
  }
}
