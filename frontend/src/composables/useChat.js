import { ref } from 'vue'

import { sendChatStream } from '../api/chat.js'
import { clearHistory, getHistory } from '../api/history.js'

let seq = 0

// v-for 的 key 只求稳定唯一，自增比 randomUUID 省事，刷新后按历史重建也不会撞
function nextKey() {
  seq += 1
  return `m${seq}`
}

export function useChat() {
  const messages = ref([])
  const pending = ref(false)
  const error = ref('')
  let controller = null

  // 主动打断（换会话 / 清空）：后端收到断连会掐掉生成器、不写半截历史，
  // 所以本地这两条也必须跟着撤——"前端只留后端有的"原则不变。
  function abortStream() {
    if (controller) {
      controller.abort()
      controller = null
    }
  }

  // 按 key 撤而不是按下标撤：竞态下 restore/clear 可能已整体替换 messages.value，
  // 此时按下标 splice(len-2, 2) 会误删刚恢复回来的历史末两条；找不到 key 即无操作。
  function removeTurn(bubble) {
    const i = messages.value.findIndex((m) => m.key === bubble.key)
    if (i !== -1) messages.value.splice(Math.max(i - 1, 0), 2)
  }

  async function restore(sessionId) {
    abortStream()
    try {
      // 后端已把一行 DB 展开成 user + assistant 两条，形状与实时发送一致（spec 6.2 第 3 条）。
      // mode 由后端从 chat_history.document_ids 派生（Task 3），user 行为 null——MessageBubble 的 v-if 不渲染标签
      const rows = await getHistory(sessionId)
      messages.value = rows.map((row) => ({
        key: nextKey(),
        role: row.role,
        content: row.content,
        references: row.references ?? [],
        mode: row.mode ?? null,
        streaming: false,
      }))
      error.value = ''
      return true
    } catch (err) {
      error.value = err.message
      return false
    }
  }

  async function send({ session_id, question, document_ids }) {
    if (pending.value || !question.trim()) return false
    error.value = ''
    // 阶段二 pending 覆盖整条流：没有停止生成按钮时，中途放手会让界面挂着一条
    // 后端没有的半截答案，禁用输入到关流是唯一能守住"界面==历史"的做法。
    pending.value = true

    messages.value.push({ key: nextKey(), role: 'user', content: question, references: [], mode: null, streaming: false })
    messages.value.push({ key: nextKey(), role: 'assistant', content: '', references: [], mode: null, streaming: true })
    // 必须 push 完再按下标取回：拿到的是响应式代理，改它的字段才推动视图；
    // 改 push 之前那个原始对象，数据变了但界面不动。
    const bubble = messages.value[messages.value.length - 1]

    controller = new AbortController()
    const signal = controller.signal
    let fail = ''
    try {
      await sendChatStream(
        { session_id, question, document_ids },
        (event, data) => {
          switch (event) {
            case 'meta':
              // 模式标签先于答案上屏（spec 6.4：meta 立即先发）
              bubble.mode = data.mode
              break
            case 'references':
              // references 帧恒在第一个 token 之前，后端数组直接上屏
              bubble.references = data
              break
            case 'token':
              bubble.content += data.text
              break
            case 'error':
              // error 帧后流正常关闭，postStream 不 throw；失败在这里记账，走循环后分支
              fail = data.detail
              break
            case 'done':
              break
          }
        },
        { signal },
      )
      if (fail) {
        // meta 后失败：后端没写历史（异常在 save 前抛出），本地两条一起撤 + 横幅
        removeTurn(bubble)
        error.value = fail
        return false
      }
      return true
    } catch (err) {
      if (err?.name === 'AbortError') {
        // 自己按的打断：不弹横幅（真相是用户自己取消了，弹错反而让人去查服务器），
        // 但半截那两条必须撤——后端断流即丢，从没写历史。
        removeTurn(bubble)
        return false
      }
      removeTurn(bubble)
      error.value = err.message
      return false
    } finally {
      bubble.streaming = false
      if (controller?.signal === signal) controller = null
      pending.value = false
    }
  }

  async function clear(sessionId) {
    abortStream()
    try {
      // 先确认后端删掉了再动本地：本地清空而后端没删，刷新会把历史原样冲回来
      await clearHistory(sessionId)
      messages.value = []
      error.value = ''
      return true
    } catch (err) {
      error.value = err.message
      return false
    }
  }

  return { messages, pending, error, restore, send, clear, abortStream }
}
