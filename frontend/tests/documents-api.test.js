// api/documents.js 的两个块级出口：删除块与候选池查询。这里唯一会咬人的是 parent_id：
// 它是 f"{文件名}_parent_{i}"，中文和空格都来自文件名本身、没被 _safe_filename 洗掉，
// 只能靠编码送进路径段。写错的坏法不是报错而是 404——"块不存在"，比崩还难查。
import { afterEach, describe, expect, it, vi } from 'vitest'

import { deleteChunk, listChunks, uploadDocument } from '../src/api/documents.js'
import { ApiError, setAuthToken, setUnauthorizedHandler } from '../src/api/client.js'

function stubFetch() {
  const calls = []
  global.fetch = vi.fn(async (path, opts) => {
    calls.push([path, opts])
    return {
      ok: true,
      status: 200,
      json: async () => ({ id: 42, filename: '手册 上.pdf', chunk_count: 1, created_at: '2026-09-30T12:00:00' }),
      text: async () => '',
    }
  })
  return calls
}

afterEach(() => {
  delete global.fetch
})

describe('deleteChunk', () => {
  const PREFIX = '/api/documents/42/chunks/'

  it('用 DELETE 方法打后端那条路径，parent_id 原值编码在路径段里', async () => {
    const calls = stubFetch()
    const parentId = '手册 上.pdf_parent_0'

    await deleteChunk(42, parentId)

    const [path, opts] = calls[0]
    expect(opts.method).toBe('DELETE')
    // 裸空格与裸中文都不许出现在请求行里
    expect(path).not.toContain(' ')
    expect(path).not.toContain('手')
    expect(decodeURIComponent(path.slice(PREFIX.length))).toBe(parentId)
  })

  it('返回后端回读的文档行（chunk_count 已是删完后的实数）', async () => {
    stubFetch()
    await expect(deleteChunk(42, 'a.txt_parent_0')).resolves.toEqual({
      id: 42, filename: '手册 上.pdf', chunk_count: 1, created_at: '2026-09-30T12:00:00',
    })
  })
})

describe('listChunks（Task 1 契约的前端出口）', () => {
  it('空入参打裸路径，不拼一串无意义的问号', async () => {
    const calls = stubFetch()
    await listChunks()
    expect(calls[0][0]).toBe('/api/documents/chunks')
  })

  it('中文关键词与后缀都进 query', async () => {
    const calls = stubFetch()
    await listChunks({ query: '手册 上', suffix: 'pdf' })
    const params = new URLSearchParams(calls[0][0].split('?')[1])
    // 比解析后的原文，不比编码串：URLSearchParams 把空格编成 +，
    // 拿 decodeURIComponent 反解会得到"手册 +上"，那是判据写错不是实现错
    expect(params.get('query')).toBe('手册 上')
    expect(params.get('suffix')).toBe('pdf')
  })

  // 这一条是"选中项刷新后蒸发"的唯一防线：parent_id 由清洗后的文件名拼出，
  // 逗号是合法字符。逗号拼接会把一个真 id 拆成两个假 id，后端只会静默少返回。
  it('parent_ids 用重复键而不是逗号拼接，含逗号的 id 原样往返', async () => {
    const calls = stubFetch()
    const ids = ['手册,第一版.txt_parent_0', 'b.txt_parent_1']
    await listChunks({ parentIds: ids })
    const params = new URLSearchParams(calls[0][0].split('?')[1])
    expect(params.getAll('parent_ids')).toEqual(ids)
  })

  it('limit 只在非默认值时才出现在 query 里', async () => {
    const calls = stubFetch()
    await listChunks({ limit: 200 })
    expect(calls[0][0]).toContain('limit=200')
    await listChunks({ limit: 50 })
    expect(calls[1][0]).not.toContain('limit=')
  })
})

// 这条会改写 global.XMLHttpRequest 并设置模块级令牌，结尾自己拆桩（见下），
// 所以它排在哪都无害——不再靠"排在文件最末尾"来防继承。
it('上传用 XHR 也带上 Bearer 头——它是全项目唯一不走 client.js 的出口', async () => {
  const headers = {}
  global.XMLHttpRequest = class {
    constructor() { this.upload = {} }
    open() {}
    setRequestHeader(k, v) { headers[k] = v }
    send() {
      this.status = 201
      this.responseText = JSON.stringify({ id: 1, filename: 'a.txt', chunk_count: 1,
                                           created_at: '2026-10-06T12:00:00' })
      this.onload()
    }
  }
  setAuthToken('tok-xhr')
  await uploadDocument(new File(['x'], 'a.txt'))
  expect(headers.Authorization).toBe('Bearer tok-xhr')
  // 收口：令牌与全局桩件都还原。今天只靠这条测排在文件末尾才无害，
  // 一旦有人在本文件后面追加测，没还原就会让它看到上一个账号的令牌。
  setAuthToken('')
  delete global.XMLHttpRequest
})

// Task 8：上传这条出口（XHR，全项目唯一不走 request/postStream 的）也要交状态码，
// 并且 401 一样得把界面喊回登录页——三条出口漏一条，"票过期了还停在原界面上"就还在。
describe('上传的失败出口也带状态码（Task 8）', () => {
  // jsdom 本来就有 XMLHttpRequest，这里换掉必须在 afterEach 里**还原**而不是 delete。
  // （上一节那条测就是 delete 的，而本节的 RealXHR 在收集阶段就抓好了真身，还原得回去。）
  const RealXHR = global.XMLHttpRequest

  afterEach(() => {
    global.XMLHttpRequest = RealXHR
    setUnauthorizedHandler(null)
  })

  it('XHR 的非 2xx 失败回 ApiError，状态码来自 xhr.status', async () => {
    let captured
    global.XMLHttpRequest = class {
      constructor() { captured = this; this.upload = {}; this.headers = {} }
      open() {}
      setRequestHeader(k, v) { this.headers[k] = v }
      send() {}
    }
    const file = { name: 'a.txt' }
    const p = uploadDocument(file)
    captured.status = 415
    captured.responseText = JSON.stringify({ detail: '只支持 txt / pdf / docx' })
    captured.onload()
    const err = await p.catch((e) => e)
    expect([err.status, err.message]).toEqual([415, '只支持 txt / pdf / docx'])
  })

  it('上传撞 401 同样触发登出回调（三条出口一条都不能漏）', async () => {
    let captured
    let hits = 0
    setUnauthorizedHandler(() => { hits += 1 })
    global.XMLHttpRequest = class {
      constructor() { captured = this; this.upload = {} }
      open() {} setRequestHeader() {} send() {}
    }
    const p = uploadDocument({ name: 'a.txt' })
    captured.status = 401
    captured.responseText = JSON.stringify({ detail: '未登录或登录已过期' })
    captured.onload()
    await expect(p).rejects.toBeInstanceOf(ApiError)
    expect(hits).toBe(1)
  })
})
