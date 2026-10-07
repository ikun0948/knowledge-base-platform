<script setup>
import { computed, onMounted, ref } from 'vue'

import AuthPanel from './components/AuthPanel.vue'
import ChatHeader from './components/ChatHeader.vue'
import ChatInput from './components/ChatInput.vue'
import ChunkPickerModal from './components/ChunkPickerModal.vue'
import DocumentPanel from './components/DocumentPanel.vue'
import MessageList from './components/MessageList.vue'
import StatusBar from './components/StatusBar.vue'
import { useAuth } from './composables/useAuth.js'
import { useChat } from './composables/useChat.js'
import { useChunkSelection } from './composables/useChunkSelection.js'
import { useDocuments } from './composables/useDocuments.js'
import { useSession } from './composables/useSession.js'

// 五个 composable 在 App.vue 里显式接线，不引 Pinia/Vuex（spec 五节）
const { sessionId, setSession, resetSession, clearSession } = useSession()
const { user, authError, isLoggedIn, bootstrap, signUp, signIn, signOut } = useAuth()
const {
  documents, queue, listError, docCount,
  refresh, enqueue, retry, dismiss,
} = useDocuments()
const {
  selectedChunks, selectedParentIds, selectedCount, pickerOpen, selectionError,
  hydrate, toggle, remove, clearSelection,
} = useChunkSelection()
const { messages, pending, error, restore, send, clear, abortStream, markChunkDeleted } = useChat()

const question = ref('')
const clearing = ref(false)
// 宽屏侧栏常驻，panelOpen 只在 ≤768px 起作用
const panelOpen = ref(false)

// 改造前 onMounted 的三拍原样搬进这个函数：顺序是既有不变式，不许重排。
// hydrate 要打一枪 /api/documents/chunks：放在 restore 之前，
// 让"选中项已被剪掉"这件事先于历史渲染，错误横幅只剩最后一条真的。
async function enterWorkspace() {
  await refresh()
  await hydrate()
  await restore(sessionId.value)
}

onMounted(async () => {
  // 启动第一拍（spec 5.2）：手上没令牌就一个请求都不发，
  // 否则未登录的人一进站就撞一串 401 横幅。
  if (await bootstrap()) await enterWorkspace()
})

// 登录/注册成功后的两拍在这里，而不是 AuthPanel 里：
// AuthPanel 自己调 API 的话，isLoggedIn 一变 v-if 就要卸载它，
// emit 与后续动作的先后只能靠调度器 flush 时机解释——顺序代码放这儿最直白。
async function handleAuth({ mode, payload }) {
  authError.value = ''
  let sid
  try {
    // signUp/signIn 会抛（useAuth 内部只有 try/finally），文案统一落在 authError 上给 AuthPanel 显示
    sid = mode === 'register' ? await signUp(payload) : await signIn(payload)
  } catch (err) {
    authError.value = err.message
    return
  }
  setSession(sid)   // 后端铸造的对话 id 覆盖本地（spec 5.3）：重新登录就是新对话
  await enterWorkspace()
}

async function handleSignOut() {
  // 先掐掉在飞的流：不掐的话这条流会在登出之后把答案写进已经换人的界面，
  // 而 useChat 的 done 记账会让它名正言顺地留在屏上
  abortStream()
  await signOut()      // 后端失败已在 useAuth 里被 catch 吞掉，所以这里一定走到下面的清理
  clearSession()       // auth_token 与 session_id 一起清（spec 5.3）
  // 界面此刻换成登录页，但 App 实例还在、这些 ref 也还在：不清的话下一个人登录后
  // 会在 enterWorkspace 覆盖之前瞥见上一个账号的文件名。documents/queue/messages 都是
  // composable 返回的 ref，直接赋空数组就行；选中项必须走 clearSelection（它同时回写 localStorage）。
  documents.value = []
  queue.value = []
  messages.value = []
  clearSelection()
  error.value = ''
  pickerOpen.value = false
}

// 头像：`users.avatar` 这一期恒为 'auto'（预设表情的选择器随 SettingsModal 在阶段二接入），
// 所以这里只做昵称首字母；昵称为空才退回账号标识，再空才是 '我'。
const avatarChar = computed(() => {
  const name = (user.value?.nickname || user.value?.identifier || '').trim()
  return name ? name.charAt(0).toUpperCase() : '我'
})

async function handleClear() {
  // 没有 UI 库可借，destructive 操作用原生 confirm：误点一次就再也找不回来
  if (!window.confirm('确认清空当前会话的全部消息？会删除后端保存的历史，不可恢复。')) return
  clearing.value = true
  const ok = await clear(sessionId.value)
  if (ok) {
    // 与 app.py 的行为等价：清空后换一个新的 session_id（旧 id 已被 DELETE 清空）。
    // 需求 3 删掉了「换一个 session_id」那个调试按钮，但换 id 这个动作不能跟着删（spec 5.4）。
    resetSession()
    question.value = ''
    // 原先这一步靠 watch(sessionId) 重拉历史。那个 watch 整条删了（下面注释说明原因），
    // 所以这里显式补一次：界面==历史这条不变式不许等到下次刷新才成立。
    await restore(sessionId.value)
  }
  clearing.value = false
}

