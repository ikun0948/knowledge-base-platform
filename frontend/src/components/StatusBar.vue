<script setup>
// 模式标签只看"选了几个文档块"，不看后端回传：选了块即 RAG（spec 6.2 parent_ids 为空即普通对话）。
// Task 7（需求 3）：session 前缀 chip 整块删，sessionId prop 也一起删——留着 prop
// 就等于 App.vue 还在传一个没人读的值，下一个人会以为界面上还有地方用它。
const props = defineProps({
  selectedCount: { type: Number, required: true },
})
</script>

<template>
  <div class="status-bar">
    <span v-if="props.selectedCount > 0" class="status-indicator status-rag">
      🔍 知识库模式（{{ props.selectedCount }} 个文档块）
    </span>
    <span v-else class="status-indicator status-normal">💬 普通对话模式</span>
  </div>
</template>
