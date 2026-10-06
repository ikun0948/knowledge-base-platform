// api/documents.js 的两个块级出口：删除块与候选池查询。这里唯一会咬人的是 parent_id：
// 它是 f"{文件名}_parent_{i}"，中文和空格都来自文件名本身、没被 _safe_filename 洗掉，
// 只能靠编码送进路径段。写错的坏法不是报错而是 404——"块不存在"，比崩还难查。
import { afterEach, describe, expect, it, vi } from 'vitest'

import { deleteChunk, listChunks, uploadDocument } from '../src/api/documents.js'
import { setAuthToken } from '../src/api/client.js'

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

// 放在文件末尾：这条会改写 global.XMLHttpRequest 并留下一个令牌，同文件里它之后不该再有测。
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
})
