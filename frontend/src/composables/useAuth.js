import { computed, ref } from 'vue'

import { getMe, login as apiLogin, logout as apiLogout, register as apiRegister } from '../api/auth.js'
import { setAuthToken } from '../api/client.js'

const TOKEN_KEY = 'auth_token'
// 令牌原文是 secrets.token_urlsafe(32)，长度恒为 43；下限收到 32 只为挡掉
// DevTools 里手敲的 "1"、上个版本残留的 UUID 这类坏值（同 useSession 的 UUID_RE 口径）。
const TOKEN_RE = /^[A-Za-z0-9_-]{32,}$/

// 状态放模块级而不是函数内：App.vue、AuthPanel.vue 与 Task 7 的 .user-rail 都要读它，
// 而这个项目不引 Pinia（spec 5.1）。函数内各造 ref 的话，退出只清掉一份副本。
// 这与 useChunkSelection 相反——那个的 selectedChunks 是函数内 ref，因为只有 App.vue 一处持有；
// 这里三处要读，所以必须上移到模块作用域。别照着 useChunkSelection 抄回函数内。
const user = ref(null)
const authError = ref('')
const authBusy = ref(false)

function readToken() {
  const raw = localStorage.getItem(TOKEN_KEY)
  return raw && TOKEN_RE.test(raw) ? raw : ''
}

function applySession(token, nextUser) {
  localStorage.setItem(TOKEN_KEY, token)
  setAuthToken(token)
  user.value = nextUser
  authError.value = ''
}

export function useAuth() {
  const isLoggedIn = computed(() => user.value !== null)

  async function bootstrap() {
    // 启动流程的第一拍（spec 5.2）：手上没令牌就一个请求都不发。
    // 返回真表示"确认已登录"，App.vue 只有在这个前提下才去跑 refresh/hydrate/restore。
    const token = readToken()
    if (!token) {
      // 走完整的 clearAuth() 而不是只 setAuthToken('')：手上那枚形状不合格的值（DevTools 里手敲的、
      // 上个版本残留的 UUID）留在 localStorage 里就是永久的残留，模块级 user 也该跟着落回未登录，
      // 否则"没令牌"这条分支只清了网络层、没清账号态。返回值仍是布尔 false（clearAuth 回 undefined）。
      clearAuth()
      return false
    }
    setAuthToken(token)
    try {
      const body = await getMe()
      user.value = body.user
      return true
    } catch {
      // 401、网络失败、代理宕机(502) 都走这里：清掉坏票静默落回登录页。
      // 不弹横幅——"你上次登录的票过期了"对用户没有可行动信息，只会让人以为服务坏了。
      clearAuth()
      return false
    }
  }

  async function signUp(payload) {
    // 不 catch：错误原样上抛给调用方（Task 7 的 App.vue），由它写进 authError。
    // 这里吞掉就等于替界面决定了"报错怎么显示"，而 authError 是模块级、三处共享的。
    authBusy.value = true
    try {
      const body = await apiRegister(payload)
      applySession(body.token, body.user)
      return body.session_id   // App.vue 拿它覆盖 localStorage 的 session_id（spec 5.3）
    } finally {
      authBusy.value = false
    }
  }

  async function signIn(payload) {
    // 同上：try/finally 不是 try/catch，登录失败的文案归调用方。
    authBusy.value = true
    try {
      const body = await apiLogin(payload)
      applySession(body.token, body.user)
      return body.session_id
    } finally {
      authBusy.value = false
    }
  }

  async function signOut() {
    try {
      await apiLogout()   // 204：request 那层的空响应体处理让它回 null，不是报错
    } catch {
      // 后端删不掉令牌也算本地退出，这里没有要渲染的消息：登出不像登录有 authError 这条文案出口，
      // 401（票早过期）与 502（uvicorn 重启时代理回空体）都是用户点退出时的常态路径。
      // 上抛的代价由 Task 7 付：handleSignOut 在 `await signOut()` 之后才 clearSession()、
      // 才清 documents/queue/messages/clearSelection()，一抛就全跳过，而 v-if 因为 finally
      // 跑过照样翻回登录页——留下无人察觉的跨用户残留。
      // 注意分工：finally 保证清理一定发生，catch 保证不打断调用方；两者缺一不可。
    } finally {
      // 后端删不掉也算本地退出：令牌可能已经过期、服务可能正在重启，
      // 而这些都不该成为"我点了退出却还留在这个账号里"的理由。
      clearAuth()
    }
  }

  function clearAuth() {
    localStorage.removeItem(TOKEN_KEY)
    setAuthToken('')
    user.value = null
  }

  return { user, authError, authBusy, isLoggedIn, bootstrap, signUp, signIn, signOut, clearAuth }
}
