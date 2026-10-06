<script setup>
import { computed } from 'vue'

const props = defineProps({
  chunk: { type: Object, required: true },
  selected: { type: Boolean, default: false },
  removable: { type: Boolean, default: false },
  deletable: { type: Boolean, default: false },
  deleting: { type: Boolean, default: false },
})
const emit = defineEmits(['toggle', 'remove', 'delete'])

// 卡面只留「文件名 #块序号」：两列布局放不下正文，正文改挂原生 title 悬浮。
// 序号从 parent_id 尾部取（它由清洗后的文件名派生，形如 `手册.pdf_parent_0`）；
// 对不上就不拼后缀，绝不能显示成 "手册.pdf #undefined"。
const label = computed(() => {
  const match = /_parent_(\d+)$/.exec(props.chunk.parent_id ?? '')
  return match ? `${props.chunk.filename} #${match[1]}` : props.chunk.filename
})

const hoverText = computed(() =>
  `${props.chunk.snippet}\n块 ${props.chunk.parent_id} · ${props.chunk.child_count} 个子块`)
</script>

<template>
  <div class="chunk-card" :class="{ 'chunk-card-selected': props.selected }">
    <button
      class="chunk-card-body"
      type="button"
      :title="hoverText"
      @click="emit('toggle', props.chunk)"
    >
      <span class="chunk-title">
        {{ label }}
        <span v-if="props.selected" class="chunk-badge">已选</span>
      </span>
    </button>
    <!-- 角标按钮排在本体之后：.chunk-card 是横向 flex，第二个孩子才落在右上角（写在前面会跑到左边）。
         stop 也必需：它和本体在同一张卡片里，不拦住冒泡就会连带触发 toggle，看起来像"点一下就选中又取消"。 -->
    <button
      v-if="props.removable"
      class="chunk-remove"
      type="button"
      aria-label="取消选择"
      title="取消选择这个文档块"
      @click.stop="emit('remove', props.chunk.parent_id)"
    >✕</button>
    <!-- 删除与取消选择是两回事，文案不能混：✕ 只动本地选择，🗑 真的删向量库、不可恢复。 -->
    <button
      v-if="props.deletable"
      class="btn btn-ghost btn-small chunk-delete"
      type="button"
      aria-label="删除这个文档块"
      title="从向量库删除这个文档块及其全部子块，不可恢复"
      :disabled="props.deleting"
      @click.stop="emit('delete', props.chunk)"
    >🗑</button>
  </div>
</template>
