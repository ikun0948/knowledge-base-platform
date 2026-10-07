// AuthPanel 只管两件事：tab 切换与"格式坏值不发请求"。
// 它不碰 API（登录成功后的 setSession 归 App.vue 编排），所以这里一个 fetch 桩都不需要。
import { afterEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import AuthPanel from '../src/components/AuthPanel.vue'
import { useAuth } from '../src/composables/useAuth.js'

const { authBusy, authError } = useAuth()

afterEach(() => {
  // useAuth 的状态是模块级的（没有 Pinia 的代价，Task 6 已记），
  // 上一条测把 authBusy 拨成 true 不还回去，下一条就莫名点不动提交按钮
  authBusy.value = false
  authError.value = ''
})

function fields(wrapper) {
  return {
    identifier: wrapper.findAll('input[type="text"]')[0],
    password: wrapper.find('input[type="password"]'),
    nickname: wrapper.findAll('input[type="text"]')[1],
    typeSelect: wrapper.find('select'),
    submit: wrapper.find('button[type="submit"]'),
  }
}

async function toRegister(wrapper) {
  await wrapper.findAll('.picker-tab')[1].trigger('click')
}

describe('AuthPanel：默认登录态', () => {
  it('只有账号与密码两个输入框，按钮写「登录」', () => {
    const { identifier, password, nickname, typeSelect, submit } = fields(mount(AuthPanel))
    expect(identifier.exists()).toBe(true)
    expect(password.exists()).toBe(true)
    expect(nickname).toBeUndefined()
    expect(typeSelect.exists()).toBe(false)
    expect(submit.text()).toBe('登录')
  })

  it('登录时邮箱归一小写、手机号原样（与后端 LoginIn 的分支同口径）', async () => {
    const wrapper = mount(AuthPanel)
    const { identifier, password, submit } = fields(wrapper)
    await identifier.setValue('A@B.com')
    await password.setValue('hunter2')
    await submit.trigger('click')
    expect(wrapper.emitted('submit')[0][0].payload.identifier).toBe('a@b.com')

    const phone = mount(AuthPanel)
    const pf = fields(phone)
    await pf.identifier.setValue('13800138000')
    await pf.password.setValue('hunter2')
    await pf.submit.trigger('click')
    expect(phone.emitted('submit')[0][0].mode).toBe('login')
    expect(phone.emitted('submit')[0][0].payload.identifier).toBe('13800138000')
  })
})

describe('AuthPanel：切到注册', () => {
  it('出现账号类型选择与昵称框，按钮写「注册并进入」', async () => {
    const wrapper = mount(AuthPanel)
    await toRegister(wrapper)
    const { nickname, typeSelect, submit } = fields(wrapper)
    expect(typeSelect.exists()).toBe(true)
    expect(nickname.exists()).toBe(true)
    expect(submit.text()).toBe('注册并进入')
  })

  it('合法邮箱注册：payload 带 identifierType 与已归一的 identifier', async () => {
    const wrapper = mount(AuthPanel)
    await toRegister(wrapper)
    const { identifier, password, nickname, submit } = fields(wrapper)
    await identifier.setValue('Me@Example.COM')
    await password.setValue('hunter2')
    await nickname.setValue('小明')
    await submit.trigger('click')
    expect(wrapper.emitted('submit')[0][0]).toEqual({
      mode: 'register',
      payload: { identifierType: 'email', identifier: 'me@example.com', password: 'hunter2', nickname: '小明' },
    })
  })

  it('选手机号时按手机号规则校验（1 开头 11 位）', async () => {
    const wrapper = mount(AuthPanel)
    await toRegister(wrapper)
    await wrapper.find('select').setValue('phone')
    const { identifier, password, submit } = fields(wrapper)
    await identifier.setValue('23800138000')
    await password.setValue('hunter2')
    await submit.trigger('click')
    expect(wrapper.emitted('submit')).toBeUndefined()
    expect(wrapper.find('.picker-error').text()).toBe('手机号格式不正确')
  })
})

describe('AuthPanel：坏值不发请求', () => {
  it('坏邮箱 / 短密码各自出中文文案，点提交不 emit', async () => {
    // 坏值时按钮本身已被 fieldError 置成 disabled，这里的"不 emit"于是有两条腿：
    // disabled 挡掉事件、submit() 里的门禁再挡一次。不管测试库对 disabled 元素派发不派发事件，
    // 判据都成立——这正是想要的口径。
    const wrapper = mount(AuthPanel)
    const { identifier, password, submit } = fields(wrapper)
    await identifier.setValue('a@b')
    await password.setValue('hunter2')
    await submit.trigger('click')
    expect(wrapper.emitted('submit')).toBeUndefined()
    expect(wrapper.find('.picker-error').text()).toBe('邮箱格式不正确')

    await identifier.setValue('a@b.com')
    await password.setValue('12345')
    await submit.trigger('click')
    expect(wrapper.emitted('submit')).toBeUndefined()
    expect(wrapper.find('.picker-error').text()).toBe('密码至少 6 位')

    await identifier.setValue('')
    expect(wrapper.find('.picker-error').text()).toBe('请填写账号')
  })

  it('authBusy 时按钮 disabled 且点不出第二次 emit', async () => {
    const wrapper = mount(AuthPanel)
    const { identifier, password, submit } = fields(wrapper)
    await identifier.setValue('a@b.com')
    await password.setValue('hunter2')
    authBusy.value = true
    // 必须等一次 flush：disabled 是渲染出来的属性，改了 ref 不重渲染就还是旧 DOM
    await wrapper.vm.$nextTick()
    expect(submit.attributes('disabled')).toBeDefined()
    await submit.trigger('click')
    expect(wrapper.emitted('submit')).toBeUndefined()

    authBusy.value = false
    await wrapper.vm.$nextTick()
    await submit.trigger('click')
    expect(wrapper.emitted('submit')).toHaveLength(1)
  })

  it('后端文案（authError）在字段本地合法时才显示，一旦判出坏值立刻让位', async () => {
    const wrapper = mount(AuthPanel)
    const { identifier, password } = fields(wrapper)
    authError.value = '账号或密码不正确'
    // 空表单时 fieldError 是「请填写账号」，它会压住后端文案——这是刻意的：
    // 连该填的都没填完，上一次失败的原因对当下没有帮助
    await identifier.setValue('a@b.com')
    await password.setValue('hunter2')
    expect(wrapper.find('.picker-error').text()).toBe('账号或密码不正确')

    await identifier.setValue('bad')
    expect(wrapper.find('.picker-error').text()).toBe('邮箱格式不正确')
  })
})
