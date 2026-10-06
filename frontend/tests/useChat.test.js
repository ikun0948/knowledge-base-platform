// useChat 的状态机回归：done 哨兵、error 记账、abort 静默撤泡这三条分支
// 是阶段二终审的修复波成果，之前只有浏览器手测背书——这里钉死，防止未来改动悄悄退回"半截答案留在界面"。
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../src/api/chat.js', () => ({ sendChatStream: vi.fn() }))
vi.mock('../src/api/history.js', () => ({ getHistory: vi.fn(), clearHistory: vi.fn() }))

import { sendChatStream } from '../src/api/chat.js'
import { clearHistory, getHistory } from '../src/api/history.js'
import { useChat } from '../src/composables/useChat.js'

// 把 mock 的 sendChatStream 设成"按序派发事件后正常返回"
function scriptEvents(events) {
  sendChatStream.mockImplementation(async (payload, onEvent) => {
    for (const [event, data] of events) onEvent(event, data)
  })
}

const flush = () => new Promise((r) => setTimeout(r, 0))

const DONE = ['done', {}]

describe('useChat.send：收流结局', () => {
  beforeEach(() => vi.clearAllMocks())

  it('完整流（meta→references→token×2→done）：true，气泡内容/模式/引用逐一对上', async () => {
    const ref = { document_id: 1, filename: '甲.txt', snippet: '片段' }
    scriptEvents([
      ['meta', { mode: 'rag', session_id: 's1' }],
      ['references', [ref]],
      ['token', { text: '你好' }],
      ['token', { text: '世界' }],
      DONE,
    ])
    const chat = useChat()
    await expect(chat.send({ session_id: 's1', question: 'q', parent_ids: ['甲.txt_parent_0'] })).resolves.toBe(true)
    expect(chat.messages.value).toHaveLength(2)
    const [user, assistant] = chat.messages.value
    expect([user.role, user.content, user.streaming]).toEqual(['user', 'q', false])
    expect(assistant.content).toBe('你好世界')
    expect(assistant.mode).toBe('rag') // meta 帧先于 token 落上
    expect(assistant.references).toEqual([ref])
    expect(assistant.streaming).toBe(false)
    expect(chat.pending.value).toBe(false)
    expect(chat.error.value).toBe('')
  })

  // 后端那份 ChatRequest 只认 parent_ids；多余字段被 Pydantic 静默丢掉，
  // 坏法是"每次对话都走普通链、引用条永远空"，不是 422 也不是报错。
  it('载荷里的池子字段叫 parent_ids', async () => {
    scriptEvents([['token', { text: 'x' }], DONE])
    const chat = useChat()
    await chat.send({ session_id: 's1', question: 'q', parent_ids: ['甲.txt_parent_0'] })
    expect(sendChatStream.mock.calls[0][0]).toEqual({
      session_id: 's1', question: 'q', parent_ids: ['甲.txt_parent_0'],
    })
  })

  it('done 前干净 EOF：撤两条 + “意外中断”，这一轮后端没落库就不能留在界面', async () => {
    scriptEvents([['meta', { mode: 'normal', session_id: 's1' }], ['token', { text: '半截' }]])
    const chat = useChat()
    await expect(chat.send({ session_id: 's1', question: 'q', parent_ids: [] })).resolves.toBe(false)
    expect(chat.messages.value).toEqual([])
    expect(chat.error.value).toBe('流式响应意外中断，请重试')
  })

  it('error 帧带 detail：撤两条 + 原样横幅（此时流是正常关闭的，不走 catch）', async () => {
    scriptEvents([['meta', { mode: 'rag', session_id: 's1' }], ['error', { detail: '大模型不可用' }], DONE])
    const chat = useChat()
    await expect(chat.send({ session_id: 's1', question: 'q', parent_ids: ['甲.txt_parent_0'] })).resolves.toBe(false)
    expect(chat.messages.value).toEqual([])
    expect(chat.error.value).toBe('大模型不可用')
  })

  it('error 帧 detail 为空串：真值判断会把它当成功，兜底文案必须顶上', async () => {
    scriptEvents([['error', { detail: '' }]])
    const chat = useChat()
    await chat.send({ session_id: 's1', question: 'q', parent_ids: [] })
    expect(chat.error.value).toBe('流式响应出错，请重试')
  })

  it('非取消的 throw：撤两条 + 原错误文案', async () => {
    sendChatStream.mockImplementation(async () => {
      throw new Error('流式响应中断，请重试')
    })
    const chat = useChat()
    await expect(chat.send({ session_id: 's1', question: 'q', parent_ids: [] })).resolves.toBe(false)
    expect(chat.messages.value).toEqual([])
    expect(chat.error.value).toBe('流式响应中断，请重试')
  })
})

