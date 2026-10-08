// 已选块是"刷新后还得认得回来"的状态：只有 id 值得进 localStorage。
// 快照会在块被删/改名后说谎，所以读回必须整批去问后端，并以后端没返回来剪死 id。
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../src/api/documents.js', () => ({ listChunks: vi.fn() }))

import { listChunks } from '../src/api/documents.js'
// ApiError 来自未被 mock 的 client.js：钉档要钉的就是"真实网络层抛的那个形状"
import { ApiError } from '../src/api/client.js'
// 上限那枚数字归 constants.js（后端契约的镜像，pytest 两头钉），这里只从那里取
import { MAX_SELECTED_CHUNKS } from '../src/constants.js'
import { useChunkSelection } from '../src/composables/useChunkSelection.js'

const KEY = 'selected_parent_ids'

function chunk(parentId, docId = 3, filename = 'a.txt') {
  return { parent_id: parentId, document_id: docId, filename, suffix: 'txt',
           snippet: '片段', child_count: 2 }
}

beforeEach(() => {
  localStorage.clear()
  listChunks.mockReset()
})

describe('useChunkSelection', () => {
  it('toggle 追加并落盘，只落 id 不落快照', () => {
    const s = useChunkSelection()
    s.toggle(chunk('甲_p_0'))
    s.toggle(chunk('乙_p_0', 9, 'b.pdf'))
    expect(s.selectedParentIds.value).toEqual(['甲_p_0', '乙_p_0'])
    expect(JSON.parse(localStorage.getItem(KEY))).toEqual(['甲_p_0', '乙_p_0'])
    expect(localStorage.getItem(KEY)).not.toContain('snippet')
  })

  it('再点一次同一个块即取消，持久化同步', () => {
    const s = useChunkSelection()
    s.toggle(chunk('甲_p_0'))
    s.toggle(chunk('甲_p_0'))
    expect(s.selectedChunks.value).toEqual([])
    expect(JSON.parse(localStorage.getItem(KEY))).toEqual([])
  })

  it('第 51 块被拒：中文文案说清上限与出路，且不进集合不发盘', () => {
    const s = useChunkSelection()
    for (let i = 0; i < MAX_SELECTED_CHUNKS; i += 1) s.toggle(chunk(`p${i}`))
    expect(s.selectedCount.value).toBe(50)
    s.toggle(chunk('overflow'))
    expect(s.selectedCount.value).toBe(50)
    expect(s.selectionError.value).toContain('50')
    expect(JSON.parse(localStorage.getItem(KEY))).not.toContain('overflow')
  })

  it('hydrate 以后端返回为准：没返回的 id 就是死了，就地剪掉并回写', async () => {
    localStorage.setItem(KEY, JSON.stringify(['活_p_0', '死_p_1']))
    listChunks.mockResolvedValue([chunk('活_p_0')])
    const s = useChunkSelection()
    await s.hydrate()
    expect(s.selectedParentIds.value).toEqual(['活_p_0'])
    expect(JSON.parse(localStorage.getItem(KEY))).toEqual(['活_p_0'])
    expect(listChunks.mock.calls[0][0]).toEqual({ parentIds: ['活_p_0', '死_p_1'] })
  })

  it('hydrate 保住点选顺序，不按后端返回顺序重排', async () => {
    localStorage.setItem(KEY, JSON.stringify(['乙_p_0', '甲_p_0']))
    listChunks.mockResolvedValue([chunk('甲_p_0'), chunk('乙_p_0')])
    const s = useChunkSelection()
    await s.hydrate()
    expect(s.selectedParentIds.value).toEqual(['乙_p_0', '甲_p_0'])
  })

  it('本地没有选择时不打后端：一次空请求只会把错误横幅平白点亮', async () => {
    const s = useChunkSelection()
    await s.hydrate()
    expect(listChunks).not.toHaveBeenCalled()
    expect(s.selectedChunks.value).toEqual([])
  })

  it('脏 localStorage 读回即丢：非数组、非字符串元素、超长、超额都不进集合', async () => {
    localStorage.setItem(KEY, '不是 JSON')
    const a = useChunkSelection()
    await a.hydrate()
    expect(a.selectedChunks.value).toEqual([])

    localStorage.setItem(KEY, JSON.stringify(['ok_p_0', 7, '', 'x'.repeat(101), null]))
    listChunks.mockResolvedValue([chunk('ok_p_0')])
    const b = useChunkSelection()
    await b.hydrate()
    expect(listChunks.mock.calls.at(-1)[0]).toEqual({ parentIds: ['ok_p_0'] })

    localStorage.setItem(KEY, JSON.stringify(Array.from({ length: 80 }, (_, i) => `p${i}`)))
    listChunks.mockResolvedValue([])
    const c = useChunkSelection()
    await c.hydrate()
    expect(listChunks.mock.calls.at(-1)[0].parentIds).toHaveLength(50)
  })

  it('hydrate 失败只落文案、保留已有集合：面板不该因为一次网络失败就空掉', async () => {
    const s = useChunkSelection()
    s.toggle(chunk('甲_p_0'))
    listChunks.mockRejectedValue(new Error('无法连接后端，请确认 uvicorn 已在 :8000 运行'))
    localStorage.setItem(KEY, JSON.stringify(['甲_p_0', '乙_p_0']))
    await s.hydrate()
    expect(s.selectionError.value).toContain('无法连接后端')
    expect(s.selectedParentIds.value).toEqual(['甲_p_0'])
  })

  it('hydrate 失败：本地池一个键都不清，只说错误（一次网络抖动不许抹掉用户的选中项）', async () => {
    // 钉档（今天即绿，advisory ③）：useChunkSelection.js:53-56 的 catch 故意不 persist()，
    // 于是 selected_parent_ids 原样留在 localStorage——这件事之前只有注释担保。
    // ApiError 用真形状（status=0 就是"连不上"），mock 掉网络层等于没钉这一格。
    localStorage.setItem(KEY, JSON.stringify(['活_p_0', '死_p_1']))
    listChunks.mockRejectedValue(new ApiError('无法连接后端，请确认 uvicorn 已在 :8000 运行', 0))
    const sel = useChunkSelection()
    await sel.hydrate()
    expect(sel.selectionError.value).toContain('无法连接后端')
    expect(sel.selectedChunks.value).toEqual([])                 // 内存里没建起来
    // 判据本体：localStorage **原样**，既不回写空数组也不剪枝
    expect(JSON.parse(localStorage.getItem(KEY))).toEqual(['活_p_0', '死_p_1'])
    // 清它的唯一入口是 clearSelection()——阶段一终审明写"今天承重别删"：
    // 它是登出/401 自动登出时把上一个账号的选中池抹掉的唯一动作（App.vue 的 resetWorkspace 调它）
    sel.clearSelection()
    expect(localStorage.getItem(KEY)).toBe('[]')
  })

  it('remove 只按 parent_id 摘，isSelected 跟着变', () => {
    const s = useChunkSelection()
    s.toggle(chunk('甲_p_0'))
    expect(s.isSelected('甲_p_0')).toBe(true)
    s.remove('甲_p_0')
    expect(s.isSelected('甲_p_0')).toBe(false)
    expect(JSON.parse(localStorage.getItem(KEY))).toEqual([])
  })

  it('clearSelection 把集合与本地存储一起清掉', () => {
    const s = useChunkSelection()
    s.toggle(chunk('甲_p_0'))
    s.clearSelection()
    expect(localStorage.getItem(KEY)).toBe('[]')
    expect(s.selectedChunks.value).toEqual([])
  })
})
