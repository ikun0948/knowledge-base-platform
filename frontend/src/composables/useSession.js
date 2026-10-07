import { ref } from 'vue'

const STORAGE_KEY = 'session_id'
// 只接受 UUID 形状：后端路由不匹配含 "/" 的 id，坏 id 由构造不可达（Task 2 ruling I-2）
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

// localStorage 里三个键（auth_token / session_id / selected_parent_ids）中这一个归这里管。
// 消息永不落本地，刷新后靠 GET /api/history 恢复（spec 五节）。
function validOrFresh(raw) {
  if (raw && UUID_RE.test(raw)) return raw
  const fresh = crypto.randomUUID()
  localStorage.setItem(STORAGE_KEY, fresh)
  return fresh
}

// ref 必须在模块作用域：Task 7 之后 App.vue 与 AuthPanel 都要读写它——
// 放函数里就是两个互不相干的副本，后端铸造的对话 id 落了盘却没进界面，
// 症状是"换了账号历史却没换"，正好是需求 2 的反面。
// （对照 useChunkSelection：那个的 ref 留在函数内，因为它只被 App.vue 一处持有。）
const sessionId = ref(validOrFresh(localStorage.getItem(STORAGE_KEY)))

export function useSession() {
  function persist(next) {
    // 外部塞进来的坏值一律换成 uuid，而不是原样落盘：
    // setSession 的入参来自 HTTP 响应，那已经是"不完全可信"的边界
    const safe = typeof next === 'string' && UUID_RE.test(next) ? next : crypto.randomUUID()
    sessionId.value = safe
    localStorage.setItem(STORAGE_KEY, safe)
    return safe
  }

  // 登录/注册成功时用后端 uuid4() 铸造的那个 id 覆盖本地（spec 5.3）：
  // 重新登录就是新对话，刷新不会走到这里所以对话不丢。
  function setSession(next) {
    return persist(next)
  }

  function resetSession() {
    // "清空对话"要换 id（与归档 app.py 等价）：旧 session 的历史已被 DELETE 清掉，
    // 换新 id 顺带避免"清空后立刻刷新"时和还在飞的请求抢同一个 session。
    return persist(crypto.randomUUID())
  }

  function clearSession() {
    // 登出时 auth_token 与 session_id 一起清（spec 5.3）。键删掉即可，
    // ref 仍留一个合法 uuid：界面此刻是登录页，不许出现空 id 这种半吊子状态。
    localStorage.removeItem(STORAGE_KEY)
    sessionId.value = crypto.randomUUID()
    return sessionId.value
  }

  return { sessionId, setSession, resetSession, clearSession }
}
