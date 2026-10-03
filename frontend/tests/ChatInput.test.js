// ChatInput 的停止/发送双态回归：pending 决定"⏹ 停止生成"还是"发送"，
// 这条互斥是停止按钮交付的核心 UI 行为，之前只靠浏览器手测。
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import ChatInput from '../src/components/ChatInput.vue'

function mountInput(props) {
  return mount(ChatInput, { props: { modelValue: '', ...props } })
}

describe('ChatInput：非 pending（发送态）', () => {
  it('空/纯空白输入时发送按钮 disabled，有字则可点且 emit 去空格后的文本', async () => {
    const empty = mountInput({ modelValue: '   ' })
    expect(empty.find('button').attributes('disabled')).toBeDefined()

    const wrapper = mountInput({ modelValue: '  你好  ' })
    const btn = wrapper.find('button')
    expect(btn.attributes('disabled')).toBeUndefined()
    await btn.trigger('click')
    expect(wrapper.emitted('send')).toEqual([['你好']])
  })

  it('Enter 发送、Shift+Enter 换行不发送', async () => {
    const wrapper = mountInput({ modelValue: 'q' })
    const textarea = wrapper.find('textarea')
    await textarea.trigger('keydown', { key: 'Enter', shiftKey: true })
    expect(wrapper.emitted('send')).toBeUndefined()
    await textarea.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('send')).toEqual([['q']])
  })

  it('输入框 input 事件回传 modelValue', async () => {
    const wrapper = mountInput({})
    await wrapper.find('textarea').setValue('打字')
    expect(wrapper.emitted('update:modelValue').at(-1)).toEqual(['打字'])
  })
})

describe('ChatInput：pending（生成中/停止态）', () => {
  it('显示“⏹ 停止生成”且只有这一个按钮，textarea 被禁用', () => {
    const wrapper = mountInput({ pending: true, modelValue: 'q' })
    const buttons = wrapper.findAll('button')
    expect(buttons).toHaveLength(1)
    expect(buttons[0].text()).toBe('⏹ 停止生成')
    expect(wrapper.find('textarea').attributes('disabled')).toBeDefined()
  })

  it('点停止 emit stop；此态下 Enter 不会再发 send（submit 有 pending 门禁）', async () => {
    const wrapper = mountInput({ pending: true, modelValue: 'q' })
    await wrapper.find('button').trigger('click')
    expect(wrapper.emitted('stop')).toHaveLength(1)
    await wrapper.find('textarea').trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('send')).toBeUndefined()
  })
})
