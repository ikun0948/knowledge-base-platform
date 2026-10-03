import { computed, ref } from 'vue'

import { listDocuments, uploadDocument } from '../api/documents.js'

const UPLOAD_STATUS = { pending: 'pending', uploading: 'uploading', ok: 'ok', fail: 'fail' }

// 坑 5：同名文档必须靠 id 区分，这个格式是界面上唯一的出处（M-F2 收口：ReferenceList 也走这里）。
// 两种入参形状：文档行用 id，后端引用的 Reference 用 document_id。
export function docLabel(doc) {
  return `${doc.filename}(#${doc.id ?? doc.document_id})`
}

export function useDocuments() {
  const documents = ref([])
  const selectedIds = ref([])
  const queue = ref([])
  const listError = ref('')
  let running = false

  const docCount = computed(() => documents.value.length)

  async function refresh() {
    try {
      documents.value = await listDocuments()
      listError.value = ''
      // 勾过的文档不在列表里了就要撤勾：留着会让 document_ids 带上后端不认的 id，问答直接 502
      const alive = new Set(documents.value.map((doc) => doc.id))
      selectedIds.value = selectedIds.value.filter((id) => alive.has(id))
    } catch (err) {
      listError.value = err.message
    }
  }

  function toggleSelect(id) {
    selectedIds.value = selectedIds.value.includes(id)
      ? selectedIds.value.filter((x) => x !== id)
      : [...selectedIds.value, id]
  }

  function enqueue(files) {
    const stamp = Date.now()
    queue.value.push(
      ...Array.from(files).map((file, index) => ({
        key: `${stamp}-${index}-${file.name}`,
        file,
        name: file.name,
        percent: 0,
        status: UPLOAD_STATUS.pending,
        error: '',
      })),
    )
    runQueue()
  }

  async function runQueue() {
    if (running) return
    running = true
    try {
      // 串行而不是 Promise.all：后端只有单文件端点（spec 6.2），
      // 并行会让 embedding 与 MySQL 写互相排队，进度条也会跳成乱序
      for (;;) {
        // 从 queue.value 里取到的是响应式代理，直接改字段就能推动进度条
        const item = queue.value.find((q) => q.status === UPLOAD_STATUS.pending)
        if (!item) break
        item.status = UPLOAD_STATUS.uploading
        item.percent = 0
        item.error = ''
        try {
          await uploadDocument(item.file, { onProgress: (percent) => { item.percent = percent } })
          item.percent = 100
          item.status = UPLOAD_STATUS.ok
          await refresh()
        } catch (err) {
          item.status = UPLOAD_STATUS.fail
          item.error = err.message
        }
      }
    } finally {
      running = false
    }
  }

  function retry(item) {
    item.status = UPLOAD_STATUS.pending
    item.percent = 0
    item.error = ''
    runQueue()
  }

  function dismiss(item) {
    queue.value = queue.value.filter((q) => q.key !== item.key)
  }

  return {
    documents,
    selectedIds,
    queue,
    listError,
    docCount,
    refresh,
    toggleSelect,
    enqueue,
    retry,
    dismiss,
    docLabel,
  }
}
