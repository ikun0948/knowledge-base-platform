import { detailFromText, request } from './client.js'

export function listDocuments() {
  return request('/api/documents')
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
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress?.(Math.round((event.loaded / event.total) * 100))
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText))
        } catch {
          reject(new Error(`上传成功但响应不是 JSON（HTTP ${xhr.status}）`))
        }
      } else {
        reject(new Error(detailFromText(xhr.responseText, xhr.status)))
      }
    }
    xhr.onerror = () => reject(new Error('无法连接后端，上传中断'))
    xhr.send(form)
  })
}
