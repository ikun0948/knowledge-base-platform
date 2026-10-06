// client.js 的 SSE 契约回归：终审指出这块行为只靠浏览器手测背书，CI 完全接不住。
// 这里把 postStream 的每条出口（正常收流 / 非流响应 / HTTP 失败 / 读中断 / 主动取消 / 坏帧）
// 都钉成断言——桩掉 fetch，不需要真服务。
import { afterEach, describe, expect, it, vi } from 'vitest'

import { detailFromText, postStream, request, setAuthToken } from '../src/api/client.js'

function fakeReader(chunks, { failAt = -1, err } = {}) {
  let i = 0
  const state = { cancelled: false }
  return {
    state,
    reader: {
      async read() {
        if (failAt >= 0 && i === failAt) throw err ?? new Error('network down')
        if (i >= chunks.length) return { done: true, value: undefined }
        return { done: false, value: new TextEncoder().encode(chunks[i++]) }
      },
      async cancel() {
        state.cancelled = true
      },
    },
  }
}

function streamResponse(chunks, { contentType = 'text/event-stream', ...readerOpts } = {}) {
  const { reader, state } = fakeReader(chunks, readerOpts)
  const res = {
    ok: true,
    status: 200,
    headers: { get: (k) => (k.toLowerCase() === 'content-type' ? contentType : null) },
    body: { getReader: () => reader },
  }
  return { res, state }
}

function jsonResponse(body, status = 200, contentType = 'application/json') {
  const text = typeof body === 'string' ? body : JSON.stringify(body)
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => contentType },
    text: async () => text,
    // 补 json()：既有测只走 request 的非 2xx 出口（读 text），成功出口读不到这里。
    json: async () => JSON.parse(text),
    body: null,
  }
}

function stubFetch(r) {
  // streamResponse 返回 {res, state}，jsonResponse 直接是 res——两种形状都收
  const res = r && r.res !== undefined ? r.res : r
  global.fetch = vi.fn(async () => res)
}

function stubFetchWithCalls(r) {
  // stubFetch 只换实现、不留参数，而"三条出口有没有带上 Bearer 头"必须看到实发的 headers
  const res = r && r.res !== undefined ? r.res : r
  const calls = []
  global.fetch = vi.fn(async (path, opts) => { calls.push([path, opts]); return res })
  return calls
}

