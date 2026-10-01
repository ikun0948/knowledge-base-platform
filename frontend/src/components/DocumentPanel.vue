<script setup>
import DocCard from './DocCard.vue'
import FileUploader from './FileUploader.vue'

const props = defineProps({
  documents: { type: Array, required: true },
  selectedIds: { type: Array, required: true },
  queue: { type: Array, required: true },
  listError: { type: String, default: '' },
  docCount: { type: Number, required: true },
})
const emit = defineEmits(['enqueue', 'retry', 'dismiss', 'toggle'])
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
    <h2 class="panel-title">📚 知识库</h2>
    <p class="panel-hint">勾选后基于文档内容回答；一个都不勾就是普通对话。</p>

    <ul v-if="props.documents.length" class="doc-list">
      <li v-for="doc in props.documents" :key="doc.id">
        <DocCard
          :doc="doc"
          :checked="props.selectedIds.includes(doc.id)"
          @toggle="emit('toggle', $event)"
        />
      </li>
    </ul>
    <p v-else-if="!props.listError" class="panel-hint">暂无文档，请先上传</p>

    <div class="metric">📊 文档数 {{ props.docCount }}</div>
  </div>
</template>
