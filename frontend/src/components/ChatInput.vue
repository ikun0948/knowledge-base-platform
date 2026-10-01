<script setup>
const props = defineProps({
  modelValue: { type: String, required: true },
  pending: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'send'])

function onInput(event) {
  emit('update:modelValue', event.target.value)
}

function submit() {
  if (props.pending || !props.modelValue.trim()) return
  emit('send', props.modelValue.trim())
}

function onKeydown(event) {
  // 原 st.chat_input 就是回车发送；Shift+Enter 留给人工换行
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    submit()
  }
}
</script>

<template>
  <div class="chat-input">
    <textarea
      class="chat-textarea"
      rows="2"
      placeholder="💬 输入你的问题…"
      :value="props.modelValue"
      :disabled="props.pending"
      @input="onInput"
      @keydown="onKeydown"
    ></textarea>
    <button class="btn" type="button" :disabled="props.pending || !props.modelValue.trim()" @click="submit">
      {{ props.pending ? '🤔 思考中…' : '发送' }}
    </button>
  </div>
</template>