// 删块的请求由弹窗自己发（deleteChunk 在那边），这里只收"已经删掉了"这个事实：
// 先标界面再刷列表——引用条目是"那一轮用过什么"的凭据，不能因为刷列表而消失。
function handleChunkDeleted(chunk) {
  markChunkDeleted(chunk.document_id, chunk.parent_id)
  // parent_id 全库唯一，所以按它摘正好：这块的死是此刻确定的事实，
  // 留在允许池里等于面板挂一张空卡片、下次问答带一个必空召回的 id
  remove(chunk.parent_id)
  refresh()
}

// M-F3：直接用 ChatInput emit 的载荷（已是 trim 后的文本），不再回头重读 question——
// 载荷与 modelValue 当前等值，接线后数据流单向：输入框把"要发的话"交给 App。
async function handleSend(text) {
  if (!text || pending.value) return
  question.value = ''
  const ok = await send({ session_id: sessionId.value, question: text, parent_ids: selectedParentIds.value })
  // 后端失败时不写历史，本地那两条也已经撤掉；把问题还给输入框，别让用户重打
  if (!ok) question.value = text
}

// 停止不能只信本地撤泡：后端在 done 帧前一刻已落库的窗口里，界面==历史只有重拉才能成立。
// 已知窄口：GET 早于后端最终落库返回时本轮看不到那条答案，刷新一次自愈（记档于阶段三）。
async function handleStop() {
  abortStream()
  await restore(sessionId.value)
}

function dismissError() {
  error.value = ''
}
</script>

<template>
  <!-- 需求 5 的门禁：未登录整屏只有登录页。DocumentPanel、上传按钮、聊天输入
       统统不渲染——比"渲染出来但禁用"更难漏（spec 5.1） -->
  <main v-if="!isLoggedIn" class="auth-screen">
    <AuthPanel @submit="handleAuth" />
  </main>

  <div v-else class="app-shell" :class="{ 'panel-open': panelOpen }">
    <!-- DOM 首位是 panel-toggle（L-1 根治）：≤768 单栏 grid 按文档顺序排轨，
         按钮排第 1 行 auto 才保证长历史下不滚动就在首屏；桌面它 display:none 不占轨，两栏照旧 -->
    <button class="btn btn-ghost btn-small panel-toggle" type="button" @click="panelOpen = !panelOpen">
      {{ panelOpen ? '收起文档面板' : '展开文档面板' }}
    </button>

    <aside class="side-panel">
      <DocumentPanel
        :selected-chunks="selectedChunks"
        :selection-error="selectionError"
        :queue="queue"
        :list-error="listError"
        :doc-count="docCount"
        :clearing="clearing"
        @enqueue="enqueue"
        @retry="retry"
        @dismiss="dismiss"
        @open-picker="pickerOpen = true"
        @deselect-chunk="remove"
        @clear="handleClear"
      />
      <div class="side-panel-inner">
        <!-- 需求 3：原先这里的「session_id 调试区」整块删除（那行的 <code> 展示与
             「换一个 session_id」按钮一起走），原位置换成 `.user-rail`——sessionId 在界面上
             只剩读的地方，没有显示的地方；换 id 的动作留在 handleClear 里。
             ⚙ 这一期是 disabled 的占位：设置弹窗（改昵称/密码/api_key）在阶段二，
             现在点出一个空白弹窗比点不动更糟。title 说明"什么时候有"。 -->
        <hr class="panel-hr" />
        <div class="user-rail">
          <span class="rail-avatar" aria-hidden="true">{{ avatarChar }}</span>
          <span class="rail-name" :title="user?.identifier">{{ user?.nickname }}</span>
          <button
            class="btn btn-ghost btn-small rail-settings"
            type="button"
            disabled
            title="设置项将在下一阶段开放"
            aria-label="打开设置"
          >⚙</button>
          <button class="btn btn-ghost btn-small rail-signout" type="button" @click="handleSignOut">退出登录</button>
        </div>
      </div>
    </aside>

    <main class="chat-main">
      <div class="chat-container">
        <ChatHeader />
        <div class="chat-body">
          <!-- StatusBar 不再收 :session-id（prop 已删，见 Step 4） -->
          <StatusBar :selected-count="selectedCount" />
          <p v-if="error" class="error-banner">
            <span>⚠️ {{ error }}</span>
            <button class="btn btn-ghost btn-small" type="button" @click="dismissError">关闭</button>
          </p>
          <MessageList
            :messages="messages"
            :has-documents="documents.length > 0"
          />
          <ChatInput v-model="question" :pending="pending" @send="handleSend" @stop="handleStop" />
          <ChunkPickerModal
            v-if="pickerOpen"
            :selected-ids="selectedParentIds"
            :error="selectionError"
            @toggle="toggle"
            @chunk-deleted="handleChunkDeleted"
            @close="pickerOpen = false"
          />
        </div>
      </div>
    </main>
  </div>
</template>
