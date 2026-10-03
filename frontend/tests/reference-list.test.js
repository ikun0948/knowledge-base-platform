// M-F2 收口回归：`文件名(#id)` 这个格式必须只有 docLabel 一个实现——
// 测试同时吃"文档形状（id）"与"Reference 形状（document_id）"两种入参，
// 并钉住 ReferenceList 渲染走的就是这条唯一出处。
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import { docLabel } from '../src/composables/useDocuments.js'
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
