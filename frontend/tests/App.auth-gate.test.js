// App.vue 的登录门禁、enterWorkspace() 的请求顺序、登出的清键——本 Task 里 spec 5.1/5.3 在界面上
// 唯一的实现处，之前只有 build 和注释担保（谁删掉 clearSession()、或把整屏 v-if 换成"渲染但禁用"，
// 没有测会红）。2026-10-07 修正轮 1 补上第一道自动化。
//
// 口径（工单 I-2 明写的两条反例都不走）：
//   ① 不 vi.mock 任何 composable。mock 五个再断言调用次数，测的是 mock 不是接线——
//      App.vue 换成另一套同样正确的编排照样绿。这里只 vi.stubGlobal('fetch', …) 一个
//      按 URL 记账的假实现，然后走真实的 useAuth.bootstrap() / useSession / useDocuments /
//      useChunkSelection / useChat，请求顺序由各 composable 的真实实现产生。
//   ② 不读源码字符串做包含断言。那种东西只会在重构时挡住正确的改写。
//
// 已知环境事实（都写死在本文件里，不靠运气）：
//   - 这里没有 Vite 代理，fetch 全被 stub 接管：**任何测都不许真出网**。未知 URL 也记账，
//     并回一个 200 空数组兜底——这样"多打了一枪"表现为记账里多一条 unknown，
//     而不是变成一条 JSON 解析报错（那种红查起来只会让人以为测写坏了）。
//   - useAuth 的 user/authError/authBusy（useAuth.js:15-17）、useSession 的 sessionId
//     （useSession.js:20）、api/client.js 的 authToken 都是**模块级**状态，同一个文件里三个
//     it() 共享它们。收口方式：不用 vi.resetModules() 重取模块（那会连 vue 一起换成第二份运行时，
//     跨份的 ref 不再触发重渲染），而是 **beforeEach 显式归零 + 每条 it() 自己建立前置条件**
//     （清 localStorage / 塞令牌）。it() 的书写顺序因此不承载任何判据——
//     --sequence.shuffle 与物理倒序两个方向都验过（见报告）。
//   - jsdom 原生 window.confirm 只在 handleClear 里用，本轮不碰那条路径，也没往 stub 里塞 confirm。
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import App from '../src/App.vue'
import { setAuthToken } from '../src/api/client.js'
import { useAuth } from '../src/composables/useAuth.js'
import { useSession } from '../src/composables/useSession.js'

// 形状必须过 useAuth.js:9 的 TOKEN_RE = /^[A-Za-z0-9_-]{32,}$/，43 位是后端 token_urlsafe(32) 的长度
const TOKEN = 'a'.repeat(43)
const SID = '3f2b1c00-1111-2222-3333-444455556666'
const CHUNK = { parent_id: '手册.pdf_parent_0', document_id: 7, filename: '手册.pdf',
                suffix: 'pdf', snippet: '片段一', child_count: 3 }
const ME = { user: { id: 1, identifier: 'a@b.com', identifier_type: 'email', nickname: '小明', avatar: 'auto' } }
// 上一个账号的文档与历史：登出的"不残留"就靠它们做探针
const DOC = { id: 42, filename: '上一个账号的文档.pdf', size: 1 }
const HISTORY_ROWS = [
  { role: 'user', content: '上一个账号的问题', references: null, mode: null },
  { role: 'assistant', content: '上一个账号的答案', references: [], mode: 'rag' },
]

// 前缀按长度降序：'/api/documents' 会吃掉 '/api/documents/chunks'，认错了就是一条兜底空体。
// label = "哪一拍"：query 串里带着 percent-encoded 的中文 parent_id 与 session id，
// 拿原始 URL 断顺序会把判据绑在编码细节上——那一层由 documents-api.test.js 与 client.test.js 管。
const ROUTES = [
  { prefix: '/api/documents/chunks', label: 'chunks', status: 200, body: [CHUNK] },
  { prefix: '/api/auth/logout', label: 'logout', status: 204, body: null },
  { prefix: '/api/history/', label: 'history', status: 200, body: HISTORY_ROWS },
  { prefix: '/api/auth/me', label: 'me', status: 200, body: ME },
  { prefix: '/api/documents', label: 'documents', status: 200, body: [DOC] },
]

