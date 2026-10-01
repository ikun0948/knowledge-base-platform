import { ref } from 'vue'

const STORAGE_KEY = 'session_id'
// 只接受 UUID 形状：后端路由不匹配含 "/" 的 id，坏 id 由构造不可达（Task 2 ruling I-2）
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

// localStorage 里只有这一个键：消息永不落本地，刷新后靠 GET /api/history 恢复（spec 五节）
export function useSession() {
  const stored = localStorage.getItem(STORAGE_KEY)
  const validStored = stored && UUID_RE.test(stored)
  const sessionId = ref(validStored ? stored : crypto.randomUUID())
  if (!validStored) localStorage.setItem(STORAGE_KEY, sessionId.value)

  function resetSession() {
    // "清空对话"要换 id（与 app.py 的行为等价）：旧 session 的历史已被 DELETE 清掉，
    // 换新 id 顺带避免"清空后立刻刷新"时和还在飞的请求抢同一个 session。
    const next = crypto.randomUUID()
    sessionId.value = next
    localStorage.setItem(STORAGE_KEY, next)
    return next
  }

  return { sessionId, resetSession }
}
