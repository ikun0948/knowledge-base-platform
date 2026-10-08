import { computed, ref } from 'vue'

import { listChunks } from '../api/documents.js'
import { MAX_ID_CHARS, MAX_SELECTED_CHUNKS } from '../constants.js'

const STORAGE_KEY = 'selected_parent_ids'

// localStorage 是用户能亲手改的地方（DevTools、上个版本的残留），坏值必须在这道关口
// 就被丢掉，而不是带着进请求 URL——同 useSession 的"坏值构造不可达"，别等后端 422。
function readStoredIds() {
  let raw
  try {
    raw = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]')
  } catch {
    return []
  }
  if (!Array.isArray(raw)) return []
  const clean = raw.filter((id) => typeof id === 'string' && id.length > 0 && id.length <= MAX_ID_CHARS)
  return [...new Set(clean)].slice(0, MAX_SELECTED_CHUNKS)
}

function writeStoredIds(ids) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(ids))
}

export function useChunkSelection() {
  const selectedChunks = ref([])
  const pickerOpen = ref(false)
  const selectionError = ref('')

  const selectedParentIds = computed(() => selectedChunks.value.map((c) => c.parent_id))
  const selectedCount = computed(() => selectedChunks.value.length)

  function persist() {
    writeStoredIds(selectedParentIds.value)
  }

  async function hydrate() {
    const ids = readStoredIds()
    if (!ids.length) {
      selectedChunks.value = []
      selectionError.value = ''
      return
    }
    try {
      const rows = await listChunks({ parentIds: ids })
      const byId = new Map(rows.map((row) => [row.parent_id, row]))
      // 按存下来的顺序重建，并剪掉后端没返回的：那是已删/已隐存的块，留着等于发一个必空召回的请求
      selectedChunks.value = ids.map((id) => byId.get(id)).filter(Boolean)
      // 剪过就要回写，否则下次刷新再剪一次，坏值永远赖在本地
      persist()
    } catch (err) {
      // 一次网络失败不该把面板清空：保留已有集合，只把错误说出来
      selectionError.value = err.message
    }
  }

  function isSelected(parentId) {
    return selectedChunks.value.some((c) => c.parent_id === parentId)
  }

  function toggle(chunk) {
    const i = selectedChunks.value.findIndex((c) => c.parent_id === chunk.parent_id)
    if (i !== -1) {
      selectedChunks.value.splice(i, 1)
      selectionError.value = ''
    } else {
      if (selectedChunks.value.length >= MAX_SELECTED_CHUNKS) {
        selectionError.value = `最多只能选择 ${MAX_SELECTED_CHUNKS} 个文档块，请先取消几个再添加。`
        return
      }
      selectedChunks.value.push(chunk)
      selectionError.value = ''
    }
    persist()
  }

  function remove(parentId) {
    selectedChunks.value = selectedChunks.value.filter((c) => c.parent_id !== parentId)
    persist()
  }

  function clearSelection() {
    selectedChunks.value = []
    persist()
  }

  return {
    selectedChunks, selectedParentIds, selectedCount, pickerOpen, selectionError,
    hydrate, toggle, remove, isSelected, clearSelection,
  }
}
