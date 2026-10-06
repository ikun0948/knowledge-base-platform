<script setup>
import { docLabel } from '../composables/useDocuments.js'

const props = defineProps({
  references: { type: Array, required: true },
})
</script>

<template>
  <ul class="reference-list">
    <li
      v-for="(reference, i) in props.references"
      :key="`${reference.document_id}-${reference.parent_id}-${i}`"
      class="reference-item"
      :class="{ 'reference-deleted': reference.deleted }"
    >
      <span class="reference-source">📎 {{ docLabel(reference) }}</span>
      <span v-if="reference.deleted" class="reference-state">🗑 已删除（之前的答案仍然引用它）</span>
      <span class="reference-snippet pre-wrap">{{ reference.snippet }}</span>
    </li>
  </ul>
</template>
