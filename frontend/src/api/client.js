// 全项目唯一的网络出口：组件层永远看不到 fetch 与 Response（spec 六节"不加响应壳"）

// 令牌是全项目唯一的"我是谁"证据，而出口有三条（request / postStream / 上传的 XHR）。
// 做成模块级变量而不是让每个调用方自己传：传漏一次的表征是一整片 401，
// 而 401 在前端只有一句"未登录或登录已过期"，看的人只会去怀疑令牌过期了。
let authToken = ''

export function setAuthToken(token) {
  authToken = token || ''
}

export function authHeaders(extra = {}) {
  // 没令牌时一个键都不加：加了 `Authorization: Bearer ` 空值反而会让后端把坏格式判成缺凭证，
  // 两种成因共用一句文案是设计（spec 3.5），但请求本身没必要长得像攻击载荷。
  return authToken ? { Authorization: `Bearer ${authToken}`, ...extra } : { ...extra }
}

// 独立成纯函数是因为上传走 XHR（见 documents.js），它手上没有 Response 只有文本，
// 但错误规则必须和 fetch 那条完全一致，否则同一个 415 在两个入口显示两种文案。
export function detailFromText(text, status) {
  let body
  try {
    body = JSON.parse(text)
  } catch {
    // 代理层或静态服务器给的 HTML 错误页：别让 JSON.parse 抛出的怪话盖掉真实状态码
    return `HTTP ${status}`
  }
  const detail = body?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    // 数组 detail 来自参数校验（msg 是英文）：冠一句中文，原文照抄在后——翻译会漂、丢弃等于藏 bug（M-j）
    return `请求参数不合法：${detail.map((item) => item?.msg ?? JSON.stringify(item)).join('；')}`
  }
  return `HTTP ${status}`
}

