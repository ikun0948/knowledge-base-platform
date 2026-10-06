<script setup>
import { computed } from 'vue'

// 模式标签只看"选了几个文档块"，不看后端回传：选了块即 RAG（spec 6.2 parent_ids 为空即普通对话）
const props = defineProps({
  selectedCount: { type: Number, required: true },
  sessionId: { type: String, required: true },
})

const shortSession = computed(() => props.sessionId.slice(0, 8))
</script>

<template>
  <div class="status-bar">
    <span v-if="props.selectedCount > 0" class="status-indicator status-rag">
      🔍 知识库模式（{{ props.selectedCount }} 个文档块）
    </span>
    <span v-else class="status-indicator status-normal">💬 普通对话模式</span>
    <span class="session-chip" :title="props.sessionId">session {{ shortSession }}</span>
  </div>
</template>