function frame(event, data) {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`
}

describe('detailFromText', () => {
  it('字符串 detail 原样、422 数组 detail 冠中文引导句并保留原文', () => {
    expect(detailFromText(JSON.stringify({ detail: '文件类型不支持' }), 415)).toBe('文件类型不支持')
    // M-j：pydantic 的 msg 是英文，界面不能整句外语；但原文是唯一的排错线索，翻译/丢弃都不干
    expect(detailFromText(JSON.stringify({ detail: [{ msg: 'a' }, { msg: 'b' }] }), 422))
      .toBe('请求参数不合法：a；b')
  })

  it('422 数组里缺 msg 的项降级为 JSON 文本，不让 undefined 混进中文句', () => {
    expect(detailFromText(JSON.stringify({ detail: [{ type: 'too_short', loc: ['body', 'x'] }] }), 422))
      .toBe('请求参数不合法：{"type":"too_short","loc":["body","x"]}')
  })

  it('非 JSON 响应体（反代 HTML 错误页）回退到 HTTP 状态码', () => {
    expect(detailFromText('<html>502 Bad Gateway</html>', 502)).toBe('HTTP 502')
  })
})

describe('request', () => {
  it('网络层 reject 时给可行动的中文而不是英文堆栈', async () => {
    global.fetch = vi.fn(async () => {
      throw new TypeError('Failed to fetch')
    })
    await expect(request('/api/anything')).rejects.toThrow('无法连接后端')
  })

  it('非 2xx 走 detailFromText', async () => {
    stubFetch(jsonResponse({ detail: '会话不存在' }, 404))
    await expect(request('/api/history/x')).rejects.toThrow('会话不存在')
  })
})

describe('postStream：正常收流', () => {
  it('五类帧按行序派发，event 名与 data 对象逐帧一致', async () => {
    const ref = { document_id: 1, filename: '甲.txt', snippet: '片段' }
    stubFetch(streamResponse([
      frame('meta', { mode: 'rag', session_id: 's1' }),
      frame('references', [ref]),
      frame('token', { text: '第一段' }),
      frame('token', { text: '第二段' }),
      frame('done', {}),
    ]))
    const seen = []
    await expect(postStream('/api/chat/stream', {}, (e, d) => seen.push([e, d]))).resolves.toBeUndefined()
    expect(seen.map(([e]) => e)).toEqual(['meta', 'references', 'token', 'token', 'done'])
    expect(seen[0][1]).toEqual({ mode: 'rag', session_id: 's1' })
    expect(seen[2][1].text).toBe('第一段')
  })

  it('帧跨 chunk 劈开也能重组（buffer  leftover 语义）', async () => {
    const full = frame('token', { text: '中文\n换行' }) + frame('done', {})
    stubFetch(streamResponse([full.slice(0, 9), full.slice(9)]))
    const seen = []
    await postStream('/api/chat/stream', {}, (e, d) => seen.push([e, d]))
    expect(seen).toEqual([['token', { text: '中文\n换行' }], ['done', {}]])
  })

  it('无 event 行的帧按 SSE 默认名 message 派发', async () => {
    stubFetch(streamResponse(['data: {"a":1}\n\n']))
    const seen = []
    await postStream('/api/chat/stream', {}, (e, d) => seen.push([e, d]))
    expect(seen).toEqual([['message', { a: 1 }]])
  })

  it('EOF 正常退出后 reader 被归还（cancel 无副作用也要执行）', async () => {
    const { res, state } = streamResponse([frame('done', {})])
    stubFetch(res)
    await postStream('/api/chat/stream', {}, () => {})
    expect(state.cancelled).toBe(true)
  })
})

describe('postStream：失败出口', () => {
  it('流开始前的 422 仍是普通 HTTP：状态码 + detail', async () => {
    stubFetch(jsonResponse({ detail: [{ msg: 'too long' }] }, 422))
    await expect(postStream('/api/chat/stream', {}, () => {})).rejects.toThrow('too long')
  })

  it('200 但 content-type 不是 event-stream → 判“不是流”，且从不取 reader', async () => {
    // 反代把 SSE 缓冲成整包或 200 落地 HTML 错误页时 res.ok 仍为真；
    // 不拦就会把"根本没有流"读成"一条空流"。
    const { res, state } = streamResponse([], { contentType: 'text/html' })
    let gotReader = false
    res.body = { getReader: () => { gotReader = true; return state.reader } }
    stubFetch(res)
    await expect(postStream('/api/chat/stream', {}, () => {})).rejects.toThrow('响应不是 SSE 事件流')
    expect(gotReader).toBe(false)
  })

  it('读途中网络断（未取消）→ 收成中文“流式响应中断”', async () => {
    stubFetch(streamResponse([frame('meta', { mode: 'normal', session_id: 's1' })],
      { failAt: 1 }))
    await expect(postStream('/api/chat/stream', {}, () => {})).rejects.toThrow('流式响应中断，请重试')
  })

  it('G-2 约定：signal 已 abort 时读错误原样上抛，不包成中断文案', async () => {
    const controller = new AbortController()
    const abortErr = new Error('aborted by user')
    controller.abort()
    stubFetch(streamResponse([], { failAt: 0, err: abortErr }))
    await expect(
      postStream('/api/chat/stream', {}, () => {}, { signal: controller.signal }),
    ).rejects.toBe(abortErr)
  })

  it('G-2 约定：fetch 阶段 abort 同样原样上抛', async () => {
    const controller = new AbortController()
    const abortErr = new Error('timeout like AbortSignal.timeout')
    controller.abort()
    global.fetch = vi.fn(async () => { throw abortErr })
    await expect(
      postStream('/api/chat/stream', {}, () => {}, { signal: controller.signal }),
    ).rejects.toBe(abortErr)
  })

  it('fetch reject 且未取消 → “无法连接后端”', async () => {
    global.fetch = vi.fn(async () => { throw new TypeError('net fail') })
    await expect(postStream('/api/chat/stream', {}, () => {})).rejects.toThrow('无法连接后端')
  })

  it('坏帧（data 不是 JSON）→ 明确判“流式帧解析失败”', async () => {
    stubFetch(streamResponse(['event: token\ndata: {not json}\n\n']))
    await expect(postStream('/api/chat/stream', {}, () => {})).rejects.toThrow('流式帧解析失败')
  })

  it('onEvent 回调抛错原样上抛，不被翻译成“流式响应中断”', async () => {
    // read() 才是网络域；把回调 bug 包成网络错误会把下个调试会话骗去查服务器
    stubFetch(streamResponse([frame('token', { text: 'x' })]))
    const bug = new Error('my callback bug')
    await expect(
      postStream('/api/chat/stream', {}, () => { throw bug }),
    ).rejects.toBe(bug)
  })
})

describe('Authorization 注入：三条出口一条都不能漏', () => {
  // 漏一条的表征是"登录了但那个功能 401"，而 401 在前端只回一句"未登录或登录已过期"，
  // 看的人第一反应是令牌过期了——真正的原因却是某个出口忘了带头。
  afterEach(() => setAuthToken(''))

  it('request 带上 Bearer 头', async () => {
    const calls = stubFetchWithCalls(jsonResponse({ ok: true }))
    setAuthToken('tok-abc')
    await request('/api/documents')
    expect(calls[0][1].headers.Authorization).toBe('Bearer tok-abc')
    // 这一组的既有判据只读 Authorization，而本 Task 重写的是整行 headers：
    // 丢 Content-Type 的表征是 POST /api/auth/login 撞 422，正是"登录了但登录用不了"。
    await request('/api/auth/login', { method: 'POST', body: { identifier: 'a@b.com', password: 'hunter2-pass' } })
    expect(calls[1][1].headers['Content-Type']).toBe('application/json')
  })

  it('postStream 带上 Bearer 头（这里的 headers 原先是硬编码的）', async () => {
    const calls = []
    const { res } = streamResponse([frame('done', {})])
    global.fetch = vi.fn(async (path, opts) => { calls.push([path, opts]); return res })
    setAuthToken('tok-stream')
    await postStream('/api/chat/stream', {}, () => {})
    expect(calls[0][1].headers.Authorization).toBe('Bearer tok-stream')
    // 这行的 headers 原先是硬编码字面量，重写时除了令牌还有 Accept：
    // 丢了它后端仍回 SSE，但 client.js 的内容类型闸门会判"响应不是 SSE 事件流"。
    expect(calls[0][1].headers['Accept']).toBe('text/event-stream')
  })

  it('没有令牌时一个 Authorization 头都不发', async () => {
    const calls = stubFetchWithCalls(jsonResponse({ ok: true }))
    setAuthToken('')
    await request('/api/documents')
    expect('Authorization' in calls[0][1].headers).toBe(false)
  })

  it('204 无响应体不走进 res.json()', async () => {
    // 登出端点回 204：空文本过 JSON.parse 会抛 SyntaxError，
    // 于是"登出成功"在界面上变成一条红色报错——这是这条判据唯一要防的事。
    global.fetch = vi.fn(async () => ({
      ok: true, status: 204, headers: { get: () => null },
      text: async () => '', json: async () => { throw new SyntaxError('Unexpected end of input') },
    }))
    await expect(request('/api/auth/logout', { method: 'POST' })).resolves.toBeNull()
  })
})
