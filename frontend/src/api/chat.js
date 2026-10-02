import { postStream, request } from './client.js'

// 入参直接用后端形状，不做 camelCase 映射层。
// sendChat 是阶段一的一次性问答（Task 5 切换调用方后即删）；
// sendChatStream 对应 backend/api/chat.py 的 chat_stream：五种帧经 onEvent 逐帧回调，
// 帧序 meta → references(rag) → token* → done，中途失败以 error 帧到达（HTTP 已是 200）。
export function sendChat(payload) {
  return request('/api/chat', { method: 'POST', body: payload })
}

export function sendChatStream(payload, onEvent, { signal } = {}) {
  return postStream('/api/chat/stream', payload, onEvent, { signal })
}