describe('useChat：取消与门禁', () => {
  beforeEach(() => vi.clearAllMocks())

  it('abortStream 中途取消：静默撤泡，不弹横幅（真相是用户自己停的）', async () => {
    sendChatStream.mockImplementation((payload, onEvent, { signal }) => new Promise((_, reject) => {
      signal.addEventListener('abort', () => {
        const err = new Error('AbortError')
        err.name = 'AbortError'
        reject(err)
      })
    }))
    const chat = useChat()
    const sending = chat.send({ session_id: 's1', question: 'q', parent_ids: [] })
    await flush()
    expect(chat.pending.value).toBe(true)
    chat.abortStream()
    await expect(sending).resolves.toBe(false)
    expect(chat.messages.value).toEqual([])
    expect(chat.error.value).toBe('') // 不弹横幅
    expect(chat.pending.value).toBe(false)
  })

  it('pending 期间二次 send 直接 false，不发第二条流', async () => {
    // 流必须真的悬着：若 mock 同步跑完，pending 在 flush 时就已落回，门禁无从验起
    let release
    sendChatStream.mockImplementation(async (payload, onEvent) => {
      onEvent('token', { text: 'x' })
      await new Promise((r) => { release = r })
    })
    const chat = useChat()
    const sending = chat.send({ session_id: 's1', question: 'q1', parent_ids: [] })
    await flush()
    expect(chat.pending.value).toBe(true)
    await expect(chat.send({ session_id: 's1', question: 'q2', parent_ids: [] })).resolves.toBe(false)
    release()
    await sending
    expect(sendChatStream).toHaveBeenCalledTimes(1)
  })

  it('空白问题不发流', async () => {
    const chat = useChat()
    await expect(chat.send({ session_id: 's1', question: '   ', parent_ids: [] })).resolves.toBe(false)
    expect(sendChatStream).not.toHaveBeenCalled()
  })
})

describe('useChat.restore / clear', () => {
  beforeEach(() => vi.clearAllMocks())

  it('restore 把后端行映射成气泡：user 的 null references 归一成 []，mode 保留', async () => {
    getHistory.mockResolvedValue([
      { role: 'user', content: '你好', references: null, mode: null },
      { role: 'assistant', content: '答', references: [{ document_id: 1, filename: 'a.txt', snippet: 's' }], mode: 'rag' },
    ])
    const chat = useChat()
    await expect(chat.restore('s1')).resolves.toBe(true)
    const [user, assistant] = chat.messages.value
    expect(user.references).toEqual([])
    expect(user.mode).toBe(null)
    expect(assistant.mode).toBe('rag')
    expect(assistant.references).toHaveLength(1)
  })

  it('restore 失败：横幅 = 错误文案，返回 false', async () => {
    getHistory.mockRejectedValue(new Error('无法连接后端，请确认 uvicorn 已在 :8000 运行'))
    const chat = useChat()
    await expect(chat.restore('s1')).resolves.toBe(false)
    expect(chat.error.value).toBe('无法连接后端，请确认 uvicorn 已在 :8000 运行')
  })

  it('clear 先删后端再清本地', async () => {
    clearHistory.mockResolvedValue({ deleted: 2 })
    const chat = useChat()
    scriptEvents([['token', { text: 'x' }], DONE])
    await chat.send({ session_id: 's1', question: 'q', parent_ids: [] })
    await expect(chat.clear('s1')).resolves.toBe(true)
    expect(chat.messages.value).toEqual([])
  })

  it('clear 后端失败：本地一条不减（否则刷新历史原样冲回来）', async () => {
    clearHistory.mockRejectedValue(new Error('HTTP 500'))
    const chat = useChat()
    scriptEvents([['token', { text: 'x' }], DONE])
    await chat.send({ session_id: 's1', question: 'q', parent_ids: [] })
    await expect(chat.clear('s1')).resolves.toBe(false)
    expect(chat.messages.value).toHaveLength(2)
    expect(chat.error.value).toBe('HTTP 500')
  })
})

describe('useChat.markChunkDeleted', () => {
  // 删的是后端那块内容，界面上只是把"这一轮用过它"的事实标灰：条目必须留着。
  function seed() {
    const chat = useChat()
    chat.messages.value = [
      { key: 'a', role: 'assistant', content: '', references: [
        { document_id: 3, parent_id: 'p0', filename: '甲.txt' },
        { document_id: 3, parent_id: 'p1', filename: '甲.txt' },
      ] },
      { key: 'b', role: 'assistant', content: '', references: [
        { document_id: 3, parent_id: 'p0', filename: '甲.txt' },
        { document_id: 7, parent_id: 'p0', filename: '乙.pdf' },
      ] },
    ]
    return chat
  }

  it('跨轮引用同一块时一起标灰', () => {
    const chat = seed()
    chat.markChunkDeleted(3, 'p0')
    expect(chat.messages.value[0].references.map((r) => r.deleted)).toEqual([true, undefined])
    expect(chat.messages.value[1].references.map((r) => r.deleted)).toEqual([true, undefined])
  })

  it('parent_id 相同但文档不同：不能顺着 parent_id 误标别人的块', () => {
    const chat = seed()
    chat.markChunkDeleted(3, 'p0')
    expect(chat.messages.value[1].references[1].deleted).toBeUndefined()
  })

  it('界面上没有这个块：一条都不改（历史恢复后引用形状不同也只能是空操作）', () => {
    const chat = seed()
    chat.markChunkDeleted(9, 'p9')
    const flags = chat.messages.value.flatMap((m) => m.references.map((r) => r.deleted))
    expect(flags).toEqual([undefined, undefined, undefined, undefined])
  })
})
