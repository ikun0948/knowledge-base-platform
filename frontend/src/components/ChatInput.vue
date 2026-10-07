<script setup>
const props = defineProps({
  modelValue: { type: String, required: true },
  pending: { type: Boolean, default: false },
  // 名单来自 user.models（Task 2 的 _user_out 给，Task 9 的 SettingsModal 改）。
  // 数组类 prop 的 default 必须是工厂函数：写死 [] 会让所有实例共享同一个引用。
  models: { type: Array, default: () => [] },
  selectedModel: { type: String, default: '' },
  // 阶段二 Task 11：账号没配好大模型时由 App 关掉发送。默认 true——
  // 除新增那条显式传 false 的判据外，既有测都不传它，行为照旧，这一格只由 App 的 setupProblem 驱动。
  allowSend: { type: Boolean, default: true },
})
// update:selectedModel 与 update:modelValue 是两条独立的双向口，别混：
// 前者改"这一轮用哪个模型"，后者改"要发什么话"。
const emit = defineEmits(['update:modelValue', 'update:selectedModel', 'send', 'stop'])

function onInput(event) {
  emit('update:modelValue', event.target.value)
}

function onModelChange(event) {
  // 交出去的是 option 的 value（模型名本身），不是下标：下标会随名单增删漂移。
  emit('update:selectedModel', event.target.value)
}

function submit() {
  if (props.pending || !props.allowSend || !props.modelValue.trim()) return
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
    <div class="chat-controls">
      <select
        class="model-select"
        aria-label="本轮使用的模型"
        :value="props.selectedModel"
        :disabled="props.pending || props.models.length === 0"
        @change="onModelChange"
      >
        <!-- 空名单也要有一个 option：否则 :value 指向一个不存在的 option，
             select 自己会显示成"空白"，看起来像控件坏了而不是"你没配模型" -->
        <option v-if="props.models.length === 0" value="">（名单为空，先去设置加一个）</option>
        <option v-for="name in props.models" :key="name" :value="name">{{ name }}</option>
      </select>
      <button v-if="props.pending" class="btn btn-stop chat-stop" type="button" @click="emit('stop')">⏹ 停止生成</button>
      <!-- 两道门与 submit() 逐字对应：!allowSend 是"账号还没配好"，!modelValue.trim() 是"没打字"。
           少一道就是漏一面：只改这里不改 submit()，Enter 照样能把话发出去。 -->
      <button v-else class="btn chat-send" type="button"
              :disabled="!props.allowSend || !props.modelValue.trim()" @click="submit">发送</button>
    </div>
  </div>
</template>
