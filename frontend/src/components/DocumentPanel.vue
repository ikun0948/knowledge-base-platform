<script setup>
import ChunkCard from './ChunkCard.vue'
import FileUploader from './FileUploader.vue'

const props = defineProps({
  selectedChunks: { type: Array, required: true },
  selectionError: { type: String, default: '' },
  queue: { type: Array, required: true },
  listError: { type: String, default: '' },
  docCount: { type: Number, required: true },
  clearing: { type: Boolean, default: false },
})
// deselect-chunk 是"取消选择"（本地动作，不发请求）；
// App.vue 里 MessageList 那条 remove-chunk 才是"删数据"（不可逆，要过 confirm）——两个名字不能混。
const emit = defineEmits(['enqueue', 'retry', 'dismiss', 'clear', 'open-picker', 'deselect-chunk'])
</script>

<template>
  <div class="side-panel-inner">
    <h2 class="panel-title">📁 文档管理</h2>
    <FileUploader
      :queue="props.queue"
      @enqueue="emit('enqueue', $event)"
      @retry="emit('retry', $event)"
      @dismiss="emit('dismiss', $event)"
    />

    <p v-if="props.listError" class="queue-error">📚 文档列表加载失败：{{ props.listError }}</p>

    <hr class="panel-hr" />
    <h2 class="panel-title">🧩 已选文档块</h2>
    <button class="btn btn-small picker-open" type="button" @click="emit('open-picker')">
      ➕ 选择文档块
    </button>
    <p v-if="props.selectionError" class="queue-error">⚠️ {{ props.selectionError }}</p>

    <ul v-if="props.selectedChunks.length" class="chunk-list">
      <li v-for="chunk in props.selectedChunks" :key="chunk.parent_id">
        <ChunkCard
          :chunk="chunk"
          selected
          removable
          @toggle="emit('deselect-chunk', chunk.parent_id)"
          @remove="emit('deselect-chunk', $event)"
        />
      </li>
    </ul>
    <p v-else class="panel-hint">还没有选择文档块，点上方按钮挑几块。</p>
    <p class="panel-hint">一个块都不选就是普通对话。点卡片右上角的 ✕ 取消选择（不删任何数据）。</p>

    <hr class="panel-hr" />
    <div class="metric">📊 文档数 {{ props.docCount }}</div>
    <button class="btn" type="button" :disabled="props.clearing" @click="emit('clear')">
      {{ props.clearing ? '清空中…' : '🗑️ 清空对话' }}
    </button>
  </div>
</template>