// ApiError：前端唯一需要的"带状态码的错误"。三条 HTTP 出口（request / postStream / 上传的 XHR）
// 共用它，`status = 0` 表示"手上根本没有响应"——网络层失败、流读到一半断、帧解析失败。
// 必须 extends Error：既有 21 条 client.test.js 判据里有一串 rejects.toThrow(文案)，
// 它只读 message；换成普通对象会让那串全红，而红的理由是"测法"不是"行为"。
export class ApiError extends Error {
  constructor(message, status = 0) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

// advisory ②：运行中撞 401（票在会话中途过期）以前只弹一句横幅，界面还停在"已登录"，
// 用户对着一个必然再 401 的输入框反复点发送。这一格把"该登出"交给界面层决定——
// client.js 不认识 user、不认识 localStorage，它只负责"认出 401"和"喊一声"。
// 单槽不是列表：全项目只有 App.vue 一个订阅者，多个订阅者要先有真实需求。
let onUnauthorized = null

export function setUnauthorizedHandler(handler) {
  onUnauthorized = typeof handler === 'function' ? handler : null
}

function notifyUnauthorized(status) {
  if (status !== 401) return
  // 回调抛错不许盖掉原错误：横幅上该出现的是后端那句 detail，不是一句 TypeError
  try {
    onUnauthorized?.()
  } catch {
    /* 静默：这一格失败给不出可行动的中文，而 401 的文案已经在路上 */
  }
}

// HTTP 状态引起的错误只有一个构造点。三条出口各自 new 一遍的坏法是
// "同一个 401 在两个入口两种文案"——detailFromText 的注释早就为这件事写过一次。
export function httpError(text, status) {
  notifyUnauthorized(status)
  return new ApiError(detailFromText(text, status), status)
}

export async function request(path, { method = 'GET', body, headers = {}, signal } = {}) {
  const isJson = body !== undefined
  let res
  try {
    res = await fetch(path, {
      method,
      headers: authHeaders({
        Accept: 'application/json',
        ...(isJson ? { 'Content-Type': 'application/json' } : {}),
        ...headers,
      }),
      body: isJson ? JSON.stringify(body) : undefined,
      signal,
    })
  } catch {
    // fetch 只在网络层失败时 reject：此时没有 detail 可读，给一句能行动的中文
    throw new ApiError('无法连接后端，请确认 uvicorn 已在 :8000 运行')
  }
  if (!res.ok) throw httpError(await res.text(), res.status)
  // 204 No Content 没有响应体：res.json() 会在空文本上抛 SyntaxError，
  // 把"操作成功"变成一条报错。登出、后面的删档类端点都走这一格。
  if (res.status === 204) return null
  return res.json()
}

// 阶段二（spec 6.4）：SSE 读取。EventSource 不支持 POST body，只能用 fetch + ReadableStream。
// 中断约定（ledger 终审 G-2 收口）：调用方主动中断（AbortController 的 AbortError、
// AbortSignal.timeout 的 TimeoutError）在 fetch 与读取两个阶段都原样上抛，判据是 signal?.aborted
// 而不是 err.name —— 包成"无法连接后端"会让用户去查服务器，而真相是他自己取消的。
export async function postStream(path, payload, onEvent, { signal } = {}) {
  let res
  try {
    res = await fetch(path, {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json', Accept: 'text/event-stream' }),
      body: JSON.stringify(payload),
      signal,
    })
  } catch (err) {
    if (signal?.aborted) throw err  // 调用方主动中断（AbortError / TimeoutError）原样上抛
    throw new ApiError('无法连接后端，请确认 uvicorn 已在 :8000 运行')
  }
  if (!res.ok) {
    // 流开始前的失败（422/409/502/500）仍是普通 HTTP：状态码 + detail 照旧。
    // Task 11 的"没配模型"横幅认的是 status === 409，不是这句文案的子串。
    throw httpError(await res.text(), res.status)
  }
  // 反代把 SSE 缓冲成整包、或 200 落地一张 HTML 错误页时 res.ok 仍为真，读循环只会拿到零帧：
  // 先认内容类型，否则"根本没有流"会被当成"读完了一条空流"。
  if (!String(res.headers.get('content-type') ?? '').includes('text/event-stream')) {
    // status 照实填 res.status（这一格手上确实有一枚成功的响应）：填 0 会把它谎报成"连不上后端"。
    throw new ApiError('响应不是 SSE 事件流，请检查代理配置', res.status)
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      // 只有 read() 属于"网络断裂"域：dispatch/onEvent 的异常一律原样上抛，
      // 把回调 bug 翻译成"流式响应中断"会把下一个调试会话骗去查服务器
      let chunk
      try {
        chunk = await reader.read()
      } catch (err) {
        if (signal?.aborted) throw err  // 调用方主动（cancel 或 AbortSignal.timeout 的 TimeoutError）都原样传播
        throw new ApiError('流式响应中断，请重试')
      }
      if (chunk.done) break
      buffer += decoder.decode(chunk.value, { stream: true })
      let cut = buffer.indexOf('\n\n')
      while (cut >= 0) {
        dispatch(buffer.slice(0, cut), onEvent)
        buffer = buffer.slice(cut + 2)
        cut = buffer.indexOf('\n\n')
      }
    }
  } finally {
    // 任何出口（EOF/abort/回调异常）都把流归还：EOF 后 cancel 是无害 no-op，
    // 异常出口则让后端生成器随断连停下，而不是对着没人读的 socket 续产
    reader.cancel().catch(() => {})
  }
}

// 一条帧 = "event: 名" 行 + "data: 单行JSON" 行；无 event 行按 SSE 默认名 message 派发，
// 后端不会发这种帧，但默认值让 onEvent 的 switch 分支不用处理 undefined。
function dispatch(frame, onEvent) {
  let event = 'message'
  const dataLines = []
  for (const line of frame.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
  }
  if (!dataLines.length) return
  let data
  try {
    data = JSON.parse(dataLines.join('\n'))
  } catch {
    // 这一格在 dispatch() 里：手上只有帧文本、没有 response，只能 0
    throw new ApiError('流式帧解析失败，请重试')
  }
  onEvent(event, data)
}
