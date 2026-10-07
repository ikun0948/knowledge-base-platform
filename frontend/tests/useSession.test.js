// useSession 的三条契约：出厂值是合法 uuid、外部塞进来的坏值进不了请求 URL、
// 以及"多处调用拿到的是同一个 ref"。第三条是 Task 7 新加的能力（登录要把后端铸造的
// 对话 id 换进界面），前两条是把原本只写在注释里的话钉住。
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useSession } from '../src/composables/useSession.js'

const KEY = 'session_id'
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const GOOD = '3f2b1c00-1111-2222-3333-444455556666'

// 构造那一下的行为只能重新 import 来测：sessionId 的初值在模块加载时读一次 localStorage，
// 静态 import 会把它冻在第一个测试的时钟上。
// 这里用 resetModules 不是逃避——Task 6 告诫过的那条是"三处读同一个对象"，
// 而那件事由下面第 5 条测专门证，两边不冲突。
async function freshUseSession(seed) {
  localStorage.removeItem(KEY)
  if (seed !== undefined) localStorage.setItem(KEY, seed)
  vi.resetModules()
  const mod = await import('../src/composables/useSession.js')
  return mod.useSession()
}

describe('useSession', () => {
  beforeEach(() => localStorage.removeItem(KEY))

  it('没存过就造一个 uuid 并立刻落盘', async () => {
    const { sessionId } = await freshUseSession()
    expect(sessionId.value).toMatch(UUID_RE)
    expect(localStorage.getItem(KEY)).toBe(sessionId.value)
  })

  it('DevTools 里塞进来的坏值（含 "/"）当场作废并换成新 uuid', async () => {
    // 这个键会拼进 GET /api/history/${sessionId}：带 "/" 的值能把请求路径劈开，
    // 所以"由构造不可达"这条要在这一层守（Task 2 ruling I-2 的前端半边）
    const { sessionId } = await freshUseSession('../../etc/passwd')
    expect(sessionId.value).toMatch(UUID_RE)
    expect(localStorage.getItem(KEY)).toBe(sessionId.value)
  })

  it('setSession 同时改 ref 与 localStorage；坏形状换成 uuid 而不是原样写入', async () => {
    const { sessionId, setSession } = await freshUseSession()
    expect(setSession(GOOD)).toBe(GOOD)
    expect(sessionId.value).toBe(GOOD)
    expect(localStorage.getItem(KEY)).toBe(GOOD)

    const after = setSession('not-a-uuid')
    expect(after).toMatch(UUID_RE)
    expect(localStorage.getItem(KEY)).toBe(after)
  })

  it('resetSession 换出来的 id 与清空前不同（需求 2「重新登录就是新对话」的存储层判据）', async () => {
    const { sessionId, setSession, resetSession } = await freshUseSession()
    setSession(GOOD)
    const next = resetSession()
    expect(next).not.toBe(GOOD)
    expect(next).toMatch(UUID_RE)
    expect(localStorage.getItem(KEY)).toBe(next)
  })

  it('两次 useSession() 返回同一个 ref：登录写入的 id 界面立刻看得见', () => {
    const a = useSession()
    const b = useSession()
    expect(a.sessionId).toBe(b.sessionId)
    a.setSession(GOOD)
    expect(b.sessionId.value).toBe(GOOD)
  })

  it('clearSession 把键删掉，但 ref 仍是一个合法 uuid（登出后界面不许出现空 id）', async () => {
    const { sessionId, clearSession } = await freshUseSession()
    clearSession()
    expect(localStorage.getItem(KEY)).toBe(null)
    expect(sessionId.value).toMatch(UUID_RE)
  })
})
