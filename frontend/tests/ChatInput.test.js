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
    expect(empty.find('.chat-send').attributes('disabled')).toBeDefined()

    const wrapper = mountInput({ modelValue: '  你好  ' })
    const btn = wrapper.find('.chat-send')
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
    const buttons = wrapper.findAll('.chat-controls button')
    expect(buttons).toHaveLength(1)
    expect(buttons[0].text()).toBe('⏹ 停止生成')
    expect(wrapper.find('textarea').attributes('disabled')).toBeDefined()
  })

  it('点停止 emit stop；此态下 Enter 不会再发 send（submit 有 pending 门禁）', async () => {
    const wrapper = mountInput({ pending: true, modelValue: 'q' })
    await wrapper.find('.chat-stop').trigger('click')
    expect(wrapper.emitted('stop')).toHaveLength(1)
    await wrapper.find('textarea').trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('send')).toBeUndefined()
  })
})

// Task 10 的四条：两段结构、option 逐项来自名单、改选只回名字不顺手发送、空名单与生成中都禁用。
// 前三条钉的是"下拉在按钮左边、发出去的是名字"，第四条钉的是"没配模型时界面说人话"。
describe('ChatInput：两段式与模型下拉（Task 10）', () => {
  it('结构是两段：textarea 独占第一行，控件行的最后一个子节点才是发送按钮', () => {
    const w = mountInput({ modelValue: 'q', models: ['qwen-max'], selectedModel: 'qwen-max' })
    const kids = w.find('.chat-input').element.children
    expect(kids[0].className).toContain('chat-textarea')
    expect(kids[1].className).toContain('chat-controls')
    // 右对齐是 CSS 的事（justify-content），DOM 顺序只保证"下拉在按钮左边"这一件事。
    // 按 class 归属断而不是 classes()[0]：按钮写的是 class="btn chat-send"，
    // 只看第一个令牌会永远读到 'btn'，钉不出"谁是发送"。
    const controls = w.findAll('.chat-controls > *')
    expect(controls).toHaveLength(2)
    expect(controls[0].classes()).toContain('model-select')
    expect(controls[1].classes()).toContain('chat-send')
  })

  it('下拉的 option 逐个来自 models，值与文本都是模型名原样（含空格与中文）', () => {
    const w = mountInput({ modelValue: 'q', selectedModel: 'qwen 2.5/coder',
                           models: ['qwen 2.5/coder', '千问-max'] })
    const options = w.findAll('.model-select option')
    expect(options.map((o) => o.text())).toEqual(['qwen 2.5/coder', '千问-max'])
    expect(options.map((o) => o.element.value)).toEqual(['qwen 2.5/coder', '千问-max'])
    expect(w.find('.model-select').element.value).toBe('qwen 2.5/coder')
  })

  it('改选模型 emit update:selectedModel，值是新选中的那个名字（不是下标）', async () => {
    const w = mountInput({ modelValue: 'q', selectedModel: 'a', models: ['a', 'b'] })
    await w.find('.model-select').setValue('b')
    expect(w.emitted('update:selectedModel')).toEqual([['b']])
    // 下拉的 change 绝不能顺手把 send 也发出去（用户只是想换个模型）
    expect(w.emitted('send')).toBeUndefined()
  })

  it('名单为空 / 正在生成 两种情况下下拉都被禁用', () => {
    const empty = mountInput({ modelValue: 'q' })          // models 默认 () => []
    expect(empty.findAll('.model-select option')).toHaveLength(1)
    expect(empty.find('.model-select option').element.value).toBe('')
    expect(empty.find('.model-select').text()).toContain('名单为空')
    expect(empty.find('.model-select').attributes('disabled')).toBeDefined()

    const busy = mountInput({ modelValue: 'q', pending: true, models: ['a'] })
    expect(busy.find('.model-select').attributes('disabled')).toBeDefined()
  })

  it('allowSend=false：有字但发送按钮仍禁用，且 Enter 也发不出 send', async () => {
    const w = mountInput({ modelValue: '你好', allowSend: false, models: ['a'], selectedModel: 'a' })
    expect(w.find('.chat-send').attributes('disabled')).toBeDefined()
    await w.find('.chat-textarea').trigger('keydown', { key: 'Enter' })
    expect(w.emitted('send')).toBeUndefined()
  })
})
