<script setup>
import { onMounted, ref, watch } from 'vue'

import ChatHeader from './components/ChatHeader.vue'
import ChatInput from './components/ChatInput.vue'
import DocumentPanel from './components/DocumentPanel.vue'
import MessageList from './components/MessageList.vue'
import StatusBar from './components/StatusBar.vue'
import { useChat } from './composables/useChat.js'
import { useDocuments } from './composables/useDocuments.js'
import { useSession } from './composables/useSession.js'

// 三个 composable 在 App.vue 里显式接线，不引 Pinia/Vuex（spec 五节）
const { sessionId, resetSession } = useSession()
const {
  documents, selectedIds, queue, listError, docCount,
  refresh, toggleSelect, enqueue, retry, dismiss,
} = useDocuments()
const { messages, pending, error, restore, send, clear, abortStream } = useChat()

const question = ref('')
const clearing = ref(false)
// 宽屏侧栏常驻，panelOpen 只在 ≤768px 起作用
const panelOpen = ref(false)

onMounted(async () => {
  await refresh()
  await restore(sessionId.value)
})

// session_id 一变就重拉历史：调试按钮和"清空对话"都会改它，
// 不 watch 的话界面会继续挂着上一个 session 的消息，看起来像"换 id 没生效"。
watch(sessionId, (next) => restore(next))

async function handleClear() {
  // 没有 UI 库可借，destructive 操作用原生 confirm：误点一次就再也找不回来
  if (!window.confirm('确认清空当前会话的全部消息？会删除后端保存的历史，不可恢复。')) return
  clearing.value = true
  const ok = await clear(sessionId.value)
  if (ok) {
    // 与 app.py 的行为等价：清空后换一个新的 session_id（旧 id 已被 DELETE 清空）
    resetSession()
    question.value = ''
  }
  clearing.value = false
}

async function handleSend() {
  const text = question.value.trim()
  if (!text || pending.value) return
  question.value = ''
  const ok = await send({ session_id: sessionId.value, question: text, document_ids: selectedIds.value })
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
  <div class="app-shell" :class="{ 'panel-open': panelOpen }">
    <aside class="side-panel">
      <DocumentPanel
        :documents="documents"
        :selected-ids="selectedIds"
        :queue="queue"
        :list-error="listError"
        :doc-count="docCount"
        :clearing="clearing"
        @enqueue="enqueue"
        @retry="retry"
        @dismiss="dismiss"
        @toggle="toggleSelect"
        @clear="handleClear"
      />
      <div class="side-panel-inner">
        <hr class="panel-hr" />
        <div class="session-debug">
          <span>当前 session_id</span>
          <code class="session-value">{{ sessionId }}</code>
          <button class="btn btn-ghost btn-small" type="button" @click="resetSession">换一个 session_id</button>
        </div>
      </div>
    </aside>

    <main class="chat-main">
      <div class="chat-container">
        <ChatHeader />
        <div class="chat-body">
          <StatusBar :selected-count="selectedIds.length" :session-id="sessionId" />
          <p v-if="error" class="error-banner">
            <span>⚠️ {{ error }}</span>
            <button class="btn btn-ghost btn-small" type="button" @click="dismissError">关闭</button>
          </p>
          <MessageList :messages="messages" :has-documents="documents.length > 0" />
          <ChatInput v-model="question" :pending="pending" @send="handleSend" @stop="handleStop" />
        </div>
      </div>
    </main>

    <button class="btn btn-ghost btn-small panel-toggle" type="button" @click="panelOpen = !panelOpen">
      {{ panelOpen ? '收起文档面板' : '展开文档面板' }}
    </button>
  </div>
</template>
