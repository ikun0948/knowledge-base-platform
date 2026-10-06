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
    // 与 brief 的一行差异：这里改成断言"错误原样上抛"。signOut 内部是 try/finally 没有 catch
    // （与 signIn/signUp 同一口径：吞不吞错归调用方），所以裸 await 会让这条测红在抛出本身、
    // 而不是红在"本地没退干净"。真正要钉的两条判据在下面，且它们只在 finally 跑过时才成立。
    await expect(signOut()).rejects.toThrow('HTTP 502')
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
})
