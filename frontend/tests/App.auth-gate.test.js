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
//     （useSession.js:20）、api/client.js 的 authToken 都是**模块级**状态，同一个文件里六个
//     it() 共享它们。收口方式：不用 vi.resetModules() 重取模块（那会连 vue 一起换成第二份运行时，
//     跨份的 ref 不再触发重渲染），而是 **beforeEach 显式归零 + 每条 it() 自己建立前置条件**
//     （清 localStorage / 塞令牌）。it() 的书写顺序因此不承载任何判据——
//     --sequence.shuffle 与物理倒序两个方向都验过（见报告）。
//   - jsdom 原生 window.confirm 只在 handleClear 里用，本轮不碰那条路径，也没往 stub 里塞 confirm。
import { nextTick } from 'vue'
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
// 十键 = backend/schemas/auth.py 的 UserOut 一字不差（阶段二起后五键由 _user_out 组装）。
// `.rail-avatar` 读 avatar、设置弹窗回填读 models/api_key_masked、Task 11 的横幅读
// llm_configured 与 models——少给一键的表征不是红，是"读 undefined 走了 falsy 分支"：
// 横幅永远不出现，那条判据假绿。取值与 SettingsModal.test.js 同套。
// over 用于造变体（未配 key / 名单为空），十键的默认值就是"全配齐"的那个人。
function meUser(over = {}) {
  return {
    id: 1, identifier: 'a@b.com', identifier_type: 'email', nickname: '小明', avatar: 'auto',
    llm_configured: true, llm_base_url: 'https://fake/v1', api_key_masked: 'sk-****7890',
    // 两个模型不是笔误：Task 10 那条"下拉换模型 → 载荷跟着换"需要**第二个 option 可换**，
    // 名单只有一项时 select.setValue 找不到目标，测会红在桩上而不是红在接线上。
    models: ['qwen-max', 'qwen-turbo'], default_model: 'qwen-max',
    ...over,
  }
}
const ME = { user: meUser() }
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
    calls.push({ url, method: init.method ?? 'GET', body: init.body })
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
    // Task 10：先真的换一个模型，下面的 modelOverride 归零断言才有牙
    // （不选就永远是 ''，那句断言就成了永久绿——与 settingsOpen 那条的处理同一个道理）
    await app.find('.model-select').setValue('qwen-turbo')
    expect(app.vm.modelOverride).toBe('qwen-turbo')

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
    // Task 10：modelOverride 走的是同一组清理（上面刚把它换成 qwen-turbo）。
    // DOM 观测不到——此刻 .app-shell 已经整棵卸载，下拉框本身都不存在了。
    expect(app.vm.modelOverride).toBe('')
    // X-3：authError 由 handleSignOut 清掉。
    // 照实说：DOM 那一句单独不构成判据——重挂的 AuthPanel 表单为空，「请填写账号」会压住后端文案，
    // 残留本来就在屏上看不见。有牙的是 authError 这个模块级 ref 本身。两句都留着：
    // 前者钉"屏上不许出现那句旧文案"，后者钉"状态里不许留着它"。
    expect(authError.value).toBe('')
    expect(app.find('.picker-error').text()).not.toContain('上一次失败的文案')
  })

  it('运行中撞 401：整屏落回登录页，清理与点退出那条一字不差，且不发 logout', async () => {
    // advisory ② 的判据。注入方式只能改 ROUTES 元素再还原：那是模块级常量数组，
    // 换成 vi.stubGlobal 重写 fetch 就会绕过真实的 client.js——而 status 与 401 回调
    // 正是本 Task 的交付物，绕过它等于什么都没测。
    //
    // documents 与 history **两拍一起**翻 401（计划原文只翻了 documents，实测咬不住）：
    // 只翻一拍的话，handleSessionLost 之后 enterWorkspace 照样会继续跑到 restore(newSid)，
    // 而桩对 /api/history/ 仍回 200 两行 ⇒ msgs 断言永久红——那口红是注入方式造的，不是实现坏。
    // 真实场景里一枚过期票就是**每一枪都 401**，两拍同翻才是事实，顺带把重入也压给了被测代码。
    seedLoggedIn()
    const flips = ['/api/documents', '/api/history/'].map((prefix) => {
      const route = ROUTES.find((r) => r.prefix === prefix)
      const original = [route.status, route.body]
      route.status = 401
      route.body = { detail: '未登录或登录已过期' }
      return [route, original]
    })
    try {
      const app = await mountApp()
      await flushPromises()      // 落回登录页是 clearAuth() 触发的重渲染，多冲一拍不改变任何判据
      expect(app.find('.auth-screen').exists()).toBe(true)     // 整屏落回，不是"渲染但禁用"
      expect(app.find('.user-rail').exists()).toBe(false)
      // 三个键一起清（与上面点退出那条同一组判据）
      expect(localStorage.getItem('auth_token')).toBe(null)
      expect(localStorage.getItem('session_id')).toBe(null)
      expect(localStorage.getItem('selected_parent_ids')).toBe('[]')
      // vm 层：DOM 此时已整棵卸载，屏上没有残留可断——这条口径见上面 :183 那段注释
      expect({ docs: app.vm.documents.length, msgs: app.vm.messages.length })
        .toEqual({ docs: 0, msgs: 0 })
      // Task 9：settingsOpen 与 pickerOpen 同组清理。这一句单独**不是牙**——401 发生在
      // onMounted 的三拍里，弹窗在此之前没有开过的机会，照初值绿；有牙的是 Step 5
      // 第一条「开着弹窗登出」。留着的价值是：将来谁往 handleSessionLost 走一条不开弹窗的
      // 清理分支（比如拆掉 resetWorkspace 复用），这里与那条测一起红。
      expect(app.vm.settingsOpen).toBe(false)
      // 判据的另一半：自动登出**不许**补发 logout（那一枪必再 401，回调就成了环）
      expect(calls.filter((c) => c.url.startsWith('/api/auth/logout'))).toEqual([])
    } finally {
      for (const [route, [status, body]] of flips) {
        route.status = status
        route.body = body
      }
    }
  })

  it('⚙ 点得开、弹窗能关，且退出后不再留着上一个账号的表单', async () => {
    seedLoggedIn()
    const app = await mountApp()
    // 前置事实：⚙ 不再是 disabled（阶段一那条 disabled 是"点出空白弹窗更糟"的占位）
    const gear = app.find('.rail-settings')
    expect(gear.attributes('disabled')).toBeUndefined()
    expect(app.find('.settings-panel').exists()).toBe(false)

    await gear.trigger('click')
    expect(app.find('.settings-panel').exists()).toBe(true)
    // 弹窗里此刻是**这个人**的资料（回填来自模块级 user，不是空表单）
    expect(app.find('.settings-nickname-input').element.value).toBe('小明')

    // Task 9 的关键接线：开着弹窗登出，ref 必须跟着归位
    await app.find('.rail-signout').trigger('click')
    await flushPromises()
    expect(app.vm.settingsOpen).toBe(false)
    expect(app.find('.settings-panel').exists()).toBe(false)
  })

  it('头像列的三种值都渲染得出来：auto 取昵称首字母、预设表情是整枚、空昵称退回标识首字母', async () => {
    const { user } = useAuth()
    seedLoggedIn()
    const app = await mountApp()                        // me 回的是 ME.user（avatar: 'auto'）
    expect(app.find('.rail-avatar').text()).toBe('小')  // 昵称「小明」的首字母，中文不需要 toUpperCase
    // 每改一次都要 nextTick：computed 是同步的，但它只重算值，DOM 补丁排在渲染队列里，
    // 不冲这一拍读到的还是上一拍的渲染（计划 Step 5 的片段少了这两句，实测第一个红就是这么来的）。
    user.value = { ...user.value, avatar: '🤖' }
    await nextTick()
    expect(app.find('.rail-avatar').text()).toBe('🤖')   // 整枚，不是半个代理对
    user.value = { ...user.value, avatar: 'auto', nickname: '', identifier: 'z@b.com' }
    await nextTick()
    expect(app.find('.rail-avatar').text()).toBe('Z')
  })

  it('下拉换模型 → 发出去的载荷跟着换（App 到网络层是一条链，分段测各自看不见它）', async () => {
    seedLoggedIn()
    const app = await mountApp()
    // 前置事实：下拉的两项就是 ME.user.models 那两项，顺序照抄（currentModel 默认取 default_model）
    const select = app.find('.model-select')
    expect(select.findAll('option').map((o) => o.element.value)).toEqual(['qwen-max', 'qwen-turbo'])
    await select.setValue('qwen-turbo')
    await app.find('.chat-textarea').setValue('营收多少')
    await app.find('.chat-send').trigger('click')
    await flushPromises()
    // 桩只记 url/method/body，这里只需要 body：/api/chat/stream 回的是 application/json，
    // postStream 必然在 content-type 那一格抛"响应不是 SSE 事件流"——**这不影响判据**：
    // fetch 已经发生并记账，抛错发生在其后，useChat 的 catch 只会撤掉那两条气泡。
    // 测的是载荷，不是流。
    const chatCall = calls.find((c) => c.url === '/api/chat/stream')
    expect(JSON.parse(chatCall.body).model_name).toBe('qwen-turbo')
    // 顺带钉住另一个键：池子还是那个池子，模型名不该把 parent_ids 顶掉
    expect(JSON.parse(chatCall.body).parent_ids).toEqual(['手册.pdf_parent_0'])
  })

  it('选中的模型被从自己名单里删掉后，下拉回落到默认而不是抱着那个名字', async () => {
    // 这条是 currentModel 里 `opts.includes(modelOverride.value)` 那半门禁的**唯一牙**：
    // 上一条测选的 qwen-turbo 本来就在名单里，删掉门禁它也绿（计划 Step 7 的变异自证预期错了，
    // 实测删门禁后本文件 7 条全绿）。
    // 场景取 SettingsModal 的 applyModels：删模型只 patchMe 新的 models/default_model，
    // 它碰不到 App 层的 modelOverride——于是"屏上选着一个后端名单里已经没有的模型"必然发生，
    // 门禁在的就是这一格（换人那一格由 resetWorkspace 清 ref，另有判据）。
    const { user } = useAuth()
    seedLoggedIn()
    const app = await mountApp()
    await app.find('.model-select').setValue('qwen-turbo')
    // 前置事实：这一档真的被选中了（不是默认值恰好等于它）
    expect(app.find('.model-select').element.value).toBe('qwen-turbo')
    // 同一个账号，把 qwen-turbo 从名单里删掉，默认回到剩下的那项
    user.value = { ...ME.user, models: ['qwen-max'], default_model: 'qwen-max' }
    await nextTick()
    // 没有门禁时 currentModel 会抱着 'qwen-turbo' 不放：:value 指向一个不存在的 option，
    // jsdom 把 select.value 落成空串，这一句就红（红得具体，不是"字段不存在"那种脏红）。
    expect(app.find('.model-select').element.value).toBe('qwen-max')
  })

  it('没配 key：横幅在输入区上方、文案点名 api_key，且发送被禁用（输入框有字也一样禁）', async () => {
    seedLoggedIn()
    const route = ROUTES.find((r) => r.prefix === '/api/auth/me')
    const original = route.body
    route.body = { user: meUser({ llm_configured: false, api_key_masked: '', llm_base_url: '', models: [] }) }
    try {
      const app = await mountApp()
      expect(app.find('.setup-banner').exists()).toBe(true)
      expect(app.find('.setup-banner').text()).toContain('api_key')
      await app.find('.chat-textarea').setValue('你好')
      expect(app.find('.chat-send').attributes('disabled')).toBeDefined()
      // 判据的另一半：Enter 这条路也被同一条门挡住（禁用只挡住了按钮）
      await app.find('.chat-textarea').trigger('keydown', { key: 'Enter' })
      expect(calls.filter((c) => c.url === '/api/chat/stream')).toEqual([])
    } finally { route.body = original }
  })

  it('凭证齐了但名单为空：横幅换成"名单是空的"那句（两句不许合成一句）', async () => {
    seedLoggedIn()
    const route = ROUTES.find((r) => r.prefix === '/api/auth/me')
    const original = route.body
    route.body = { user: meUser({ models: [], default_model: null }) }
    try {
      const app = await mountApp()
      expect(app.find('.setup-banner').text()).toContain('名单是空的')
      expect(app.find('.setup-banner').text()).not.toContain('api_key')
    } finally { route.body = original }
  })

  it('点横幅上的「去设置」把弹窗打开；配齐之后横幅消失、发送恢复可点', async () => {
    seedLoggedIn()
    const route = ROUTES.find((r) => r.prefix === '/api/auth/me')
    const original = route.body
    route.body = { user: meUser({ llm_configured: false, models: [] }) }
    try {
      const app = await mountApp()
      await app.find('.setup-open').trigger('click')
      expect(app.find('.settings-panel').exists()).toBe(true)
      await app.find('.picker-close').trigger('click')      // 关掉弹窗，横幅还在（配置没变）
      expect(app.find('.setup-banner').exists()).toBe(true)

      // 同一次挂载里把 /me 换回"配齐"：模拟在设置里填完之后的 rehydrate
      route.body = { user: meUser() }
      await useAuth().bootstrap()
      await flushPromises()
      expect(app.find('.setup-banner').exists()).toBe(false)
      await app.find('.chat-textarea').setValue('你好')
      expect(app.find('.chat-send').attributes('disabled')).toBeUndefined()
    } finally { route.body = original }
  })
})
