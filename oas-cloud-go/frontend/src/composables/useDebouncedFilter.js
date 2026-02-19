import { watch, onBeforeUnmount } from "vue";

export function useDebouncedFilter(filterRef, fetchFn, { delay = 400, resetPage } = {}) {
  let timer = null;

  const stop = watch(
    filterRef,
    () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => {
        if (resetPage) resetPage();
        fetchFn();
      }, delay);
    },
    { deep: true },
  );

  onBeforeUnmount(() => {
    if (timer) clearTimeout(timer);
    stop();
  });
}
