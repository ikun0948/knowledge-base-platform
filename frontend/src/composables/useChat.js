import { ref } from 'vue'

import { sendChat } from '../api/chat.js'
import { clearHistory, getHistory } from '../api/history.js'
import { startTypewriter } from '../utils/typewriter.js'

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
  let typer = null
  let typingBubble = null

  function finishTyping() {
    if (typer) {
      typer.stop()
      typer = null
    }
    if (typingBubble) {
      // 直接补全成整段：中途开新一轮时宁可"字一下全出来"，也不留一条永远残缺的答案
      typingBubble.content = typingBubble.fullText
      typingBubble.streaming = false
      typingBubble = null
    }
  }

  async function restore(sessionId) {
    finishTyping()
    try {
      // 后端已把一行 DB 展开成 user + assistant 两条，形状与实时发送一致（spec 6.2 第 3 条），
      // 所以这里不需要区分"来自历史"和"来自本次会话"
      const rows = await getHistory(sessionId)
      messages.value = rows.map((row) => ({
        key: nextKey(),
        role: row.role,
        content: row.content,
        references: row.references ?? [],
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
    finishTyping()
    pending.value = true

    messages.value.push({ key: nextKey(), role: 'user', content: question, references: [], streaming: false })
    messages.value.push({ key: nextKey(), role: 'assistant', content: '', references: [], streaming: true, fullText: '' })
    // 必须 push 完再按下标取回：拿到的是响应式代理，改它的字段才推动视图；
    // 改 push 之前那个原始对象，数据变了但界面不动。
    const bubble = messages.value[messages.value.length - 1]

    try {
      const resp = await sendChat({ session_id, question, document_ids })
      bubble.mode = resp.mode
      bubble.references = resp.references ?? []
      bubble.fullText = resp.answer
      typer = startTypewriter(resp.answer, {
        onUpdate: (partial) => {
          bubble.content = partial
        },
        onDone: () => {
          bubble.streaming = false
          typer = null
          typingBubble = null
        },
      })
      typingBubble = bubble
      return true
    } catch (err) {
      // 后端 502 时不写历史（spec 七节"新增"那条）。本地这两条也必须一起撤掉：
      // 界面消息比后端历史多，刷新就会"消息蒸发"，比报错更难查。
      messages.value.splice(messages.value.length - 2, 2)
      error.value = err.message
      return false
    } finally {
      pending.value = false
    }
  }

  async function clear(sessionId) {
    try {
      // 先确认后端删掉了再动本地：本地清空而后端没删，刷新会把历史原样冲回来
      await clearHistory(sessionId)
      finishTyping()
      messages.value = []
      error.value = ''
      return true
    } catch (err) {
      error.value = err.message
      return false
    }
  }

  return { messages, pending, error, restore, send, clear, finishTyping }
}
