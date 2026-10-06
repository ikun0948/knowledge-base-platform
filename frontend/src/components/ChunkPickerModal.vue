<script setup>
import { onMounted, onUnmounted, ref } from 'vue'

import ChunkCard from './ChunkCard.vue'
import { deleteChunk, listChunks } from '../api/documents.js'

const props = defineProps({
  selectedIds: { type: Array, required: true },
  error: { type: String, default: '' },
})
const emit = defineEmits(['toggle', 'close', 'chunk-deleted'])

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
// 搜索失败与删除失败共用一处错误位：错在哪一行就说在哪，但都顶在弹窗里而不是全局横幅
const localError = ref('')
// 删块期间记住是谁：既是按钮的禁用依据，也挡住连点——第二次 DELETE 只能拿 404，
// 然后界面显示"删除失败"，其实数据早就没了。
const deletingId = ref('')

// 只有回车与按钮提交，不做输入防抖：搜索框每敲一个字打一次后端，
// 在这个体量（父块十来个）上是纯浪费，真要加防抖得先有分页。
async function search() {
  busy.value = true
  localError.value = ''
  try {
    chunks.value = await listChunks({ query: keyword.value.trim(), suffix: suffix.value })
  } catch (err) {
    chunks.value = []
    localError.value = err.message
  } finally {
    busy.value = false
  }
}

function pickSuffix(value) {
  suffix.value = value
  search()
}

// 2026-10-06：删除入口从消息引用条搬到这里，删数据只剩这一个入口。
async function removeChunk(chunk) {
  if (deletingId.value) return
  // 向量库删完就没了，原生 confirm 这道门禁跟着搬过来，而且必须先于任何请求
  const ok = window.confirm(
    `确认删除文档块「${chunk.parent_id}」？会连同它名下的子块一起从向量库移除，不可恢复。`,
  )
  if (!ok) return
  deletingId.value = chunk.parent_id
  try {
    await deleteChunk(chunk.document_id, chunk.parent_id)
    // 先剔行再通知：这块已经死了，留在结果里等于挂一张必然空召回的卡片
    chunks.value = chunks.value.filter((item) => item.parent_id !== chunk.parent_id)
    emit('chunk-deleted', chunk)
  } catch (err) {
    // 删失败不能减行：界面不能宣称删掉了其实没删
    localError.value = err.message
  } finally {
    deletingId.value = ''
  }
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

      <p v-if="props.error || localError" class="picker-error">⚠️ {{ props.error || localError }}</p>
      <p v-if="busy" class="picker-hint">搜索中…</p>
      <ul v-else-if="chunks.length" class="picker-results">
        <li v-for="item in chunks" :key="item.parent_id">
          <ChunkCard
            :chunk="item"
            :selected="props.selectedIds.includes(item.parent_id)"
            deletable
            :deleting="deletingId === item.parent_id"
            @toggle="emit('toggle', $event)"
            @delete="removeChunk($event)"
          />
        </li>
      </ul>
      <p v-else class="picker-hint">没有匹配的文档块，换个关键词或分类试试。</p>
    </div>
  </div>
</template>
