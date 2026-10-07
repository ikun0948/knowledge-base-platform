// AuthPanel 只管两件事：tab 切换与"格式坏值不发请求"。
// 它不碰 API（登录成功后的 setSession 归 App.vue 编排），所以这里一个 fetch 桩都不需要。
//
// 提交手势为什么打在 form 上（wrapper.find('form').trigger('submit')），而不是按钮的 click：
// 本机 jsdom 30.1.1 对 isTrusted=false 的 click **不执行按钮的激活行为**，所以
// `submit.trigger('click')` 根本不会变成 submit 事件——@submit.prevent 那条路径永远不触发，
// 能测到的只有"按钮上另挂一条 @click"这条为测试环境改出来的接线（2026-10-07 修正轮 1 已撤掉）。
// 打在 form 上走的是生产里真实存在的那条 @submit.prevent，并且 submit 事件绕过按钮的 disabled
// 直达 submit()，于是组件内部那道 `if (authBusy || fieldError) return` 第一次有判据守着：
// DOM 层的 :disabled 与 submit() 内部的 return 两道防线，各由一条测钉住。
// 勘误：本文件与计划文原有那句"不管测试库对 disabled 元素派发不派发事件，判据都成立"只成立一半——
// "disabled 挡掉事件"这一半对，"内部门禁再挡一次"那一半在 trigger('click') 的旧测法下从不发生。
//
// 切 tab 仍然用 click（`.picker-tab` 是 type="button"，点它就是这个手势的真身，不存在激活行为问题）。
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
    const { identifier, password } = fields(wrapper)
    await identifier.setValue('A@B.com')
    await password.setValue('hunter2')
    await wrapper.find('form').trigger('submit')
    expect(wrapper.emitted('submit')[0][0].payload.identifier).toBe('a@b.com')

    const phone = mount(AuthPanel)
    const pf = fields(phone)
    await pf.identifier.setValue('13800138000')
    await pf.password.setValue('hunter2')
    await phone.find('form').trigger('submit')
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
    const { identifier, password, nickname } = fields(wrapper)
    await identifier.setValue('Me@Example.COM')
    await password.setValue('hunter2')
    await nickname.setValue('小明')
    await wrapper.find('form').trigger('submit')
    expect(wrapper.emitted('submit')[0][0]).toEqual({
      mode: 'register',
      payload: { identifierType: 'email', identifier: 'me@example.com', password: 'hunter2', nickname: '小明' },
    })
  })

  it('选手机号时按手机号规则校验（1 开头 11 位）', async () => {
    const wrapper = mount(AuthPanel)
    await toRegister(wrapper)
    await wrapper.find('select').setValue('phone')
    const { identifier, password } = fields(wrapper)
    await identifier.setValue('23800138000')
    await password.setValue('hunter2')
    await wrapper.find('form').trigger('submit')
    expect(wrapper.emitted('submit')).toBeUndefined()
    expect(wrapper.find('.picker-error').text()).toBe('手机号格式不正确')
  })
})

describe('AuthPanel：坏值不发请求', () => {
  // 2026-10-07 修正轮 1（X-1）：这条原来第一拍打的是"登录 tab 上 a@b → 邮箱格式不正确"，
  // 那是断言错，不是组件错——后端 LoginIn 不校验账号形状，前端替它校验就会把
  // core/migrations.py 启动期直接写进 users 表的 default@local 挡死（域名没有点、过不了 EMAIL_RE）。
  // 现在登录态只做"非空 + 密码长度"两道，形状交给后端；最后一段是本次缺陷的真判据。
  it('空账号与短密码各自出中文文案且不 emit；default@local 在登录 tab 本地放行', async () => {
    const wrapper = mount(AuthPanel)
    const { identifier, password, submit } = fields(wrapper)

    // 第一拍：空账号 → 本地挡下（文案 + 按钮 disabled）
    await identifier.setValue('')
    await password.setValue('hunter2')
    await wrapper.find('form').trigger('submit')
    expect(wrapper.emitted('submit')).toBeUndefined()
    expect(wrapper.find('.picker-error').text()).toBe('请填写账号')
    expect(submit.attributes('disabled')).toBeDefined()

    // 第二拍：账号形状合法、密码短了 → 换「密码至少 6 位」，仍然不 emit
    await identifier.setValue('a@b.com')
    await password.setValue('123')
    await wrapper.find('form').trigger('submit')
    expect(wrapper.emitted('submit')).toBeUndefined()
    expect(wrapper.find('.picker-error').text()).toBe('密码至少 6 位')

    // 第三拍（钉住本轮缺陷）：default@local 是 Task 3 那 13 行旧文档的主人，后端受理、界面必须放行。
    // normalizedIdentifier() 的登录分支只做"含 @ 才小写"，这串本来就全小写，于是原样出去。
    await identifier.setValue('default@local')
    await password.setValue('hunter2')
    expect(wrapper.find('.picker-error').exists()).toBe(false)
    expect(submit.attributes('disabled')).toBeUndefined()
    await wrapper.find('form').trigger('submit')
    expect(wrapper.emitted('submit')).toHaveLength(1)
    expect(wrapper.emitted('submit')[0][0].payload.identifier).toBe('default@local')
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
    await wrapper.find('form').trigger('submit')
    expect(wrapper.emitted('submit')).toBeUndefined()

    authBusy.value = false
    await wrapper.vm.$nextTick()
    await wrapper.find('form').trigger('submit')
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

    // 让位的那一拍改用短密码（登录 tab 也成立的本地判据）；
    // 原来这里 setValue('bad') 依赖的是登录态的形状校验，那条已按 X-1 撤掉。
    await password.setValue('123')
    expect(wrapper.find('.picker-error').text()).toBe('密码至少 6 位')
  })
})
