<script setup>
import { onMounted, onUnmounted, ref } from 'vue'

import ChunkCard from './ChunkCard.vue'
import { listChunks } from '../api/documents.js'

const props = defineProps({
  selectedIds: { type: Array, required: true },
  error: { type: String, default: '' },
})
const emit = defineEmits(['toggle', 'close'])

const TABS = [
  { value: '', label: '全部' },
  { value: 'pdf', label: 'PDF' },
  { value: 'docx', label: 'DOCX' },
  { value: 'txt', label: 'TXT' },
]

const keyword = ref('')
const suffix = ref('')
const chunks = ref([])
const busy = ref(false)
const searchError = ref('')

// 只有回车与按钮提交，不做输入防抖：搜索框每敲一个字打一次后端，
// 在这个体量（父块十来个）上是纯浪费，真要加防抖得先有分页。
async function search() {
  busy.value = true
  searchError.value = ''
  try {
    chunks.value = await listChunks({ query: keyword.value.trim(), suffix: suffix.value })
  } catch (err) {
    chunks.value = []
    searchError.value = err.message
  } finally {
    busy.value = false
  }
}

function pickSuffix(value) {
  suffix.value = value
  search()
}

function onKeydown(event) {
  if (event.key === 'Escape') emit('close')
}

function onBackdrop(event) {
  // target===currentTarget 才关：从内容区冒泡上来的点击不是"点空白"
  if (event.target === event.currentTarget) emit('close')
}

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
  search()
})
onUnmounted(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <div class="picker-backdrop" @click="onBackdrop">
    <div class="picker-modal" role="dialog" aria-modal="true" aria-label="选择文档块">
      <header class="picker-header">
        <h3 class="picker-title">🧩 选择文档块</h3>
        <button class="picker-close" type="button" aria-label="关闭" title="关闭" @click="emit('close')">✕</button>
      </header>

      <form class="picker-search" @submit.prevent="search">
        <input
          v-model="keyword"
          class="picker-input"
          type="search"
          aria-label="搜索文档块"
          placeholder="按文件名或块内文字搜索，回车提交"
        />
        <button class="btn btn-small" type="submit">搜索</button>
      </form>

      <div class="picker-tabs">
        <button
          v-for="tab in TABS"
          :key="tab.value"
          class="picker-tab"
          :class="{ 'picker-tab-active': suffix === tab.value }"
          type="button"
          @click="pickSuffix(tab.value)"
        >{{ tab.label }}</button>
      </div>

      <p v-if="props.error || searchError" class="picker-error">⚠️ {{ props.error || searchError }}</p>
      <p v-else-if="busy" class="picker-hint">搜索中…</p>
      <ul v-else-if="chunks.length" class="picker-results">
        <li v-for="item in chunks" :key="item.parent_id">
          <ChunkCard
            :chunk="item"
            :selected="props.selectedIds.includes(item.parent_id)"
            @toggle="emit('toggle', $event)"
          />
        </li>
      </ul>
      <p v-else class="picker-hint">没有匹配的文档块，换个关键词或分类试试。</p>
    </div>
  </div>
</template>
