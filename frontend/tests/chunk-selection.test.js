// 面板与弹窗共用 ChunkCard，两处的"点一下"语义必须相反又不打架：
// 弹窗里点卡片=选中/取消，面板里右上角那个 ✕=取消选择（本地动作，不发请求）。
// 🗑（删除文档块）在引用条上，是另一回事——文案必须区分，混了会让人以为点一下就丢数据。
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { h, nextTick, ref } from 'vue'

vi.mock('../src/api/documents.js', () => ({ listChunks: vi.fn() }))

import ChunkCard from '../src/components/ChunkCard.vue'
import ChunkPickerModal from '../src/components/ChunkPickerModal.vue'
import { listChunks } from '../src/api/documents.js'

const chunk = { parent_id: '手册.pdf_parent_0', document_id: 7, filename: '手册.pdf',
                suffix: 'pdf', snippet: '片段一', child_count: 3 }

beforeEach(() => {
  listChunks.mockReset()
  listChunks.mockResolvedValue([chunk])
})

describe('ChunkCard', () => {
  it('三行内容：docLabel 格式唯一出处 + 片段 + 块与子块数', () => {
    const text = mount(ChunkCard, { props: { chunk } }).text()
    expect(text).toContain('手册.pdf(#7)')
    expect(text).toContain('片段一')
    expect(text).toContain('手册.pdf_parent_0')
    expect(text).toContain('3 个子块')
  })

  it('removable 才给红叉，且它的 aria-label 说的是"取消选择"不是"删除"', () => {
    const plain = mount(ChunkCard, { props: { chunk } })
    expect(plain.find('.chunk-remove').exists()).toBe(false)

    const card = mount(ChunkCard, { props: { chunk, removable: true } })
    const x = card.find('.chunk-remove')
    expect(x.attributes('aria-label')).toBe('取消选择')
    expect(x.text()).toBe('✕')
    expect(card.text()).not.toMatch(/删除文档块[^（]/)
  })

  it('点红叉只 emit remove，不连带 emit toggle（同一卡片两个动作不能双触发）', async () => {
    const card = mount(ChunkCard, { props: { chunk, removable: true } })
    await card.find('.chunk-remove').trigger('click')
    expect(card.emitted('remove')).toEqual([[chunk.parent_id]])
    expect(card.emitted('toggle')).toBeUndefined()
  })

  it('点卡片本体 emit toggle(整块)', async () => {
    const card = mount(ChunkCard, { props: { chunk, removable: true } })
    await card.find('.chunk-card-body').trigger('click')
    expect(card.emitted('toggle')).toEqual([[chunk]])
  })

  it('selected 时带角标与高亮类', () => {
    const card = mount(ChunkCard, { props: { chunk, selected: true } })
    expect(card.find('.chunk-badge').exists()).toBe(true)
    expect(card.classes()).toContain('chunk-card-selected')
  })
})

describe('ChunkPickerModal', () => {
  const props = { selectedIds: [], error: '' }

  it('一挂载就先查一次全量（弹窗要的是真值，不缓存上次的结果）', async () => {
    mount(ChunkPickerModal, { props })
    expect(listChunks).toHaveBeenCalledWith({ query: '', suffix: '' })
  })

  it('回车提交：关键词去空白后交给 listChunks', async () => {
    const wrapper = mount(ChunkPickerModal, { props })
    await wrapper.find('input').setValue('  手册  ')
    await wrapper.find('form').trigger('submit')
    expect(listChunks.mock.calls.at(-1)[0]).toEqual({ query: '手册', suffix: '' })
  })

  it('切分类用当前关键词立即重查', async () => {
    const wrapper = mount(ChunkPickerModal, { props })
    await wrapper.find('input').setValue('手册')
    await wrapper.findAll('.picker-tab')[2].trigger('click')   // DOCX
    expect(listChunks.mock.calls.at(-1)[0]).toEqual({ query: '手册', suffix: 'docx' })
    expect(wrapper.findAll('.picker-tab')[2].classes()).toContain('picker-tab-active')
  })

  it('点结果卡片 emit toggle(整块)；卡片本体不带红叉', async () => {
    const wrapper = mount(ChunkPickerModal, { props })
    // 一轮 microtask 不够：listChunks 的 promise 落地后还要等 Vue 调度器渲染那一轮
    await flushPromises()
    await wrapper.find('.chunk-card-body').trigger('click')
    expect(wrapper.emitted('toggle')).toEqual([[chunk]])
    expect(wrapper.find('.chunk-remove').exists()).toBe(false)
  })

  it('已选中的卡片带角标（选中状态在弹窗里也看得见）', async () => {
    const wrapper = mount(ChunkPickerModal, { props: { ...props, selectedIds: [chunk.parent_id] } })
    await flushPromises()
    expect(wrapper.find('.chunk-badge').exists()).toBe(true)
  })

  it('两种点击关闭：✕ 按钮与点遮罩空白；点内容区不关', async () => {
    const wrapper = mount(ChunkPickerModal, { props })
    await wrapper.find('.picker-close').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)

    await wrapper.find('.picker-backdrop').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(2)

    await wrapper.find('.picker-modal').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(2)   // 内容区点击不算"点空白"
    wrapper.unmount()
  })

  // Esc 的监听挂在 window 上（焦点在弹窗内任意处都吃得到），所以判据也必须从 window 派发：
  // wrapper.trigger 只会打到那个 DOM 节点，keydown 不会往下传。
  // 卸载那一半必须靠宿主组件的回调数组来观察：wrapper.unmount() 会连 VTU 的事件记录一起清掉，
  // 之后再读 wrapper.emitted() 只会拿到 undefined，"没响应"就成了永远成立的假判据。
  it('Esc 关闭，卸载后不再抢键盘', async () => {
    const closed = []
    const shown = ref(true)
    const Host = {
      setup() {
        return () => (shown.value
          ? h(ChunkPickerModal, { selectedIds: [], error: '', onClose: () => closed.push(1) })
          : null)
      },
    }
    mount(Host)
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    expect(closed).toHaveLength(1)

    shown.value = false
    await nextTick()   // 让 onUnmounted 跑掉：监听不摘就会跨用例、跨页面存活
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    expect(closed).toHaveLength(1)
  })

  it('上限文案顶在弹窗里而不是全局横幅：错在哪就说在哪', async () => {
    const wrapper = mount(ChunkPickerModal, { props: { ...props, error: '最多只能选择 50 个文档块' } })
    expect(wrapper.find('.picker-error').text()).toContain('50')
  })

  it('请求失败给一句能行动的中文，不把空白弹窗留给用户', async () => {
    listChunks.mockRejectedValue(new Error('无法连接后端，请确认 uvicorn 已在 :8000 运行'))
    const wrapper = mount(ChunkPickerModal, { props })
    await flushPromises()
    expect(wrapper.find('.picker-error').text()).toContain('无法连接后端')
    expect(wrapper.findAll('.chunk-card')).toHaveLength(0)
  })

  it('零命中时说"没有匹配"而不是空面板', async () => {
    listChunks.mockResolvedValue([])
    const wrapper = mount(ChunkPickerModal, { props })
    await flushPromises()
    expect(wrapper.find('.picker-hint').text()).toContain('没有匹配')
  })
})
