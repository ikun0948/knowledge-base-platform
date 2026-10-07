<script setup>
import { computed, reactive, ref, watch } from 'vue'

import { useAuth } from '../composables/useAuth.js'

// 与后端 schemas/auth.py 同一套口径（那边才是权威；改动要两边一起改）。
// 这里不是防线，只是让人少跑一趟网络：绕过界面直接打 /api/auth/register 照样 422。
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
  if (mode.value === 'register') {
    if (form.identifierType === 'email') {
      if (!EMAIL_RE.test(identifier)) return '邮箱格式不正确'
    } else if (!PHONE_RE.test(identifier)) {
      return '手机号格式不正确'
    }
  } else if (!PHONE_RE.test(identifier) && !EMAIL_RE.test(identifier)) {
    // 登录不锁类型（后端 LoginIn 按有没有 @ 分流），所以两个形状都得判——
    // 只判注册的话，坏邮箱在登录 tab 上是"本地放行、后端 401"，
    // 而 authError 里上一次失败的文案又会盖在输入框下面把人往错处引。
    // 两边都不合时报邮箱：手机号是「1 开头 11 位」的窄形状，落不进这个窄形状的人
    // 大概率是在输邮箱（'bad'、'a@b' 都属于这一类）。
    return '邮箱格式不正确'
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

    <!-- 回车能登录：靠的是 form + @submit.prevent（不会把整页刷掉）。
         按钮另外还挂 @click.prevent，两个原因：① 单测环境是 jsdom，它对 isTrusted=false 的
         click 不执行按钮的激活行为，"点提交"根本不会变成 submit 事件（VTU 的常规口径是让测试
         直接 trigger('submit')——但那样测的就不是"人点按钮"这个手势了）；
         ② 真实浏览器里回车隐式提交会对默认按钮派发 click，于是这条 @click 正是那条路径。
         .prevent 取消的是"点击提交表单"这个默认动作，所以一次手势只 emit 一次；
         @submit.prevent 留着兜 requestSubmit 这类不经按钮点击的提交。 -->
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

      <button class="btn auth-submit" type="submit" :disabled="authBusy || !!fieldError" @click.prevent="submit">
        {{ authBusy ? (mode === 'login' ? '登录中…' : '注册中…') : (mode === 'login' ? '登录' : '注册并进入') }}
      </button>
      <p class="auth-hint">只校验格式，不发验证码；忘记密码暂无找回入口。</p>
    </form>
  </section>
</template>
