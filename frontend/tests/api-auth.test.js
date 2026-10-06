// api/auth.js 的薄封装只有两格承重：字段名在这层从 camelCase 翻成后端的 snake_case，
// 以及"昵称留空就连键都不发"——backend/schemas/auth.py:37 给 nickname 设了 min_length=1，
// 前端多发一个 '' 就是建号 422。useAuth.test.js 把整个 ../src/api/auth.js mock 掉了，
// 所以这两条直接钉它自己，别再绕回 composable。
//
// 桩的是 ../src/api/client.js 里的 request（形状抄 client.test.js 的 stubFetchWithCalls：
// 把实参收进数组再读），而不是 global.fetch。原因：request 交给 fetch 之前已经 JSON.stringify 过，
// 而 JSON.stringify 会**丢掉值为 undefined 的键**——真在 fetch 那一层断 'nickname' in JSON.parse(body)，
// 把 `if (nickname)` 改成无条件 `body.nickname = nickname` 照样绿。读 request 手上的 body 对象才咬得住
// "无条件多塞一个键"这件事（详见修正轮报告里 H5 那段"这条测能咬什么、咬不到什么"）。
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../src/api/client.js', () => ({ request: vi.fn() }))

import { register } from '../src/api/auth.js'
import { request } from '../src/api/client.js'

beforeEach(() => {
  vi.clearAllMocks()
})

describe('api/auth.js 的 register 请求体', () => {
  it('不填昵称时请求体里没有 nickname 键，字段名是后端的 snake_case', async () => {
    await register({ identifierType: 'email', identifier: 'a@b.com', password: 'hunter2-pass' })

    const [path, opts] = request.mock.calls[0]
    expect(path).toBe('/api/auth/register')
    expect(opts.method).toBe('POST')
    expect(opts.body.identifier_type).toBe('email')   // 契约真相是下划线，不是界面上的 identifierType
    expect(opts.body.identifier).toBe('a@b.com')
    // 断"键在不在"而不是断值：值 undefined 会被 JSON.stringify 抹掉，键存在才是"前端替后端决定了昵称"的证据。
    expect('nickname' in opts.body).toBe(false)
  })

  it('填了昵称就把原值送进请求体，不改写不兜底', async () => {
    await register({
      identifierType: 'email', identifier: 'a@b.com', password: 'hunter2-pass', nickname: '小明',
    })

    const body = request.mock.calls[0][1].body
    expect('nickname' in body).toBe(true)
    expect(body.nickname).toBe('小明')
  })
})
