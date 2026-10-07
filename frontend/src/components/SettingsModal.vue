<script setup>
import { onMounted, onUnmounted, reactive, ref } from 'vue'

import {
  addModel, removeModel, setDefaultModel, updateLlmConfig, updatePassword, updateProfile,
} from '../api/auth.js'
import { useAuth } from '../composables/useAuth.js'

const emit = defineEmits(['close'])

// 直接吃 useAuth() 的模块级单例，不从 App.vue 往下传 props：
// 设置弹窗改的就是"当前这个人"，传一层会让 user 出现两份真相——
// 这个项目不引 Pinia（spec 5.1），代价就是组件要么自己 import composable，要么当纯展示件。
// 本弹窗有写动作，所以走 import。
const { user, patchMe } = useAuth()

// 预设头像：与 backend/api/auth.py:27 的 AVATARS 同源（Task 2）。改动必须两处一起，
// 漏一处的表征是"界面能选出一个后端必拒 422 的值"。'auto' 不是图片，是"用昵称首字母"的编码。
const AVATARS = ['auto', '😀', '🤖', '🦊', '🐼', '🚀']
const AVATAR_LABELS = { auto: '昵称首字母', '😀': '笑脸', '🤖': '机器人', '🦊': '狐狸', '🐼': '熊猫', '🚀': '火箭' }

// 口令长度门槛：`backend/schemas/auth.py:13` 是 PASSWORD_MIN = 6，
// `AuthPanel.vue:14` 早已本地写死 6。这里是第三处副本——项目没有跨端共享常量层，
// 改后端下限必须三处一起改，漏一处的表征是"注册能过、改密码被本地拦"或反过来。数值不许自创。
const PASSWORD_MIN = 6

// 回填只发生在 setup 这一次：弹窗每次都是 v-if 新挂载的（见 App.vue），
// 所以"打开时看到的就是当前值"由挂载时机保证，不需要 watch user。
const profile = reactive({ nickname: user.value?.nickname ?? '', avatar: user.value?.avatar ?? 'auto' })
const password = reactive({ oldPassword: '', newPassword: '' })
// baseUrl 回填（它是可明文显示的），apiKey **永远不回填**：库里那串不该回到输入框里。
const llm = reactive({ apiKey: '', baseUrl: user.value?.llm_base_url ?? '' })
const modelDraft = ref('')

// 四段各一个错误位：改密码失败不该把模型名单也标红。全局那条 error 属于聊天链路
// （useChat 持有、挂在聊天框上方），借它会把设置错误显示到一个已经滚动看不见的地方。
const profileError = ref('')
const passwordError = ref('')
const llmError = ref('')
const modelsError = ref('')
// 同时只让一个动作在飞：四个保存按钮共用它。连点两次「添加模型」会让后端先 409 再成功，
// 名单顺序取决于两个请求谁先落地——那是最难复现的一种乱。
const busy = ref('')

async function run(kind, action, onOk) {
  busy.value = kind
  try {
    onOk(await action())
    if (kind === 'password') {
      // 成功之后清空表单：204 没有回执，不清的话两个明文密码就留在 DOM 里等下一个人
      password.oldPassword = ''
      password.newPassword = ''
    }
  } catch (err) {
    setKindError(kind, err.message)
  } finally {
    busy.value = ''
  }
}

function setKindError(kind, text) {
  if (kind === 'profile') profileError.value = text
  else if (kind === 'password') passwordError.value = text
  else if (kind === 'llm') llmError.value = text
  else modelsError.value = text
}

function saveProfile() {
  if (!profile.nickname.trim()) {
    // 本地先拦一句：后端会回 422（min_length=1 + strip 后拦空白），但那句在弹窗里
    // 读起来像"我没打上字"。发出去一次再懂，代价比这句话大。
    profileError.value = '昵称不能是空白'
    return
  }
  // 值原样送出，trim 只在本地判空时用：清洗是 api/auth.py 的事，前端抢先改会分叉
  return run('profile', () => updateProfile({ nickname: profile.nickname, avatar: profile.avatar }),
             (res) => patchMe(res.user))
}

function savePassword() {
  if (password.newPassword.length < PASSWORD_MIN) {
    passwordError.value = `新密码至少 ${PASSWORD_MIN} 位`   // 与后端 6 同源，不许自创
    return
  }
  if (password.oldPassword === password.newPassword) {
    passwordError.value = '新密码不能和原密码相同'
    return
  }
  return run('password', () => updatePassword({ ...password }), () => { passwordError.value = '' })
}

function saveLlm() {
  if (!llm.apiKey.trim() || !llm.baseUrl.trim()) {
    llmError.value = 'api_key 与路由都要填，只填一半后端会拒'
    return
  }
  return run('llm', () => updateLlmConfig({ apiKey: llm.apiKey, baseUrl: llm.baseUrl }), (res) => {
    llm.apiKey = ''        // 提交成功立刻从组件状态里抹掉（错误路径故意不清：让用户改完直接重试）
    patchMe(res.user)
  })
}

