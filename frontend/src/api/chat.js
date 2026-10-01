import { request } from './client.js'

// 入参直接用后端形状，不做 camelCase 映射层。
// 形状即 backend/api/chat.py 的实测行为：ChatRequest 三字段入，ChatResponse 出（answer/references/mode），
// 失败 502 {"detail"}（RetrievalError/LLMError 就地转，其余领域错误走中央映射）。
export function sendChat(payload) {
  return request('/api/chat', { method: 'POST', body: payload })
}
