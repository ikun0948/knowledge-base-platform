<script setup>
import { onMounted, ref, watch } from 'vue'

import ChatHeader from './components/ChatHeader.vue'
import ChatInput from './components/ChatInput.vue'
import ChunkPickerModal from './components/ChunkPickerModal.vue'
import DocumentPanel from './components/DocumentPanel.vue'
import MessageList from './components/MessageList.vue'
import StatusBar from './components/StatusBar.vue'
import { useChat } from './composables/useChat.js'
import { useChunkSelection } from './composables/useChunkSelection.js'
import { useDocuments } from './composables/useDocuments.js'
import { useSession } from './composables/useSession.js'

// 四个 composable 在 App.vue 里显式接线，不引 Pinia/Vuex（spec 五节）
const { sessionId, resetSession } = useSession()
const {
  documents, queue, listError, docCount,
  refresh, enqueue, retry, dismiss,
} = useDocuments()
const {
  selectedChunks, selectedParentIds, selectedCount, pickerOpen, selectionError,
  hydrate, toggle, remove,
} = useChunkSelection()
const { messages, pending, error, restore, send, clear, abortStream, markChunkDeleted } = useChat()

const question = ref('')
const clearing = ref(false)
// 宽屏侧栏常驻，panelOpen 只在 ≤768px 起作用
const panelOpen = ref(false)

onMounted(async () => {
  await refresh()
  // hydrate 要打一枪 /api/documents/chunks：放在 restore 之前，
  // 让"选中项已被剪掉"这件事先于历史渲染，错误横幅只剩最后一条真的
  await hydrate()
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
  <div class="app-shell" :class="{ 'panel-open': panelOpen }">
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
          <StatusBar :selected-count="selectedCount" :session-id="sessionId" />
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
