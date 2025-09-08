<template>
  <div class="dashboard">
    <el-card class="scheduler-control" style="margin-bottom: 20px">
      <div style="display: flex; align-items: center; justify-content: space-between">
        <div style="display: flex; align-items: center">
          <span style="margin-right: 10px">调度器状态：</span>
          <el-tag :type="schedulerRunning ? 'success' : 'danger'">
            {{ schedulerRunning ? '运行中' : '已停止' }}
          </el-tag>
        </div>
        <div>
          <el-button v-if="!schedulerRunning" type="success" @click="startScheduler">启动调度器</el-button>
          <el-button v-else type="danger" @click="stopScheduler">停止调度器</el-button>
        </div>
      </div>
    </el-card>

    <el-row :gutter="20" class="stat-cards">
      <el-col :span="6">
        <el-card>
          <el-statistic title="活跃账号数" :value="stats.active_accounts" />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card>
          <el-statistic title="运行中任务" :value="stats.running_accounts" />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card>
          <el-statistic title="队列任务数" :value="stats.queue_size" />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card>
          <el-statistic title="勾协库活跃账号" :value="stats.coop_active_accounts" />
        </el-card>
      </el-col>
    </el-row>

    <el-card class="running-tasks">
      <template #header>
        <div class="card-header">
          <span>实时任务执行列表</span>
          <el-button link @click="refreshData">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </template>

      <el-table :data="runningTasks" stripe>
        <el-table-column prop="account_login_id" label="账号" width="200" />
        <el-table-column prop="task_type" label="任务类型" width="120" />
        <el-table-column label="状态" width="100">
          <template #default>
            <el-tag type="primary">运行中</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="started_at" label="开始时间" width="180">
          <template #default="{ row }">
            {{ formatTime(row.started_at) }}
          </template>
        </el-table-column>
        <el-table-column label="执行时长">
          <template #default="{ row }">
            {{ formatDuration(row.duration) }}
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!runningTasks.length" description="当前没有正在执行的任务" />
    </el-card>

    <el-card class="queue-preview">
      <template #header>
        <div class="card-header">
          <span>任务队列预览（前10个）</span>
        </div>
      </template>

      <el-table :data="queuePreview" stripe>
        <el-table-column prop="account_login_id" label="账号" width="200" />
        <el-table-column prop="task_type" label="任务类型" width="120" />
        <el-table-column prop="priority" label="优先级" width="100">
          <template #default="{ row }">
            <el-tag :type="getPriorityType(row.priority)">{{ row.priority }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="enqueue_time" label="入队时间">
          <template #default="{ row }">
            {{ formatTime(row.enqueue_time) }}
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!queuePreview.length" description="任务队列为空" />
    </el-card>

    <el-card class="system-logs" style="margin-top: 20px">
      <template #header>
        <div class="card-header">
          <span>系统日志</span>
          <div>
            <el-select v-model="logFilter.level" placeholder="日志级别" clearable style="width: 120px; margin-right: 10px" @change="fetchLogs">
              <el-option label="INFO" value="INFO" />
              <el-option label="WARNING" value="WARNING" />
              <el-option label="ERROR" value="ERROR" />
            </el-select>
            <el-select v-model="logFilter.account_id" placeholder="账号（仅显示 login_id != -1）" clearable style="width: 200px; margin-right: 10px" filterable @change="fetchLogs">
              <el-option label="全部账号" :value="null" />
              <el-option v-for="opt in accountOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
            </el-select>
            <el-button link @click="fetchLogs">
              <el-icon><Refresh /></el-icon>
              刷新
            </el-button>
          </div>
        </div>
      </template>

      <el-table :data="systemLogs" stripe height="400">
        <el-table-column prop="timestamp" label="时间" width="180">
          <template #default="{ row }">
            {{ formatTime(row.timestamp) }}
          </template>
        </el-table-column>
        <el-table-column prop="level" label="级别" width="80">
          <template #default="{ row }">
            <el-tag :type="getLevelType(row.level)" size="small">{{ row.level }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="type" label="类型" width="120" />
        <el-table-column prop="account_id" label="账号ID" width="100" />
        <el-table-column label="登录ID" width="160">
          <template #default="{ row }">
            {{ accountLoginMap[row.account_id] ?? '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="message" label="消息" min-width="200" />
      </el-table>

      <div style="margin-top: 10px; text-align: center; color: #909399; font-size: 12px">
        显示最近 {{ systemLogs.length }} 条日志
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'
import { API_ENDPOINTS, apiRequest } from '@/config'
import { getDashboard, getRealtimeStats } from '@/api/dashboard'
import { getAccounts } from '@/api/accounts'

const stats = ref({ active_accounts: 0, running_accounts: 0, queue_size: 0, coop_active_accounts: 0 })
const runningTasks = ref([])
const queuePreview = ref([])
const schedulerRunning = ref(true)

// 日志相关
const systemLogs = ref([])
const logFilter = reactive({ level: '', account_id: null })
const accountOptions = ref([])
const accountLoginMap = ref({})
const LOG_LIMIT = 30

let refreshTimer = null

const fetchData = async () => {
  try {
    const dashboardData = await getDashboard()
    stats.value.active_accounts = dashboardData.active_accounts
    stats.value.running_accounts = dashboardData.running_accounts
    stats.value.coop_active_accounts = dashboardData.coop_active_accounts || 0
    runningTasks.value = dashboardData.running_tasks || []
    queuePreview.value = dashboardData.queue_preview || []

    const realtimeData = await getRealtimeStats()
    stats.value.queue_size = realtimeData.tasks.queue

    await checkSchedulerStatus()
  } catch (error) {
    console.error('获取数据失败:', error)
  }
}

const checkSchedulerStatus = async () => {
  try {
    const response = await apiRequest(API_ENDPOINTS.tasks.scheduler.status)
    const data = await response.json()
    schedulerRunning.value = data.running
  } catch (error) {
    console.error('获取调度器状态失败:', error)
  }
}

const startScheduler = async () => {
  try {
    await apiRequest(API_ENDPOINTS.tasks.scheduler.start, { method: 'POST' })
    schedulerRunning.value = true
    ElMessage.success('调度器已启动')
  } catch (error) {
    ElMessage.error('启动调度器失败')
  }
}

const stopScheduler = async () => {
  try {
    await apiRequest(API_ENDPOINTS.tasks.scheduler.stop, { method: 'POST' })
    schedulerRunning.value = false
    ElMessage.success('调度器已停止')
  } catch (error) {
    ElMessage.error('停止调度器失败')
  }
}

const refreshData = () => {
  fetchData()
  ElMessage.success('数据已刷新')
}

const formatTime = (time) => {
  if (!time) return '-'
  return dayjs(time).format('YYYY-MM-DD HH:mm:ss')
}

const formatDuration = (seconds) => {
  if (!seconds) return '-'
  const minutes = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${minutes}分${secs}秒`
}

const getPriorityType = (priority) => {
  if (priority >= 80) return 'danger'
  if (priority >= 60) return 'warning'
  if (priority >= 40) return 'success'
  return 'info'
}

const getLevelType = (level) => {
  const map = { INFO: 'success', WARNING: 'warning', ERROR: 'danger' }
  return map[level] || 'info'
}

const fetchLogs = async () => {
  try {
    const params = new URLSearchParams()
    params.set('limit', LOG_LIMIT.toString())
    params.set('offset', '0')
    if (logFilter.level) params.set('level', logFilter.level)
    if (logFilter.account_id) params.set('account_id', logFilter.account_id.toString())
    const response = await apiRequest(`${API_ENDPOINTS.tasks.logs}?${params}`)
    const data = await response.json()
    let logs = data.logs || []
    const map = accountLoginMap.value || {}
    logs = logs.filter((l) => {
      const lid = map[l.account_id]
      return l.account_id && lid !== undefined && lid !== '-1'
    })
    systemLogs.value = logs
  } catch (error) {
    console.error('获取系统日志失败:', error)
  }
}

const fetchAccountsForLogs = async () => {
  try {
    const data = await getAccounts()
    const options = []
    const amap = {}
    const visit = (nodes) => {
      for (const n of nodes) {
        if (n.type === 'email' && Array.isArray(n.children)) {
          visit(n.children)
        } else if (n.type === 'game') {
          amap[n.id] = n.login_id
          if (n.login_id !== '-1') options.push({ label: n.login_id, value: n.id })
        }
      }
    }
    visit(data)
    accountOptions.value = options
    accountLoginMap.value = amap
  } catch (e) {
    // ignore
  }
}

onMounted(async () => {
  await fetchAccountsForLogs()
  await fetchData()
  await fetchLogs()
  refreshTimer = setInterval(fetchData, 5000)
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})
</script>

<style scoped lang="scss">
.dashboard {
  .stat-cards {
    margin-bottom: 20px;
  }
  .running-tasks,
  .queue-preview {
    margin-bottom: 20px;
  }
  .card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
}
</style>

