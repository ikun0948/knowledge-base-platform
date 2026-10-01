<script setup>
import { ref } from 'vue'

const props = defineProps({
  queue: { type: Array, required: true },
})
const emit = defineEmits(['enqueue', 'retry', 'dismiss'])

// accept 的三种扩展名与后端 SUPPORTED_SUFFIXES 对齐（backend/core/document_processor.py:14）
const inputEl = ref(null)

function onPick(event) {
  const files = Array.from(event.target.files ?? [])
  if (files.length) emit('enqueue', files)
  // 不清空 value，连续两次选同一个文件不会触发 change，队列里就永远少一条
  event.target.value = ''
}

function stateText(item) {
  if (item.status === 'pending') return '排队中'
  if (item.status === 'uploading') return `上传中 ${item.percent}%`
  if (item.status === 'ok') return '✅ 成功'
  return '❌ 失败'
}
</script>

<template>
  <div class="uploader">
    <label class="btn btn-small uploader-label">
      📥 选择文档（可多选）
      <input
        ref="inputEl"
        class="file-input"
        type="file"
        multiple
        accept=".pdf,.docx,.txt"
        @change="onPick"
      />
    </label>
    <p class="panel-hint">支持 PDF、Word、txt；逐个上传，失败可单独重试。</p>

    <ul v-if="props.queue.length" class="queue">
      <li
        v-for="item in props.queue"
        :key="item.key"
        class="queue-item"
        :class="{ 'queue-ok': item.status === 'ok', 'queue-fail': item.status === 'fail' }"
      >
        <div class="queue-head">
          <span class="queue-name" :title="item.name">{{ item.name }}</span>
          <span class="queue-state">{{ stateText(item) }}</span>
          <button
            v-if="item.status === 'fail'"
            class="btn btn-ghost btn-small"
            type="button"
            @click="emit('retry', item)"
          >
            重试
          </button>
          <button
            v-if="item.status === 'ok' || item.status === 'fail'"
            class="btn btn-ghost btn-small"
            type="button"
            @click="emit('dismiss', item)"
          >
            移除
          </button>
        </div>
        <div v-if="item.status === 'uploading'" class="progress">
          <div class="progress-bar" :style="{ width: `${item.percent}%` }"></div>
        </div>
        <p v-if="item.error" class="queue-error">{{ item.error }}</p>
      </li>
    </ul>
  </div>
</template>
