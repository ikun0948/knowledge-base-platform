<script setup>
import { computed, nextTick, ref, watch } from 'vue'

import MessageBubble from './MessageBubble.vue'

const props = defineProps({
  messages: { type: Array, required: true },
  hasDocuments: { type: Boolean, required: true },
})
// 第二跳转发：ReferenceList → MessageBubble → 这里 → App.vue（动作要碰 API 与文档列表，只有 App 够得着）
const emit = defineEmits(['remove-chunk'])

const listEl = ref(null)

// 用数组 join 而不是模板里的多行文本：Vue 模板默认 condense 空白，
// 写在模板里的换行会被压成一行。
const welcomeText = computed(() =>
  [
    '👋 你好！我是你的 AI 智能助手。',
    '',
    '💡 我能做什么：',
    '• 📚 基于你上传的文档回答问题',
    '• 💬 进行日常对话交流',
    '• 🔍 提供准确的信息检索',
    '',
    props.hasDocuments ? '从左侧「➕ 选择文档块」挑几块，或直接开始对话吧！' : '请先在左侧上传文档，或直接开始对话吧！',
  ].join('\n'),
)

// 阶段二流式：token 逐帧追加会让最后一条 content 持续变长，所以 watch 的是"长度"而不只是条数，
// 否则气泡会长出视口外而页面不跟到底部。
watch(
  () => [props.messages.length, props.messages.at(-1)?.content.length ?? 0],
  async () => {
    await nextTick()
    const el = listEl.value
    if (el) el.scrollTop = el.scrollHeight
  },
)
</script>

<template>
  <section ref="listEl" class="chat-messages">
    <div v-if="!props.messages.length" class="message">
      <div class="message-avatar assistant-avatar">🤖</div>
      <div class="message-content assistant-message">
        <span class="bubble-text pre-wrap">{{ welcomeText }}</span>
      </div>
    </div>

    <MessageBubble
      v-for="message in props.messages"
      :key="message.key"
      :message="message"
      @remove-chunk="emit('remove-chunk', $event)"
    />
  </section>
</template>
