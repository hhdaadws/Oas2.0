import { reactive } from "vue";

export function usePagination({ defaultPageSize = 50 } = {}) {
  const pagination = reactive({
    page: 1,
    pageSize: defaultPageSize,
    total: 0,
  });

  function updateTotal(total) {
    pagination.total = total;
  }

  function resetPage() {
    pagination.page = 1;
  }

  function paginationParams() {
    return { page: pagination.page, page_size: pagination.pageSize };
  }

  return { pagination, updateTotal, resetPage, paginationParams };
}
