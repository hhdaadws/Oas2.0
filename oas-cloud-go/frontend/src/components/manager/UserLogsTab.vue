<template>
  <div class="role-dashboard">
    <section class="panel-card" v-if="selectedUserId">
      <div class="panel-headline">
        <h3>用户 {{ selectedUserId }}（{{ selectedUserAccountNo }}）执行日志</h3>
        <div class="row-actions">
          <el-input v-model="eventTypeFilter" placeholder="按事件类型筛选" clearable style="width:180px" />
          <el-button plain :loading="loading.logs" @click="loadLogs">刷新</el-button>
        </div>
      </div>

      <TableSkeleton v-if="logs.length === 0 && loading.logs" :rows="5" :columns="4" />

      <div v-else class="data-table-wrapper">
        <el-table
          v-loading="loading.logs"
          :data="filteredLogs"
          border
          stripe
          empty-text="暂无日志"
        >
          <el-table-column label="时间" min-width="170" sortable>
            <template #default="scope">{{ formatTime(scope.row.event_at) }}</template>
          </el-table-column>
          <el-table-column prop="task_type" label="任务类型" width="130">
            <template #default="scope">
              <span>{{ scope.row.task_type || "-" }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="event_type" label="事件" width="150" sortable>
            <template #default="scope">
              <el-tag :type="eventTypeTagType(scope.row.event_type)" size="small">{{ scope.row.event_type || "-" }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="job_status" label="任务状态" width="130">
            <template #default="scope">
              <el-tag v-if="scope.row.job_status" :type="jobStatusTagType(scope.row.job_status)" size="small">{{ scope.row.job_status }}</el-tag>
              <span v-else class="muted">-</span>
            </template>
          </el-table-column>
          <el-table-column prop="error_code" label="错误码" width="120" />
          <el-table-column prop="message" label="消息" min-width="220" />
        </el-table>
      </div>

      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :total="pagination.total"
          :page-sizes="[50, 100, 200]"
          layout="total, sizes, prev, pager, next"
          @current-change="loadLogs"
          @size-change="loadLogs"
        />
      </div>
    </section>

    <el-empty
      v-else
      class="empty-center"
      description='请先在"下属配置"中选择用户后再查看日志'
      :image-size="100"
    />
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { managerApi, parseApiError } from "../../lib/http";
import { formatTime } from "../../lib/helpers";
import { usePagination } from "../../composables/usePagination";
import TableSkeleton from "../shared/TableSkeleton.vue";

const props = defineProps({
  token: { type: String, default: "" },
  selectedUserId: { type: Number, default: 0 },
  selectedUserAccountNo: { type: String, default: "" },
});

const loading = reactive({ logs: false });
const logs = ref([]);
const eventTypeFilter = ref("");
const filteredLogs = computed(() => {
  if (!eventTypeFilter.value) return logs.value;
  const q = eventTypeFilter.value.toLowerCase();
  return logs.value.filter((log) => (log.event_type || "").toLowerCase().includes(q));
});

const { pagination, updateTotal, paginationParams } = usePagination({ defaultPageSize: 50 });

function eventTypeTagType(eventType) {
  if (eventType === "success") return "success";
  if (eventType === "fail") return "danger";
  if (eventType === "generated") return "primary";
  if (eventType === "timeout_requeued") return "warning";
  return "info";
}

function jobStatusTagType(status) {
  if (status === "success") return "success";
  if (status === "failed") return "danger";
  if (status === "running") return "primary";
  if (status === "timeout_requeued") return "warning";
  if (status === "leased" || status === "pending") return "info";
  return "info";
}

async function loadLogs() {
  if (!props.selectedUserId || !props.token) return;
  loading.logs = true;
  try {
    const response = await managerApi.getUserLogs(props.token, props.selectedUserId, paginationParams());
    logs.value = response.items || [];
    updateTotal(response.total || logs.value.length);
  } catch (error) {
    ElMessage.error(parseApiError(error));
  } finally {
    loading.logs = false;
  }
}

watch(
  () => props.selectedUserId,
  async (newId) => {
    if (newId && props.token) {
      pagination.page = 1;
      await loadLogs();
    } else {
      logs.value = [];
      pagination.page = 1;
      updateTotal(0);
    }
  },
  { immediate: true },
);
</script>
