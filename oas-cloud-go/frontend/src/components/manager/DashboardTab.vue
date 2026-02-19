<template>
  <div class="role-dashboard">
    <section class="panel-card">
      <div class="panel-headline">
        <h3>仪表盘</h3>
        <el-button plain size="small" :loading="loading" @click="loadDashboard">刷新</el-button>
      </div>

      <div class="stats-grid" style="margin-bottom:16px">
        <div class="stat-item">
          <span class="stat-label">总用户数</span>
          <strong class="stat-value">{{ data.total_users }}</strong>
        </div>
        <div class="stat-item">
          <span class="stat-label">活跃账号</span>
          <strong class="stat-value">{{ data.active_users }}</strong>
        </div>
        <div class="stat-item">
          <span class="stat-label">运行中任务</span>
          <strong class="stat-value">{{ data.running_jobs }}</strong>
        </div>
        <div class="stat-item">
          <span class="stat-label">待执行任务</span>
          <strong class="stat-value">{{ data.pending_jobs }}</strong>
        </div>
        <div class="stat-item">
          <span class="stat-label">今日成功</span>
          <strong class="stat-value" style="color:var(--el-color-success)">{{ data.today_success }}</strong>
        </div>
        <div class="stat-item">
          <span class="stat-label">今日失败</span>
          <strong class="stat-value" style="color:var(--el-color-danger)">{{ data.today_failed }}</strong>
        </div>
      </div>

      <h4 style="margin-bottom:8px">账号状态概览</h4>
      <el-table :data="data.user_status_summary" border stripe size="small" empty-text="暂无数据" style="margin-bottom:16px">
        <el-table-column prop="user_id" label="ID" width="70" />
        <el-table-column prop="account_no" label="账号" min-width="160" />
        <el-table-column prop="account_status" label="游戏状态" width="100">
          <template #default="scope">
            <el-tag v-if="scope.row.account_status === 'active'" type="success" size="small">正常</el-tag>
            <el-tag v-else-if="scope.row.account_status === 'invalid'" type="danger" size="small">异常</el-tag>
            <el-tag v-else-if="scope.row.account_status === 'cangbaoge'" type="warning" size="small">藏宝阁</el-tag>
            <el-tag v-else type="info" size="small">-</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="current_task" label="当前任务" width="120">
          <template #default="scope">{{ scope.row.current_task || '-' }}</template>
        </el-table-column>
        <el-table-column label="最近活跃" width="160">
          <template #default="scope">{{ formatTime(scope.row.last_active) }}</template>
        </el-table-column>
      </el-table>

      <h4 style="margin-bottom:8px">最近任务</h4>
      <el-table :data="data.recent_jobs" border stripe size="small" empty-text="暂无任务">
        <el-table-column prop="user_id" label="用户ID" width="80" />
        <el-table-column prop="task_name" label="任务" min-width="140" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="scope">
            <el-tag :type="jobStatusType(scope.row.status)" size="small">{{ scope.row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="开始时间" width="160">
          <template #default="scope">{{ formatTime(scope.row.started_at) }}</template>
        </el-table-column>
      </el-table>
    </section>
  </div>
</template>

<script setup>
import { ref, reactive, watch } from "vue";
import { ElMessage } from "element-plus";
import { managerApi, parseApiError } from "../../lib/http";
import { formatTime } from "../../lib/helpers";

const props = defineProps({ token: { type: String, default: "" } });

const loading = ref(false);
const data = reactive({
  total_users: 0,
  active_users: 0,
  running_jobs: 0,
  pending_jobs: 0,
  today_success: 0,
  today_failed: 0,
  recent_jobs: [],
  user_status_summary: [],
});

function jobStatusType(status) {
  if (status === "success") return "success";
  if (status === "failed") return "danger";
  if (status === "running" || status === "leased") return "warning";
  return "info";
}

async function loadDashboard() {
  if (!props.token) return;
  loading.value = true;
  try {
    const res = await managerApi.getDashboard(props.token);
    Object.assign(data, res);
  } catch (e) {
    ElMessage.error(parseApiError(e));
  } finally {
    loading.value = false;
  }
}

watch(() => props.token, (val) => { if (val) loadDashboard(); }, { immediate: true });
</script>
