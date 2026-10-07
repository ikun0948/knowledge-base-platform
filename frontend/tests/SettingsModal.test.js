// SettingsModal 的四段各自把三件事钉死：发出去的字段名、成功之后 user 怎么变、
// api_key 原文在界面上出现过没有。第三件是全局铁律（决策 5 + spec 3.1），所以它有独立判据。
//
// 为什么八条都放在组件层而不是挂在 App 上：本弹窗**直接吃 useAuth() 的模块级单例**，
// 它写的是"当前这个人"。App 层的 ⚙ 开合与头像渲染归 App.auth-gate.test.js（Step 5 那两条），
// 这里只测弹窗自己的行为。
//
// 环境事实（都写死在本文件里）：
//   - vi.mock 的 factory 是**整体替换模块**：Task 8 的规矩，六个封装必须列全，
//     少列一个拿到的是 undefined，红的理由是 mock 落后而不是行为坏了。
//   - user 是 useAuth 的模块级 ref，测试直接写它（mountModal 的 overrides 也走这条路）：
//     这是本仓唯一能"以已登录身份挂载弹窗"的做法——App 层那条 vm/setupState 通道在这里不适用，
//     因为弹窗不是 App 子组件的 setupState。写完要清（beforeEach 的 clearAuth）。
//   - 桩的返回值一律用**后端真实形状**：profile/llm 回 `{user}`（整行），
//     password 回 null（204），三枚模型封装回 `{models, default_model}`（ModelsOut，**不是整行**）。
//     "ModelsOut 只有两个键"这件事正是判据 #5 要钉的东西，桩形状抄错就等于把判据抄空。
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

vi.mock('../src/api/auth.js', () => ({
  updateProfile: vi.fn(), updatePassword: vi.fn(), updateLlmConfig: vi.fn(),
  addModel: vi.fn(), removeModel: vi.fn(), setDefaultModel: vi.fn(),
}))

import { addModel, removeModel, setDefaultModel, updateLlmConfig, updatePassword, updateProfile }
  from '../src/api/auth.js'

import SettingsModal from '../src/components/SettingsModal.vue'
import { ApiError } from '../src/api/client.js'
import { useAuth } from '../src/composables/useAuth.js'

const ME = {
  id: 1, identifier: 'a@b.com', identifier_type: 'email', nickname: '小明', avatar: 'auto',
  llm_configured: true, llm_base_url: 'https://fake/v1', api_key_masked: 'sk-****7890',
  models: ['qwen-max'], default_model: 'qwen-max',
}

// overrides 是给"两行名单"那种前置条件用的：判据 #7 需要一个**别的键都不许动**的多行状态，
// 而 mountModal 每次都要从整行 ME 起步，所以参数化这一处、不在测里再手写整行。
function mountModal(overrides = {}) {
  useAuth().user.value = { ...ME, ...overrides }
  return mount(SettingsModal)
}

// 两个密码框在模板里只有 aria-label 可分辨（计划原文没给它们类名，也不该为一条测新增类名）
const oldPw = (w) => w.find('input[aria-label="原密码"]')
const newPw = (w) => w.find('input[aria-label="新密码"]')

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  useAuth().clearAuth()
  updateProfile.mockResolvedValue({ user: { ...ME, nickname: '改名了' } })
  updatePassword.mockResolvedValue(null)                    // 204
  updateLlmConfig.mockResolvedValue({ user: { ...ME, api_key_masked: 'sk-****9999' } })
  addModel.mockResolvedValue({ models: ['qwen-max', 'qwen-turbo'], default_model: 'qwen-max' })
  removeModel.mockResolvedValue({ models: ['qwen-max'], default_model: 'qwen-max' })
  setDefaultModel.mockResolvedValue({ models: ['qwen-max', 'qwen-turbo'], default_model: 'qwen-turbo' })
})

