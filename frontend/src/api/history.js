import { request } from './client.js'

// 形状即 backend/api/history.py 的实测行为：GET 返回"一行 DB 展开成 user + assistant 两条"的列表（spec 6.2 第 3 条），
// user 行的 references 为 null，assistant 行为数组（used_chunks 脏数据已降级成 []）。
export function getHistory(sessionId, limit = 50) {
  // session_id 进路径段。值本该是 UUID，但 localStorage 可被手改成含 "/" 的串，编一下才不会莫名 404
  return request(`/api/history/${encodeURIComponent(sessionId)}?limit=${limit}`)
}

export function clearHistory(sessionId) {
  return request(`/api/history/${encodeURIComponent(sessionId)}`, { method: 'DELETE' })
}
