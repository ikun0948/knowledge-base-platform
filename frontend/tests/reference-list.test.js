// M-F2 收口回归：`文件名(#id)` 这个格式必须只有 docLabel 一个实现——
// 测试同时吃"文档形状（id）"与"Reference 形状（document_id）"两种入参，
// 并钉住 ReferenceList 渲染走的就是这条唯一出处。
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import { docLabel } from '../src/composables/useDocuments.js'
import MessageList from '../src/components/MessageList.vue'
import ReferenceList from '../src/components/ReferenceList.vue'

describe('docLabel（M-F2：格式唯一出处）', () => {
  it('文档形状用 id', () => {
    expect(docLabel({ filename: '甲.txt', id: 3 })).toBe('甲.txt(#3)')
  })

  it('Reference 形状用 document_id', () => {
    expect(docLabel({ filename: '乙.pdf', document_id: 7 })).toBe('乙.pdf(#7)')
  })
})

describe('ReferenceList 渲染', () => {
  it('每条引用的来源行 = 📎 + docLabel(reference)，不再内联重复格式', () => {
    const wrapper = mount(ReferenceList, {
      props: {
        references: [
          { document_id: 3, parent_id: 'p1', filename: '甲.txt', snippet: '片段一' },
          { document_id: 7, parent_id: 'p2', filename: '乙.pdf', snippet: '片段二' },
        ],
      },
    })
    const sources = wrapper.findAll('.reference-source').map((n) => n.text())
    expect(sources).toEqual(['📎 甲.txt(#3)', '📎 乙.pdf(#7)'])
    expect(wrapper.findAll('.reference-item')).toHaveLength(2)
  })
})

describe('ReferenceList 删除块入口', () => {
  const references = [
    { document_id: 3, parent_id: 'a.txt_parent_0', filename: '甲.txt', snippet: '片段一' },
    { document_id: 3, parent_id: 'a.txt_parent_1', filename: '甲.txt', snippet: '片段二', deleted: true },
  ]

  it('未删除的引用带删除按钮，点击 emit 出定位所需的 (document_id, parent_id)', async () => {
    const wrapper = mount(ReferenceList, { props: { references } })
    const buttons = wrapper.findAll('.chunk-delete')
    // 第二条已经删过，不该再给一次点击的机会
    expect(buttons).toHaveLength(1)
    await buttons[0].trigger('click')
    expect(wrapper.emitted('remove-chunk')).toEqual([[{ document_id: 3, parent_id: 'a.txt_parent_0' }]])
  })

  it('已删除的条目留在列表里标灰：它是那一轮答案用过什么的凭据，抹掉等于篡改历史', () => {
    const wrapper = mount(ReferenceList, { props: { references } })
    const items = wrapper.findAll('.reference-item')
    expect(items).toHaveLength(2)
    expect(items[1].classes()).toContain('reference-deleted')
    expect(items[1].text()).toContain('已删除')
    expect(items[0].text()).not.toContain('已删除')
  })
})

// 2026-10-04 浏览器手测抓到的真缺陷：MessageList 写了 defineEmits(['remove-chunk'])，
// 却没在 <MessageBubble> 上挂监听器，事件到这一跳就断了。分层单测全绿、按钮却点了没反应，
// 所以这条从最外层挂载、走完整条链，任何一跳掉监听都会红。
describe('删除块事件三跳链路（ReferenceList → MessageBubble → MessageList）', () => {
  it('点最里层的删除按钮，(document_id, parent_id) 必须冒到 MessageList', async () => {
    const wrapper = mount(MessageList, {
      props: {
        hasDocuments: true,
        messages: [{
          key: 'm1',
          role: 'assistant',
          content: '答',
          mode: 'rag',
          streaming: false,
          references: [{ document_id: 3, parent_id: 'a.txt_parent_0', filename: '甲.txt', snippet: '片段' }],
        }],
      },
    })
    await wrapper.find('.chunk-delete').trigger('click')
    expect(wrapper.emitted('remove-chunk')).toEqual([[{ document_id: 3, parent_id: 'a.txt_parent_0' }]])
  })
})
