// useAuth 的四条纪律：坏令牌构造不可达、bootstrap 只在真登录时放行、
// 退出无论后端回什么都算本地退出、拿到新会话就把令牌同时写进 localStorage 与网络层。
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../src/api/auth.js', () => ({
  register: vi.fn(), login: vi.fn(), logout: vi.fn(), getMe: vi.fn(),
}))

import { getMe, login, logout, register } from '../src/api/auth.js'
import { useAuth } from '../src/composables/useAuth.js'

const USER = { id: 3, identifier: 'a@b.com', identifier_type: 'email', nickname: '小明', avatar: 'auto' }

beforeEach(() => {
  localStorage.clear()
  vi.clearAllMocks()
})

describe('useAuth', () => {
  it('没有令牌时 bootstrap 不发任何请求，也就不会打出一串 401 横幅', async () => {
    const { bootstrap } = useAuth()
    await expect(bootstrap()).resolves.toBe(false)
    expect(getMe).not.toHaveBeenCalled()
  })

  it('坏形状的本地令牌按没有处理（DevTools 里手敲的值不可达）', async () => {
    localStorage.setItem('auth_token', 'not-a-token')
    const { bootstrap } = useAuth()
    await expect(bootstrap()).resolves.toBe(false)
    expect(getMe).not.toHaveBeenCalled()
    // 不只是"当没有"，还要把这枚不合格的值删掉：只 setAuthToken('') 的话它永远留在机器上。
    expect(localStorage.getItem('auth_token')).toBe(null)
  })

  it('登录写入令牌、置好用户，并把后端铸造的 session_id 交回调用方', async () => {
    login.mockResolvedValue({ token: 'x'.repeat(43), user: USER, session_id: 'sid-from-server' })
    const { signIn, user, isLoggedIn } = useAuth()
    await expect(signIn({ identifier: 'a@b.com', password: 'hunter2-pass' }))
      .resolves.toBe('sid-from-server')
    expect(user.value).toEqual(USER)
    expect(isLoggedIn.value).toBe(true)
    expect(localStorage.getItem('auth_token')).toBe('x'.repeat(43))
  })

  it('bootstrap 拿到 200 才算登录成功', async () => {
    localStorage.setItem('auth_token', 'y'.repeat(43))
    getMe.mockResolvedValue({ user: USER })
    const { bootstrap, isLoggedIn } = useAuth()
    await expect(bootstrap()).resolves.toBe(true)
    expect(isLoggedIn.value).toBe(true)
  })

  it('bootstrap 失败静默清凭证：令牌过期不该变成界面上的一句红字', async () => {
    localStorage.setItem('auth_token', 'z'.repeat(43))
    getMe.mockRejectedValue(new Error('未登录或登录已过期'))
    const { bootstrap, isLoggedIn } = useAuth()
    await expect(bootstrap()).resolves.toBe(false)
    expect(isLoggedIn.value).toBe(false)
    expect(localStorage.getItem('auth_token')).toBe(null)
  })

  it('后端登出失败也完成本地退出（登出不是为了"服务端删了行"，是为了这台机器不再是你）', async () => {
    localStorage.setItem('auth_token', 'w'.repeat(43))
    getMe.mockResolvedValue({ user: USER })
    logout.mockRejectedValue(new Error('HTTP 502'))
    const { bootstrap, signOut, isLoggedIn } = useAuth()
    await bootstrap()
    await signOut()
    expect(isLoggedIn.value).toBe(false)
    expect(localStorage.getItem('auth_token')).toBe(null)
  })

  it('注册与登录都覆盖 localStorage 的令牌，不追加、不合并', async () => {
    register.mockResolvedValue({ token: 'r'.repeat(43), user: USER, session_id: 's1' })
    login.mockResolvedValue({ token: 'l'.repeat(43), user: USER, session_id: 's2' })
    const { signUp, signIn } = useAuth()
    await signUp({ identifierType: 'email', identifier: 'a@b.com', password: 'hunter2-pass' })
    expect(localStorage.getItem('auth_token')).toBe('r'.repeat(43))
    await signIn({ identifier: 'a@b.com', password: 'hunter2-pass' })
    expect(localStorage.getItem('auth_token')).toBe('l'.repeat(43))
  })

  it('patchMe 用后端回的整行覆盖 user，传空值时一个字段都不动', () => {
    getMe.mockResolvedValue({ user: USER })
    localStorage.setItem('auth_token', 'p'.repeat(43))
    const { bootstrap, patchMe, user } = useAuth()
    return bootstrap().then(() => {
      patchMe({ ...USER, nickname: '改名了', models: ['qwen-max'] })
      expect(user.value.nickname).toBe('改名了')
      expect(user.value.models).toEqual(['qwen-max'])
      patchMe(null)          // 204 那类端点回 null：不许把 user 抹成 null
      expect(user.value.nickname).toBe('改名了')
    })
  })

  it('clearAuth 是模块级的同一份：两次 useAuth() 调用共享它（401 回调要的就是这件事）', () => {
    getMe.mockResolvedValue({ user: USER })
    localStorage.setItem('auth_token', 'q'.repeat(43))
    return useAuth().bootstrap().then(() => {
      localStorage.setItem('auth_token', 'r'.repeat(43))
      useAuth().clearAuth()   // 换一个调用方
      expect(useAuth().isLoggedIn.value).toBe(false)
      expect(localStorage.getItem('auth_token')).toBe(null)
    })
  })
})
