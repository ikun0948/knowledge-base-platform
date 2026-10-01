<script setup>
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
    >
      <span class="reference-source">📎 {{ reference.filename }}(#{{ reference.document_id }})</span>
      <span class="reference-snippet pre-wrap">{{ reference.snippet }}</span>
    </li>
  </ul>
</template>