function matchRoute(url) {
  return ROUTES.find((route) => url.startsWith(route.prefix)) ?? null
}

let calls = []
let wrapper = null

const hits = () => calls.map((c) => matchRoute(c.url)?.label ?? `unknown:${c.url}`)

function makeResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => 'application/json' },
    json: async () => body,
    text: async () => (body === null ? '' : JSON.stringify(body)),
  }
}

// 唯一的桩：按 URL 记账 + 按前缀回形状正确的 200 体（204 给登出）
function stubFetch() {
  calls = []
  vi.stubGlobal('fetch', async (input, init = {}) => {
    const url = String(typeof input === 'string' ? input : (input?.url ?? input))
    calls.push({ url, method: init.method ?? 'GET' })
    const route = matchRoute(url)
    return route ? makeResponse(route.status, route.body) : makeResponse(200, [])
  })
}

async function mountApp() {
  wrapper = mount(App)
  await flushPromises()
  return wrapper
}

// 已登录的本地状态：令牌过 TOKEN_RE、session 用固定 uuid、选中项留一条让 hydrate 非空
function seedLoggedIn() {
  localStorage.setItem('auth_token', TOKEN)
  localStorage.setItem('session_id', SID)
  // hydrate() 只在本地有选中 id 时才打一枪 /api/documents/chunks（useChunkSelection.js:41-45）；
  // 不塞这个键，第三拍之前那一枪就不存在，顺序判据会退化成"两拍"。
  localStorage.setItem('selected_parent_ids', JSON.stringify([CHUNK.parent_id]))
}

