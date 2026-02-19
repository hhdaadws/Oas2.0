<script setup>
defineProps({
  selectedCount: { type: Number, required: true },
});
defineEmits(["clear"]);
</script>

<template>
  <transition name="batch-bar">
    <div v-if="selectedCount > 0" class="batch-action-bar">
      <span class="batch-count">已选择 <strong>{{ selectedCount }}</strong> 项</span>
      <div class="batch-actions">
        <slot />
      </div>
      <el-button text size="small" @click="$emit('clear')">取消选择</el-button>
    </div>
  </transition>
</template>
