<script setup>
import { docLabel } from '../composables/useDocuments.js'

const props = defineProps({
  doc: { type: Object, required: true },
  checked: { type: Boolean, required: true },
})
const emit = defineEmits(['toggle'])

function formatTime(iso) {
  // 后端 datetime 不带时区，new Date 按本地时区解析——联调就在本机，够用
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  const pad = (n) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}
</script>

<template>
  <label class="doc-card" :class="{ 'doc-card-checked': props.checked }">
    <input type="checkbox" :checked="props.checked" @change="emit('toggle', props.doc.id)" />
    <span class="doc-name">📄 {{ docLabel(props.doc) }}</span>
    <span class="doc-meta">🕒 {{ formatTime(props.doc.created_at) }}</span>
    <span class="doc-meta">📊 {{ props.doc.chunk_count }} 个文档块</span>
  </label>
</template>
