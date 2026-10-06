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

  async function send({ session_id, question, parent_ids }) {
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
    // 后端只在历史落库之后才发 done，所以 done 是"这一轮真存在于 chat_history"的唯一凭据；
    // error 帧的 detail 也可能是空串，真值判断会把它当成成功 → 失败与收流都只用显式标记记账。
    let ended = false
    let errored = false
    let errorText = ''
    try {
      await sendChatStream(
        { session_id, question, parent_ids },
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
              errored = true
              errorText = String(data.detail ?? '')
              break
            case 'done':
              // 落库已完成的信号：只有收到它，本地这两条才有资格留在界面上
              ended = true
              break
          }
        },
        { signal },
      )
      if (errored) {
        // meta 后失败：后端没写历史（异常在 save 前抛出），本地两条一起撤 + 横幅
        removeTurn(bubble)
        error.value = errorText || '流式响应出错，请重试'
        return false
      }
      if (!ended) {
        // 干净 EOF 却没有 done 帧 = 这一轮没落库（反代吞流、生成器被提前回收都会这样）。
        // 留着气泡就是"刷新后消息凭空蒸发"的案发现场：撤两条 + 一句能行动的中文。
        removeTurn(bubble)
        error.value = '流式响应意外中断，请重试'
        return false
      }
      return true
    } catch (err) {
      if (signal.aborted) {
        // 调用方主动取消（AbortController 的 AbortError、AbortSignal.timeout 的 TimeoutError）：
        // 判据与 client.js 的 G-2 约定一致——看 signal 不认错误名，否则超时会被弹成一句英文红横幅。
        // 不弹横幅（真相是用户自己取消了，弹错反而让人去查服务器），
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

  function markChunkDeleted(documentId, parentId) {
    // 整屏扫而不是只改当前气泡：同一个块会被多轮答案引用，只灰一处看起来像"删了一半"。
    // 条目本身必须留着——它是"那一轮用过什么"的凭据，抹掉等于篡改已经落库的历史。
    for (const message of messages.value) {
      for (const reference of message.references) {
        if (reference.document_id === documentId && reference.parent_id === parentId) {
          reference.deleted = true
        }
      }
    }
  }

  return { messages, pending, error, restore, send, clear, abortStream, markChunkDeleted }
}
