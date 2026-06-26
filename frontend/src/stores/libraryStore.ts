import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/utils/api'

export interface Library {
  library: string
  version: string
  chunk_count: number
  source_url?: string
}

export const useLibraryStore = defineStore('library', () => {
  const libraries = ref<Library[]>([])
  const selectedLibrary = ref<string | null>(null)  // null = 全部库
  const loading = ref(false)

  function setSelected(lib: string | null) {
    selectedLibrary.value = lib
    try {
      localStorage.setItem('v4_library', lib || '__all__')
    } catch { /* localStorage may be unavailable */ }
  }

  function restore() {
    try {
      const saved = localStorage.getItem('v4_library')
      selectedLibrary.value = saved === '__all__' || !saved ? null : saved
    } catch {
      selectedLibrary.value = null
    }
  }

  async function fetchLibraries() {
    loading.value = true
    try {
      const { data } = await api.get('/libraries/')
      libraries.value = Array.isArray(data) ? data : []
    } catch {
      libraries.value = []
    } finally {
      loading.value = false
    }
  }

  return { libraries, selectedLibrary, loading, setSelected, restore, fetchLibraries }
})