describe('SettingsModal：四段设置 + api_key 不上屏（阶段二 Task 9）', () => {
  it('昵称保存把原样（含首尾空格）交给 updateProfile，成功后 user 整行被后端回执覆盖', async () => {
    const w = mountModal()
    await w.find('.settings-nickname-input').setValue('  改名了  ')
    await w.find('.settings-profile-save').trigger('click')
    await flushPromises()
    // 不 trim：清洗是 api/auth.py 的事，前端抢先改会让"我只改了空格"那条 422 判据在界面上消失
    expect(updateProfile).toHaveBeenCalledWith({ nickname: '  改名了  ', avatar: 'auto' })
    expect(useAuth().user.value.nickname).toBe('改名了')   // trim 是后端做的，前端照抄回执

    // 变体：纯空白**一发都不发**。后端确实会回 422，但那句话在弹窗里读起来像"我没打上字"
    const w2 = mountModal()
    await w2.find('.settings-nickname-input').setValue('   ')
    await w2.find('.settings-profile-save').trigger('click')
    await flushPromises()
    expect(updateProfile).toHaveBeenCalledTimes(1)          // 上一段那一次，没有第三次
    expect(w2.find('.settings-profile-error').text()).toContain('昵称不能是空白')
  })

  it('api_key 输入框是 password 型，保存后整屏文本里搜不到原文，状态里也不留着它', async () => {
    const w = mountModal()
    await w.find('.settings-apikey-input').setValue('sk-abcdef1234567890')
    await w.find('.settings-llm-save').trigger('click')
    await flushPromises()
    expect(w.find('.settings-apikey-input').attributes('type')).toBe('password')
    expect(w.text()).not.toContain('sk-abcdef1234567890')   // 原文绝不上屏
    expect(w.find('.settings-masked').text()).toContain('sk-****9999')   // 上屏的只有掩码
    expect(w.find('.settings-apikey-input').element.value).toBe('')      // 提交即从状态里抹掉
  })

  it('凭证保存失败：user 一行都不变，错误只落在 llm 那一段，不串到隔壁', async () => {
    updateLlmConfig.mockRejectedValue(new ApiError('路由必须以 http:// 或 https:// 开头', 422))
    const w = mountModal()
    await w.find('.settings-apikey-input').setValue('sk-abcdef1234567890')
    await w.find('.settings-llm-save').trigger('click')
    await flushPromises()
    // 失败不许长得像成功：掩码还是打开弹窗时那一枚
    expect(useAuth().user.value.api_key_masked).toBe('sk-****7890')
    expect(w.find('.settings-masked').text()).toContain('sk-****7890')
    expect(w.find('.settings-llm-error').text()).toContain('路由必须以 http:// 或 https:// 开头')
    expect(w.find('.settings-profile-error').exists()).toBe(false)
    // 错误路径**故意不清**输入框：让用户改完直接重试（与成功路径的清空是一对，别写成同一个）
    expect(w.find('.settings-apikey-input').element.value).toBe('sk-abcdef1234567890')
  })

  it('改密码的两道本地门禁，与 204 之后把两个明文都从 DOM 抹掉', async () => {
    const w = mountModal()
    await oldPw(w).setValue('old-pass')
    await newPw(w).setValue('12345')                        // 5 位 < PASSWORD_MIN
    await w.find('.settings-password-save').trigger('click')
    await flushPromises()
    expect(updatePassword).not.toHaveBeenCalled()
    expect(w.find('.settings-password-error').text()).toContain('新密码至少 6 位')

    await newPw(w).setValue('old-pass')                     // 与原密码同串
    await w.find('.settings-password-save').trigger('click')
    await flushPromises()
    expect(updatePassword).not.toHaveBeenCalled()
    expect(w.find('.settings-password-error').text()).toContain('新密码不能和原密码相同')

    await newPw(w).setValue('new-pass-7')
    await w.find('.settings-password-save').trigger('click')
    await flushPromises()
    expect(updatePassword).toHaveBeenCalledWith({ oldPassword: 'old-pass', newPassword: 'new-pass-7' })
    // 204 没有任何回执可显示，不清的话两个明文密码就留在 DOM 里等下一个坐到电脑前的人（F12 一眼）
    expect(oldPw(w).element.value).toBe('')
    expect(newPw(w).element.value).toBe('')
  })

  it('加模型成功：名单渲染出两项，且除 models/default_model 之外的键一个都不动', async () => {
    const w = mountModal()
    await w.find('.settings-model-input').setValue('qwen-turbo')
    await w.find('.settings-model-add').trigger('submit')
    await flushPromises()
    expect(addModel).toHaveBeenCalledWith('qwen-turbo')
    expect(w.findAll('.settings-model-row')).toHaveLength(2)
    expect(w.find('.settings-model-input').element.value).toBe('')
    // ModelsOut 不是整行 user ⇒ 弹窗必须把两个键**合并**进去。
    // api_key_masked 这一格是判据本体：改成 patchMe(out) 那种"整行覆盖"就红在这里
    //（default_model 恰好同值，所以断言不能只钉 default_model）。
    expect(useAuth().user.value.models).toEqual(['qwen-max', 'qwen-turbo'])
    expect(useAuth().user.value.api_key_masked).toBe('sk-****7890')
    expect(useAuth().user.value.nickname).toBe('小明')
  })

  it('重复添加撞 409：后端那句原文上屏，名单一条不减', async () => {
    addModel.mockRejectedValue(new ApiError('该模型已在你的名单里', 409))
    const w = mountModal()
    await w.find('.settings-model-input').setValue('qwen-max')
    await w.find('.settings-model-add').trigger('submit')
    await flushPromises()
    expect(w.find('.settings-models-error').text()).toContain('该模型已在你的名单里')
    expect(w.findAll('.settings-model-row')).toHaveLength(1)   // 失败的写入不许先把行加上去
    expect(useAuth().user.value.models).toEqual(['qwen-max'])
    // 草稿留着让用户改成别的名字直接重试（与判据 #3 的失败路径同口径）
    expect(w.find('.settings-model-input').element.value).toBe('qwen-max')
  })

  it('删掉当前默认之后，"默认"标记落在回执里的新单项上', async () => {
    // 前置：两行名单，默认是 qwen-max（名单里第二行排在最晚，与字母序不同步，
    // 这样"取第一个"这条读侧兜底在界面上才有方向可言）
    const removeModelReturn = { models: ['qwen-turbo'], default_model: 'qwen-turbo' }
    removeModel.mockResolvedValue(removeModelReturn)
    const w = mountModal({ models: ['qwen-turbo', 'qwen-max'], default_model: 'qwen-max' })
    const rows = w.findAll('.settings-model-row')
    expect(rows).toHaveLength(2)
    // 逐行钉，不用 wrapper.find：那是全子树搜索，"第一行没有标记"会被第二行的命中顶掉
    expect(rows[0].find('.settings-default').exists()).toBe(false)   // qwen-turbo 非默认
    expect(rows[1].find('.settings-default').text()).toBe('默认')     // 默认在 qwen-max 身上

    // 删的是 qwen-max（当前默认）：第二行的删除按钮
    await w.findAll('.settings-model-drop')[1].trigger('click')
    await flushPromises()
    expect(removeModel).toHaveBeenCalledWith('qwen-max')
    expect(w.findAll('.settings-model-row')).toHaveLength(1)
    // 界面上"默认"跟着**回执**走，不是前端自己猜的
    expect(w.find('.settings-model-name').text()).toBe('qwen-turbo')
    expect(w.find('.settings-default').text()).toBe('默认')
    expect(useAuth().user.value.default_model).toBe('qwen-turbo')
  })

  it('关闭三态：点遮罩关、Escape 关、点弹窗内部不关', async () => {
    const w = mountModal()
    await w.find('.settings-panel').trigger('click')         // 内部点击（会从遮罩冒泡，但不是"点空白"）
    expect(w.emitted('close')).toBeFalsy()
    await w.find('.settings-backdrop').trigger('click')      // 遮罩本体
    expect(w.emitted('close')).toHaveLength(1)
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    expect(w.emitted('close')).toHaveLength(2)
  })
})