function applyModels(out) {
  // 三个模型端点回的是 ModelsOut（只有名单与默认），不是整行 user：就地合并这两个键，
  // 别的键（api_key_masked 那些"只有后端知道"的值）保持上一次回执。
  patchMe({ ...user.value, models: out.models, default_model: out.default_model })
}

function submitModel() {
  const name = modelDraft.value.trim()
  if (!name) {
    modelsError.value = '模型名不能是空白'
    return
  }
  return run('model-add', () => addModel(name), (out) => {
    modelDraft.value = ''
    applyModels(out)
  })
}

function dropModel(name) {
  return run(`model-drop:${name}`, () => removeModel(name), applyModels)
}

function makeDefault(name) {
  return run(`model-default:${name}`, () => setDefaultModel(name), applyModels)
}

function onKeydown(event) {
  if (event.key === 'Escape') emit('close')
}

function onBackdrop(event) {
  // target===currentTarget 才关：从内容区冒泡上来的点击不是"点空白"（ChunkPickerModal 同规矩）
  if (event.target === event.currentTarget) emit('close')
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <div class="picker-backdrop settings-backdrop" @click="onBackdrop">
    <div class="picker-modal settings-panel" role="dialog" aria-modal="true" aria-label="账号设置">
      <header class="picker-header">
        <h3 class="picker-title">⚙ 账号设置</h3>
        <button class="picker-close" type="button" aria-label="关闭" title="关闭" @click="emit('close')">✕</button>
      </header>

      <div class="settings-body">
        <section class="settings-section">
          <h4 class="settings-heading">昵称与头像</h4>
          <input class="settings-input settings-nickname-input" type="text" maxlength="50"
                 aria-label="昵称" v-model="profile.nickname" />
          <div class="settings-avatars">
            <button v-for="item in AVATARS" :key="item" type="button" class="settings-avatar"
                    :class="{ 'settings-avatar-active': profile.avatar === item }"
                    :aria-label="AVATAR_LABELS[item]" :title="AVATAR_LABELS[item]"
                    @click="profile.avatar = item">{{ item === 'auto' ? 'A' : item }}</button>
          </div>
          <p v-if="profileError" class="settings-error settings-profile-error">⚠️ {{ profileError }}</p>
          <button class="btn btn-small settings-profile-save" type="button"
                  :disabled="busy !== ''" @click="saveProfile">保存资料</button>
        </section>

        <section class="settings-section">
          <h4 class="settings-heading">修改密码</h4>
          <input class="settings-input" type="password" aria-label="原密码"
                 autocomplete="current-password" v-model="password.oldPassword" />
          <input class="settings-input" type="password" aria-label="新密码"
                 autocomplete="new-password" v-model="password.newPassword" />
          <p class="settings-hint">新密码至少 {{ PASSWORD_MIN }} 位。改密码不会让其它设备掉线（已知遗留，spec 7.4）。</p>
          <p v-if="passwordError" class="settings-error settings-password-error">⚠️ {{ passwordError }}</p>
          <button class="btn btn-small settings-password-save" type="button"
                  :disabled="busy !== ''" @click="savePassword">修改密码</button>
        </section>

        <section class="settings-section">
          <h4 class="settings-heading">大模型凭证</h4>
          <p class="settings-masked">当前密钥：<code>{{ user?.api_key_masked || '未配置' }}</code></p>
          <input class="settings-input settings-apikey-input" type="password" aria-label="api_key"
                 autocomplete="off" placeholder="sk-…" v-model="llm.apiKey" />
          <input class="settings-input settings-baseurl-input" type="text" aria-label="base_url"
                 placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1" v-model="llm.baseUrl" />
          <p v-if="llmError" class="settings-error settings-llm-error">⚠️ {{ llmError }}</p>
          <button class="btn btn-small settings-llm-save" type="button"
                  :disabled="busy !== ''" @click="saveLlm">保存凭证</button>
        </section>

        <section class="settings-section">
          <h4 class="settings-heading">模型名单</h4>
          <ul v-if="user?.models?.length" class="settings-models">
            <li v-for="name in user.models" :key="name" class="settings-model-row">
              <span class="settings-model-name">{{ name }}</span>
              <span v-if="name === user.default_model" class="settings-default">默认</span>
              <button class="btn btn-ghost btn-small settings-model-default" type="button"
                      :disabled="busy !== '' || name === user.default_model"
                      @click="makeDefault(name)">设为默认</button>
              <button class="btn btn-ghost btn-small settings-model-drop" type="button"
                      :disabled="busy !== ''" @click="dropModel(name)">删除</button>
            </li>
          </ul>
          <p v-else class="settings-hint">名单是空的——没有模型可选，问答会直接返回 409。</p>
          <form class="settings-add-model" @submit.prevent="submitModel">
            <input class="settings-input settings-model-input" type="text" maxlength="100"
                   aria-label="新模型名" placeholder="例如 qwen-max" v-model="modelDraft" />
            <button class="btn btn-small settings-model-add" type="submit"
                    :disabled="busy !== ''">添加</button>
          </form>
          <p v-if="modelsError" class="settings-error settings-models-error">⚠️ {{ modelsError }}</p>
        </section>
      </div>
    </div>
  </div>
</template>
