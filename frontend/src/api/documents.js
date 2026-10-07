import { ApiError, authHeaders, httpError, request } from './client.js'

export function listDocuments() {
  return request('/api/documents')
}

// 候选池一次问三条：模糊搜（query+suffix）、批量点查（parentIds，后端优先认它）、默认前 50。
// parentIds 用重复键 append：一个真 id 里可以含逗号，逗号拼接会被后端拆成两个假 id，
// 坏法是"刷新后选中项凭空少几个"而不是报错——比崩难查。
export function listChunks({ query = '', suffix = '', parentIds = [], limit = 50 } = {}) {
  const params = new URLSearchParams()
  if (query) params.set('query', query)
  if (suffix) params.set('suffix', suffix)
  for (const id of parentIds) params.append('parent_ids', id)
  if (limit !== 50) params.set('limit', String(limit))
  const qs = params.toString()
  return request(`/api/documents/chunks${qs ? `?${qs}` : ''}`)
}

// parent_id 形如 "手册 上.pdf_parent_0"：中文和空格是文件名本身带进来的，
// 不编码就会拼出非法请求行，坏法还是"404 块不存在"而不是报错。
export function deleteChunk(documentId, parentId) {
  return request(`/api/documents/${documentId}/chunks/${encodeURIComponent(parentId)}`, {
    method: 'DELETE',
  })
}

// 上传选 XMLHttpRequest 不选 fetch：fetch 没有上传方向的事件（ReadableStream 管的是读响应），
// 而 spec 6.2 要求每个文件独立的进度；阶段二的 SSE 才回到 fetch + ReadableStream，两者不冲突。
export function uploadDocument(file, { onProgress } = {}) {
  return new Promise((resolve, reject) => {
    const form = new FormData()
    form.append('file', file) // 字段名是后端 File(...) 定的：单数 file
    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/documents')
    // 这条出口不经过 request/postStream，令牌只能在这儿手动挂上去（setRequestHeader 必须在
    // open 之后、send 之前，早于 open 会被浏览器静默忽略）。没令牌就不加头，理由见 authHeaders。
    const auth = authHeaders()
    if (auth.Authorization) xhr.setRequestHeader('Authorization', auth.Authorization)
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress?.(Math.round((event.loaded / event.total) * 100))
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText))
        } catch {
          reject(new ApiError(`上传成功但响应不是 JSON（HTTP ${xhr.status}）`, xhr.status))
        }
      } else {
        // 401 也在这里通知：上传中途票过期是该自动登出的典型现场
        reject(httpError(xhr.responseText, xhr.status))
      }
    }
    xhr.onerror = () => reject(new ApiError('无法连接后端，上传中断'))
    xhr.send(form)
  })
}
