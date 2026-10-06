// 面板与弹窗共用 ChunkCard，两处的"点一下"语义必须相反又不打架：
// 弹窗里点卡片=选中/取消，面板里右上角那个 ✕=取消选择（本地动作，不发请求）。
// 2026-10-06：🗑（真删数据，不可逆）从消息引用条搬进弹窗，每行一个；
// 卡面同时只挂一个角标按钮（面板 ✕ / 弹窗 🗑），文案必须区分，混了会让人以为点一下就丢数据。
// 卡片正文（snippet）不再直接显示，改挂原生 title 悬浮——两列布局下放两行字就挤。
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { h, nextTick, ref } from 'vue'

vi.mock('../src/api/documents.js', () => ({ listChunks: vi.fn(), deleteChunk: vi.fn() }))

import ChunkCard from '../src/components/ChunkCard.vue'
import ChunkPickerModal from '../src/components/ChunkPickerModal.vue'
import { deleteChunk, listChunks } from '../src/api/documents.js'

const chunk = { parent_id: '手册.pdf_parent_0', document_id: 7, filename: '手册.pdf',
                suffix: 'pdf', snippet: '片段一', child_count: 3 }

beforeEach(() => {
  listChunks.mockReset()
  listChunks.mockResolvedValue([chunk])
  deleteChunk.mockReset()
  deleteChunk.mockResolvedValue({ deleted: true })
})

describe('ChunkCard', () => {
  it('卡面只显示文件名与块序号，正文不在卡面上', () => {
    const wrapper = mount(ChunkCard, { props: { chunk } })
    expect(wrapper.text()).toContain('手册.pdf #0')
    expect(wrapper.text()).not.toContain('片段一')
    expect(wrapper.text()).not.toContain('手册.pdf_parent_0')
  })

  it('悬浮 title 才是正文：块内容 + 块 id + 子块数', () => {
    const title = mount(ChunkCard, { props: { chunk } }).find('.chunk-card-body').attributes('title')
    expect(title).toContain('片段一')
    expect(title).toContain('手册.pdf_parent_0')
    expect(title).toContain('3 个子块')
  })

  it('parent_id 尾部没有 _parent_N 时退成纯文件名，不显示 undefined', () => {
    const text = mount(ChunkCard, { props: { chunk: { ...chunk, parent_id: '手册.pdf_p_0' } } }).text()
    expect(text).toContain('手册.pdf')
    expect(text).not.toMatch(/undefined|##/)
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

  it('deletable 才给删除按钮，文案说的是删数据', () => {
    const plain = mount(ChunkCard, { props: { chunk } })
    expect(plain.find('.chunk-delete').exists()).toBe(false)

    const card = mount(ChunkCard, { props: { chunk, deletable: true } })
    expect(card.find('.chunk-delete').attributes('aria-label')).toBe('删除这个文档块')
    expect(card.find('.chunk-remove').exists()).toBe(false)
  })

  it('点删除按钮只 emit delete(整块)，不连带 toggle', async () => {
    const card = mount(ChunkCard, { props: { chunk, deletable: true } })
    await card.find('.chunk-delete').trigger('click')
    expect(card.emitted('delete')).toEqual([[chunk]])
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

  it('点红叉只 emit remove，不连带 emit toggle（同一卡片两个动作不能双触发）', async () => {
    const card = mount(ChunkCard, { props: { chunk, removable: true } })
    await card.find('.chunk-remove').trigger('click')
    expect(card.emitted('remove')).toEqual([[chunk.parent_id]])
    expect(card.emitted('toggle')).toBeUndefined()
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

  // 2026-10-06：🗑 从消息引用条搬到这里。删的是向量库里的真数据、不可逆，
  // 所以原生 confirm 这道门禁跟着搬过来，而且必须先于任何请求。
  describe('删除闭环', () => {
    let confirm
    beforeEach(() => { confirm = vi.spyOn(window, 'confirm') })
    afterEach(() => confirm.mockRestore())

    it('每一行都给删除按钮', async () => {
      const wrapper = mount(ChunkPickerModal, { props })
      await flushPromises()
      expect(wrapper.findAll('.chunk-delete')).toHaveLength(1)
    })

    it('confirm 取消 ⇒ 一个请求都不发，行也不减', async () => {
      confirm.mockReturnValue(false)
      const wrapper = mount(ChunkPickerModal, { props })
      await flushPromises()
      await wrapper.find('.chunk-delete').trigger('click')
      await flushPromises()
      expect(deleteChunk).not.toHaveBeenCalled()
      expect(wrapper.findAll('.chunk-card')).toHaveLength(1)
    })

    it('confirm 确认 ⇒ 按 (document_id, parent_id) 删、本地剔行、整块 emit 给 App', async () => {
      confirm.mockReturnValue(true)
      const wrapper = mount(ChunkPickerModal, { props })
      await flushPromises()
      await wrapper.find('.chunk-delete').trigger('click')
      await flushPromises()
      expect(deleteChunk).toHaveBeenCalledWith(7, '手册.pdf_parent_0')
      // 这块已经死了：留在结果里等于挂一张必然空召回的卡片
      expect(wrapper.findAll('.chunk-card')).toHaveLength(0)
      expect(wrapper.emitted('chunk-deleted')).toEqual([[chunk]])
    })

    it('删失败 ⇒ 行留着、不报成功，错误顶在弹窗自己的错误位', async () => {
      confirm.mockReturnValue(true)
      deleteChunk.mockRejectedValue(new Error('无法连接后端，删除中断'))
      const wrapper = mount(ChunkPickerModal, { props })
      await flushPromises()
      await wrapper.find('.chunk-delete').trigger('click')
      await flushPromises()
      expect(wrapper.findAll('.chunk-card')).toHaveLength(1)
      expect(wrapper.emitted('chunk-deleted')).toBeUndefined()
      expect(wrapper.find('.picker-error').text()).toContain('无法连接后端')
    })

    // 连点两下会发两次 DELETE，第二次只能拿 404，然后界面显示"删除失败"其实数据早没了
    it('删除进行中不重复发请求', async () => {
      confirm.mockReturnValue(true)
      let release
      deleteChunk.mockImplementation(() => new Promise((resolve) => { release = resolve }))
      const wrapper = mount(ChunkPickerModal, { props })
      await flushPromises()
      const button = wrapper.find('.chunk-delete')
      await button.trigger('click')
      expect(button.attributes('disabled')).toBeDefined()
      await button.trigger('click')
      expect(deleteChunk).toHaveBeenCalledTimes(1)
      release({ deleted: true })
      await flushPromises()
    })
  })
})
