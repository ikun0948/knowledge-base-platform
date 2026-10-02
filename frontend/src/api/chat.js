import { postStream } from './client.js'

// 入参直接用后端形状，不做 camelCase 映射层。
// sendChatStream 对应 backend/api/chat.py 的 chat_stream：五种帧经 onEvent 逐帧回调，
// 帧协议见 spec 6.4（meta 立即先发 → references 仅 rag 链且先于一切 token → token×N → done；
// meta 后任何失败 → error {detail} 后流关闭）。
// 非流版 sendChat 已在阶段二 Task 5 删除：回退路径由后端 /api/chat 保留端点本身承担，
// 前端不再引用它（spec 十一节第 7→6 步回退只需把 useChat 换回一次 POST 拿整包）。
export function sendChatStream(payload, onEvent, { signal } = {}) {
  return postStream('/api/chat/stream', payload, onEvent, { signal })
}
