<script setup>
import { onMounted, ref } from 'vue'

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
const { messages, pending, error, restore, send } = useChat()

const question = ref('')
// 宽屏侧栏常驻，panelOpen 只在 ≤768px 起作用
const panelOpen = ref(false)

onMounted(async () => {
  await refresh()
  await restore(sessionId.value)
})

async function handleSend() {
  const text = question.value.trim()
  if (!text || pending.value) return
  question.value = ''
  const ok = await send({ session_id: sessionId.value, question: text, document_ids: selectedIds.value })
  // 后端失败时不写历史，本地那两条也已经撤掉；把问题还给输入框，别让用户重打
  if (!ok) question.value = text
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
        @enqueue="enqueue"
        @retry="retry"
        @dismiss="dismiss"
        @toggle="toggleSelect"
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
          <ChatInput v-model="question" :pending="pending" @send="handleSend" />
        </div>
      </div>
    </main>

    <button class="btn btn-ghost btn-small panel-toggle" type="button" @click="panelOpen = !panelOpen">
      {{ panelOpen ? '收起文档面板' : '展开文档面板' }}
    </button>
  </div>
</template>
