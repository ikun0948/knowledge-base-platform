<script setup>
import { docLabel } from '../composables/useDocuments.js'

const props = defineProps({
  chunk: { type: Object, required: true },
  selected: { type: Boolean, default: false },
  removable: { type: Boolean, default: false },
})
const emit = defineEmits(['toggle', 'remove'])
</script>

<template>
  <div class="chunk-card" :class="{ 'chunk-card-selected': props.selected }">
    <button class="chunk-card-body" type="button" @click="emit('toggle', props.chunk)">
      <span class="chunk-title">
        {{ docLabel(props.chunk) }}
        <span v-if="props.selected" class="chunk-badge">已选</span>
      </span>
      <span class="chunk-snippet">{{ props.chunk.snippet }}</span>
      <span class="chunk-meta">块 {{ props.chunk.parent_id }} · {{ props.chunk.child_count }} 个子块</span>
    </button>
    <!-- 红叉排在卡片本体之后：.chunk-card 是横向 flex，第二个孩子才落在右上角（写在前面会顶到左上角）。
         stop 也是必需的：红叉嵌在同一张卡片里，不拦住冒泡就会连带触发 toggle，看起来像"取消两次=没变"。 -->
    <button
      v-if="props.removable"
      class="chunk-remove"
      type="button"
      aria-label="取消选择"
      title="取消选择这个文档块"
      @click.stop="emit('remove', props.chunk.parent_id)"
    >✕</button>
  </div>
</template>
