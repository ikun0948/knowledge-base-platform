// 全项目唯一的网络出口：组件层永远看不到 fetch 与 Response（spec 六节"不加响应壳"）

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
    // FastAPI 的参数校验把 detail 组成数组（422），领域异常 handler 给的是字符串
    return detail.map((item) => item?.msg ?? JSON.stringify(item)).join('；')
  }
  return `HTTP ${status}`
}

export async function request(path, { method = 'GET', body, headers = {}, signal } = {}) {
  const isJson = body !== undefined
  let res
  try {
    res = await fetch(path, {
      method,
      headers: {
        Accept: 'application/json',
        ...(isJson ? { 'Content-Type': 'application/json' } : {}),
        ...headers,
      },
      body: isJson ? JSON.stringify(body) : undefined,
      signal,
    })
  } catch {
    // fetch 只在网络层失败时 reject：此时没有 detail 可读，给一句能行动的中文
    throw new Error('无法连接后端，请确认 uvicorn 已在 :8000 运行')
  }
  if (!res.ok) throw new Error(detailFromText(await res.text(), res.status))
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
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify(payload),
      signal,
    })
  } catch (err) {
    if (signal?.aborted) throw err  // 调用方主动中断（AbortError / TimeoutError）原样上抛
    throw new Error('无法连接后端，请确认 uvicorn 已在 :8000 运行')
  }
  if (!res.ok) {
    // 流开始前的失败（422/502/500）仍是普通 HTTP：状态码 + detail 照旧
    throw new Error(detailFromText(await res.text(), res.status))
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
        throw new Error('流式响应中断，请重试')
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
    throw new Error('流式帧解析失败，请重试')
  }
  onEvent(event, data)
}