describe('App：登录门禁 / 请求顺序 / 登出清键（Task 7 修正轮 1）', () => {
  beforeEach(() => {
    localStorage.clear()
    // 模块级状态归零：这几句让每个 it() 的前置条件与上一个 it() 写过什么无关
    const { authBusy, authError, clearAuth } = useAuth()
    clearAuth()
    authError.value = ''
    authBusy.value = false
    setAuthToken('')
    useSession().sessionId.value = SID
    stubFetch()
  })

  afterEach(() => {
    wrapper?.unmount()
    wrapper = null
    vi.unstubAllGlobals()
  })

  it('手上没令牌：整屏只有登录页，且一个非 /api/auth/ 的请求都不发', async () => {
    // 钉两处：App.vue 的整屏 v-if 门禁（spec 5.1，"渲染出来但禁用"是已被否决的写法）
    // 与 onMounted 的 bootstrap() 空令牌分支（spec 5.2）。
    const screen = await mountApp()
    expect(screen.find('.auth-screen').exists()).toBe(true)
    expect(screen.find('.user-rail').exists()).toBe(false)
    expect(screen.find('.app-shell').exists()).toBe(false)
    // 判据本体：记账里一条非 /api/auth/ 的 URL 都没有
    expect(calls.filter((c) => !c.url.startsWith('/api/auth/'))).toEqual([])
    // 此刻连 /api/auth/ 也该是零——readToken() 的空值分支根本不发请求（比上面那条更强，今天成立）
    expect(hits()).toEqual([])
  })

  it('带着合法令牌进来：me → documents → chunks → history 四枪按序，工作区才出现', async () => {
    // 钉 enterWorkspace() 的 refresh → hydrate → restore 不变式（原先只活在注释里）：
    // hydrate 的那枪必须早于 restore，这样"选中项已被剪掉"先于历史渲染，错误横幅只剩最后一条真的。
    seedLoggedIn()
    const workspace = await mountApp()
    expect(hits()).toEqual(['me', 'documents', 'chunks', 'history'])
    // 登录后整屏换成工作区：用户栏在、登录页没
    expect(workspace.find('.user-rail').exists()).toBe(true)
    expect(workspace.find('.auth-screen').exists()).toBe(false)
    // 顺带证明 restore 打的是本地那个 id（不是又被换掉的随机值）
    expect(calls.at(-1).url).toContain(SID)
    expect(localStorage.getItem('session_id')).toBe(SID)
  })

  it('点「退出登录」：logout 发过、auth_token 与 session_id 都不在、界面回到登录页', async () => {
    // 钉 handleSignOut 的清理组（spec 5.3"登出把两个键一起清"在界面上的唯一实现处）
    seedLoggedIn()
    const app = await mountApp()
    // 前置事实：三拍真的把上一个账号的东西渲染出来了——否则"消失了"这条判据是空的
    expect(app.find('.user-rail').exists()).toBe(true)
    expect(app.text()).toContain('上一个账号的答案')
    expect(localStorage.getItem('auth_token')).toBe(TOKEN)
    expect(localStorage.getItem('session_id')).toBe(SID)
    // 前置事实（vm 层）：三拍把上一个账号的东西写进了组件实例的 ref。
    // 走 VTU 的 setupState 通道读 app.vm.*——读的是组件实例、不是 composable 模块，
    // 不违反本文件"不 mock composable"的口径。
    // 实数由桩的形状决定：/api/documents 回 1 篇（DOC）、队列没有任何入队入口、
    // /api/history 回 HISTORY_ROWS 2 行。queue 这一格是给下面归零断言的对照，不钉 enqueue。
    expect({
      documents: app.vm.documents.length,
      queue: app.vm.queue.length,
      messages: app.vm.messages.length,
    }).toEqual({ documents: 1, queue: 0, messages: 2 })

    // X-3 的判据并进这里（不另开 it()）：登出前挂一句上一次登录失败的文案
    const { authError } = useAuth()
    authError.value = '上一次失败的文案'

    await app.find('.rail-signout').trigger('click')
    await flushPromises()

    expect(calls.filter((c) => c.url.startsWith('/api/auth/logout') && c.method === 'POST')).toHaveLength(1)
    // 两个键一起清（spec 5.3）——这一句是 clearSession() 的直接判据
    expect(localStorage.getItem('auth_token')).toBe(null)
    expect(localStorage.getItem('session_id')).toBe(null)
    // clearSelection() 也要有牙：只有它会把 selected_parent_ids 回写成空数组
    expect(localStorage.getItem('selected_parent_ids')).toBe('[]')
    // 整屏回到登录页
    expect(app.find('.auth-screen').exists()).toBe(true)
    expect(app.find('.user-rail').exists()).toBe(false)
    expect(app.find('.app-shell').exists()).toBe(false)
    // 登出清空三句（App.vue 的 documents.value = [] / queue.value = [] / messages.value = []）的
    // **唯一判据就是下面这三句 vm 层断言**：DOM 层观测不到——登出时 clearAuth() 置 user = null，
    // `.app-shell` 连同 DocumentPanel / MessageList 整棵卸载，屏上没有残留可断。
    // 这里原本是一条 `findAll('.queue-item')` 长度 0 的 DOM 断言，**永久绿**（那个场景从头到尾
    // 没有队列项，`.queue-item` 只由 FileUploader 在入队后渲染），2026-10-07 收掉、改由 vm 层钉。
    expect(app.vm.documents).toEqual([])
    expect(app.vm.queue).toEqual([])
    expect(app.vm.messages).toEqual([])
    // X-3：authError 由 handleSignOut 清掉。
    // 照实说：DOM 那一句单独不构成判据——重挂的 AuthPanel 表单为空，「请填写账号」会压住后端文案，
    // 残留本来就在屏上看不见。有牙的是 authError 这个模块级 ref 本身。两句都留着：
    // 前者钉"屏上不许出现那句旧文案"，后者钉"状态里不许留着它"。
    expect(authError.value).toBe('')
    expect(app.find('.picker-error').text()).not.toContain('上一次失败的文案')
  })
})
