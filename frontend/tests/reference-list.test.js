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

// 2026-10-06：删除入口从消息引用条搬进选择弹窗（删数据只留一个入口）。
// 判据仍从最外层 MessageList 挂载来跑：链路上任何一跳残留按钮都会红。
describe('ReferenceList 不挂删除入口（已搬到选择弹窗）', () => {
  const references = [
    { document_id: 3, parent_id: 'a.txt_parent_0', filename: '甲.txt', snippet: '片段一' },
    { document_id: 3, parent_id: 'a.txt_parent_1', filename: '甲.txt', snippet: '片段二', deleted: true },
  ]

  it('引用条上没有删除按钮：未删除的条目也不给', () => {
    const wrapper = mount(ReferenceList, { props: { references } })
    expect(wrapper.findAll('.chunk-delete')).toHaveLength(0)
  })

  it('从 MessageList 最外层也找不到删除按钮：三跳链路退役后不能留半截', () => {
    const wrapper = mount(MessageList, {
      props: {
        hasDocuments: true,
        messages: [{
          key: 'm1',
          role: 'assistant',
          content: '答',
          mode: 'rag',
          streaming: false,
          references,
        }],
      },
    })
    expect(wrapper.findAll('.chunk-delete')).toHaveLength(0)
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
