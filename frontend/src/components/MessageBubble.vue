<script setup>
import ReferenceList from './ReferenceList.vue'

const props = defineProps({
  message: { type: Object, required: true },
})
</script>

<template>
  <div class="message" :class="{ user: props.message.role === 'user' }">
    <div
      class="message-avatar"
      :class="props.message.role === 'user' ? 'user-avatar' : 'assistant-avatar'"
    >
      {{ props.message.role === 'user' ? '👤' : '🤖' }}
    </div>
    <div
      class="message-content"
      :class="props.message.role === 'user' ? 'user-message' : 'assistant-message'"
    >
      <span
        class="bubble-text pre-wrap"
        :class="{ 'streaming-cursor': props.message.streaming }"
        >{{ props.message.content }}</span>
      <p v-if="props.message.mode" class="bubble-meta">
        {{ props.message.mode === 'rag' ? '📚 知识库检索' : '💬 自由对话' }}
      </p>
      <ReferenceList v-if="props.message.references?.length" :references="props.message.references" />
    </div>
  </div>
</template>
