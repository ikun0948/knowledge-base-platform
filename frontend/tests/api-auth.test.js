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

import {
  addModel, register, removeModel, setDefaultModel,
  updateLlmConfig, updatePassword, updateProfile,
} from '../src/api/auth.js'
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

// 阶段二 Task 8：六个设置端点的封装。这层仍然只承重两件事——字段名翻译与路径拼装，
// 所以判据读的是 request 手上的 body 对象（同上那段"JSON.stringify 会抹掉 undefined 键"的理由）。
describe('api/auth.js 的六个设置封装（Task 8）', () => {
  it('updateProfile 只发非空字段，且发的是后端的下划线端点与 PUT', async () => {
    await updateProfile({ nickname: '  小明  ', avatar: '' })
    const [path, opts] = request.mock.calls[0]
    expect([path, opts.method]).toEqual(['/api/auth/me', 'PUT'])
    // 不 trim：清洗是后端的事（api/auth.py 的 update_me 自己 strip 并拦空白）。
    // 前端先 trim 会让"我只改了空格"这条 422 判据在界面上消失。
    expect(opts.body).toEqual({ nickname: '  小明  ' })
  })

  it('updatePassword 的两个键名翻成下划线，204 不需要回执', async () => {
    await updatePassword({ oldPassword: 'old-pass', newPassword: 'new-pass' })
    const [path, opts] = request.mock.calls[0]
    expect([path, opts.method]).toEqual(['/api/auth/me/password', 'PUT'])
    expect(opts.body).toEqual({ old_password: 'old-pass', new_password: 'new-pass' })
  })

  it('updateLlmConfig 的键名是 api_key / base_url（这一处最容易被顺手写成 camelCase）', async () => {
    await updateLlmConfig({ apiKey: 'sk-abcdef1234567890', baseUrl: 'https://vLLM.internal/v1' })
    expect(request.mock.calls[0][1].body).toEqual({
      api_key: 'sk-abcdef1234567890', base_url: 'https://vLLM.internal/v1',
    })
  })

  it('三枚模型封装：删除编码路径段、设默认打 /default、添加只发 name', async () => {
    // 模型名是用户手打的（"qwen 2.5/coder" 这种带空格与斜杠的真存在）。不编码就会把一段路径
    // 劈成两段，坏法是 404「模型不在你的名单里」而不是 422——那句话这时候是假的。
    await removeModel('qwen 2.5/coder')
    const [removed] = request.mock.calls[0]
    expect(removed).not.toContain(' ')
    expect(removed.startsWith('/api/auth/me/models/qwen%202.5%2Fcoder')).toBe(true)

    await setDefaultModel('qwen-max')
    expect([request.mock.calls[1][0], request.mock.calls[1][1].body])
      .toEqual(['/api/auth/me/models/default', { name: 'qwen-max' }])

    await addModel('qwen-turbo')
    expect([request.mock.calls[2][0], request.mock.calls[2][1].method, request.mock.calls[2][1].body])
      .toEqual(['/api/auth/me/models', 'POST', { name: 'qwen-turbo' }])
  })
})
