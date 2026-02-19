import { ref, computed } from "vue";

export function useBatchSelection() {
  const selectedRows = ref([]);

  const selectedIds = computed(() => selectedRows.value.map((r) => r.id));
  const selectedCount = computed(() => selectedRows.value.length);
  const hasSelection = computed(() => selectedRows.value.length > 0);

  function onSelectionChange(rows) {
    selectedRows.value = rows;
  }

  function clearSelection() {
    selectedRows.value = [];
  }

  return {
    selectedRows,
    selectedIds,
    selectedCount,
    hasSelection,
    onSelectionChange,
    clearSelection,
  };
}
