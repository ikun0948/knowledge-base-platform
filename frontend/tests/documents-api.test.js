// api/documents.js 的删除块出口。这里唯一会咬人的是 parent_id：
// 它是 f"{文件名}_parent_{i}"，中文和空格都来自文件名本身、没被 _safe_filename 洗掉，
// 只能靠编码送进路径段。写错的坏法不是报错而是 404——"块不存在"，比崩还难查。
import { afterEach, describe, expect, it, vi } from 'vitest'

import { deleteChunk } from '../src/api/documents.js'

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
