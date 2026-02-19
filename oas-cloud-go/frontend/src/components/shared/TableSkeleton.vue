<script setup>
defineProps({
  rows: { type: Number, default: 5 },
  columns: { type: Number, default: 4 },
});
</script>

<template>
  <div class="table-skeleton">
    <div v-for="i in rows" :key="i" class="table-skeleton-row">
      <el-skeleton :rows="0" animated>
        <template #template>
          <div class="table-skeleton-cols">
            <el-skeleton-item
              v-for="j in columns"
              :key="j"
              variant="text"
              style="flex: 1; height: 18px"
            />
          </div>
        </template>
      </el-skeleton>
    </div>
  </div>
</template>
