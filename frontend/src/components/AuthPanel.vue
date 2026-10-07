<script setup>
import { computed, reactive, ref, watch } from 'vue'

import { useAuth } from '../composables/useAuth.js'

// 与后端 schemas/auth.py 同一套口径（那边才是权威；改动要两边一起改）。
// 这里不是防线，只是让人少跑一趟网络：绕过界面直接打 /api/auth/register 照样 422。
// **只有注册分支用这两条正则**：后端 LoginIn 对账号形状完全不验（只 strip，含 @ 才归一小写），
// 所以登录 tab 也不验——本地一加校验就比后端严，而 core/migrations.py 的 DEFAULT_IDENTIFIER
// 是启动期迁移直接 INSERT 进 users 的 `default@local`，域名没有点、过不了 EMAIL_RE，
// 那正是界面上唯一的旧数据入口。新增登录入口（阶段二的用户名登录）时不要顺手在这里补校验。
const EMAIL_RE = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/
const PHONE_RE = /^1[3-9]\d{9}$/
const PASSWORD_MIN = 6
const PASSWORD_MAX = 64
const NICKNAME_MAX = 50 // 对齐 users.nickname 的 String(50)

const emit = defineEmits(['submit'])
// authBusy/authError 是模块级 ref：谁发起登录都是同一份忙态与文案，
// 所以这个组件既不需要 props，也不需要在 emit 之后自己收尾
const { authBusy, authError } = useAuth()

const mode = ref('login')
const form = reactive({ identifierType: 'email', identifier: '', password: '', nickname: '' })

// 切 tab 只清文案不清字段：同一个人往往两个 tab 用同一个邮箱，
// 清了字段就等于让"填错切回去看看"变成重打一遍
watch(mode, () => { authError.value = '' })

const fieldError = computed(() => {
  const identifier = form.identifier.trim()
  if (!identifier) return '请填写账号'
  // 账号形状只在注册态判（后端 RegisterIn 按 identifierType 拒 422）；
  // 登录态只做"非空 + 密码长度"两道，形状交给后端——理由见文件顶部 EMAIL_RE 那条注释。
  if (mode.value === 'register') {
    if (form.identifierType === 'email') {
      if (!EMAIL_RE.test(identifier)) return '邮箱格式不正确'
    } else if (!PHONE_RE.test(identifier)) {
      return '手机号格式不正确'
    }
  }
  if (form.password.length < PASSWORD_MIN) return `密码至少 ${PASSWORD_MIN} 位`
  if (form.password.length > PASSWORD_MAX) return `密码最多 ${PASSWORD_MAX} 位`
  if (mode.value === 'register' && form.nickname.trim().length > NICKNAME_MAX) return `昵称最多 ${NICKNAME_MAX} 个字符`
  return ''
})

// 登录不锁类型：后端按有没有 @ 归一（LoginIn 只收 identifier + password）。
// 只有邮箱归一小写——照抄 normalize_identifier 的分支，否则"A@B.com 注册、a@b.com 登录"
// 这种"明明是同一个账号却说不存在"的错觉会在界面里生根。
function normalizedIdentifier() {
  const raw = form.identifier.trim()
  if (mode.value === 'login') return raw.includes('@') ? raw.toLowerCase() : raw
  return form.identifierType === 'email' ? raw.toLowerCase() : raw
}

function submit() {
  // 门禁两道：忙态防双击（第二次只会撞上 409），坏值防白跑一趟。
  // disabled 那一腿在真实浏览器里就把点击吞了，这条是留给"事件绕过 disabled"
  // （编程派发 / 辅助技术触发）的第二次机会——别把它当冗余删掉。
  if (authBusy.value || fieldError.value) return
  emit('submit', {
    mode: mode.value,
    payload: {
      identifierType: form.identifierType,
      identifier: normalizedIdentifier(),
      password: form.password,
      nickname: form.nickname.trim(),
    },
  })
}
</script>

<template>
  <section class="auth-panel">
    <h1 class="auth-title">🔑 知识库平台</h1>

    <div class="picker-tabs">
      <button
        class="picker-tab"
        :class="{ 'picker-tab-active': mode === 'login' }"
        type="button"
        @click="mode = 'login'"
      >登录</button>
      <button
        class="picker-tab"
        :class="{ 'picker-tab-active': mode === 'register' }"
        type="button"
        @click="mode = 'register'"
      >注册</button>
    </div>

    <!-- 只有一个提交入口：form + @submit.prevent。在输入框里按回车是登录最常见的手势，
         浏览器会把它变成对默认按钮的隐式提交 → 表单的 submit 事件；.prevent 负责不把整页刷掉。
         提交按钮上不许再挂一个点击处理器：那会让一次手势走两条腿，
         "只 emit 一次"就只系于一个 .prevent 修饰符——真实浏览器里点一次登录发两次 POST，第二次撞 409。 -->
    <form class="auth-form" @submit.prevent="submit">
      <label class="auth-field">
        <span>账号</span>
        <input
          v-model="form.identifier"
          class="picker-input"
          type="text"
          autocomplete="username"
          :placeholder="mode === 'login' ? '邮箱或手机号' : '填邮箱或手机号'"
        />
      </label>

      <label v-if="mode === 'register'" class="auth-field">
        <span>账号类型</span>
        <select v-model="form.identifierType" class="picker-input">
          <option value="email">邮箱</option>
          <option value="phone">手机号</option>
        </select>
      </label>

      <label class="auth-field">
        <span>密码</span>
        <input
          v-model="form.password"
          class="picker-input"
          type="password"
          :autocomplete="mode === 'login' ? 'current-password' : 'new-password'"
          placeholder="至少 6 位"
        />
      </label>

      <label v-if="mode === 'register'" class="auth-field">
        <span>昵称（可留空）</span>
        <input v-model="form.nickname" class="picker-input" type="text" :maxlength="NICKNAME_MAX" placeholder="左下角显示的名字" />
      </label>

      <!-- 本地格式提示优先于后端上次的失败文案：已经知道这串不是邮箱时，
           再提"账号或密码不正确"只会把人往错的方向引 -->
      <p v-if="fieldError" class="picker-error">{{ fieldError }}</p>
      <p v-else-if="authError" class="picker-error">{{ authError }}</p>

      <button class="btn auth-submit" type="submit" :disabled="authBusy || !!fieldError">
        {{ authBusy ? (mode === 'login' ? '登录中…' : '注册中…') : (mode === 'login' ? '登录' : '注册并进入') }}
      </button>
      <p class="auth-hint">只校验格式，不发验证码；忘记密码暂无找回入口。</p>
    </form>
  </section>
</template>
