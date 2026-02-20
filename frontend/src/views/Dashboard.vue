<template>
  <div class="dashboard">
    <el-card class="scheduler-control" style="margin-bottom: 20px">
      <div style="display: flex; align-items: center; justify-content: space-between">
        <div style="display: flex; align-items: center">
          <span style="margin-right: 10px">执行引擎状态：</span>
          <el-tag :type="schedulerRunning ? 'success' : 'danger'">
            {{ schedulerRunning ? '运行中' : '已停止' }}
          </el-tag>
        </div>
        <div>
          <el-button v-if="!schedulerRunning" type="success" @click="startScheduler">启动执行引擎</el-button>
          <el-button v-else type="danger" @click="stopScheduler">停止执行引擎</el-button>
        </div>
      </div>
    </el-card>

    <el-card v-if="!isCloud" style="margin-bottom: 20px">
      <template #header>
        <div class="card-header">
          <span>全局任务开关</span>
        </div>
      </template>
      <div style="display: flex; align-items: center">
        <span style="margin-right: 10px">召唤礼包：</span>
        <el-switch v-model="taskSwitches.召唤礼包" @change="saveTaskSwitches" />
      </div>
    </el-card>

    <el-row :gutter="20" class="stat-cards">
      <el-col v-if="!isCloud" :span="6">
        <el-card>
          <el-statistic title="活跃账号数" :value="stats.active_accounts" />
        </el-card>
      </el-col>
      <el-col :span="isCloud ? 12 : 6">
        <el-card>
          <el-statistic title="运行中任务" :value="stats.running_accounts" />
        </el-card>
      </el-col>
      <el-col :span="isCloud ? 12 : 6">
        <el-card>
          <el-statistic title="队列任务数" :value="stats.queue_size" />
        </el-card>
      </el-col>
      <el-col v-if="!isCloud" :span="6">
        <el-card>
          <el-statistic title="勾协库活跃账号" :value="stats.coop_active_accounts" />
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" class="runtime-panels">
      <el-col :span="12">
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

          <el-table :data="runningTasks" stripe height="400">
            <el-table-column prop="account_login_id" label="账号" width="140" />
            <el-table-column prop="task_type" label="任务类型" width="110" />
            <el-table-column prop="emulator_name" label="模拟器" width="120">
              <template #default="{ row }">
                {{ row.emulator_name || '-' }}
              </template>
            </el-table-column>
            <el-table-column label="状态" width="90">
              <template #default>
                <el-tag type="primary">运行中</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="started_at" label="开始时间" min-width="150">
              <template #default="{ row }">
                {{ formatTime(row.started_at) }}
              </template>
            </el-table-column>
          </el-table>

          <el-empty v-if="!runningTasks.length" description="当前没有正在执行的任务" />
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card class="runtime-logs-card">
          <template #header>
            <div class="card-header">
              <span>运行时详细日志</span>
              <div>
                <el-select
                  v-model="runtimeLogFilter.level"
                  placeholder="级别"
                  clearable
                  size="small"
                  style="width: 110px; margin-right: 8px"
                  @change="handleRuntimeFilterChange"
                >
                  <el-option label="INFO" value="INFO" />
                  <el-option label="WARNING" value="WARNING" />
                  <el-option label="ERROR" value="ERROR" />
                </el-select>
                <el-select
                  v-model="runtimeLogFilter.emulator_id"
                  placeholder="模拟器"
                  clearable
                  size="small"
                  style="width: 120px; margin-right: 8px"
                  @change="handleRuntimeFilterChange"
                >
                  <el-option label="全部" :value="null" />
                  <el-option
                    v-for="eid in runtimeEmulatorOptions"
                    :key="eid"
                    :label="`模拟器 ${eid}`"
                    :value="eid"
                  />
                </el-select>
                <el-button link @click="fetchRuntimeLogs(true)">
                  <el-icon><Refresh /></el-icon>
                  刷新
                </el-button>
              </div>
            </div>
          </template>

          <el-table :data="runtimeLogs" stripe height="400">
            <el-table-column prop="timestamp" label="时间" width="180">
              <template #default="{ row }">
                {{ formatTime(row.timestamp) }}
              </template>
            </el-table-column>
            <el-table-column label="模块" width="180" show-overflow-tooltip>
              <template #default="{ row }">
                {{ formatModuleName(row.module) }}
              </template>
            </el-table-column>
            <el-table-column prop="message" label="执行步骤" min-width="260" show-overflow-tooltip />
            <el-table-column label="模拟器" width="80">
              <template #default="{ row }">
                {{ row.emulator_id ?? '-' }}
              </template>
            </el-table-column>
          </el-table>

          <el-empty v-if="!runtimeLogs.length" description="暂无运行时详细日志" />
        </el-card>
      </el-col>
    </el-row>

    <el-card v-if="!isCloud" class="queue-preview">
      <template #header>
        <div class="card-header">
          <span>计划任务预览（已到期 + 等待中）</span>
        </div>
      </template>

      <el-table :data="scheduledPreview" stripe>
        <el-table-column prop="account_login_id" label="账号" width="200" />
        <el-table-column prop="task_type" label="任务类型" width="120" />
        <el-table-column prop="priority" label="优先级" width="100">
          <template #default="{ row }">
            <el-tag :type="getPriorityType(row.priority)">{{ row.priority }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="next_time" label="下次执行时间" min-width="180">
          <template #default="{ row }">
            <template v-if="row.is_due">
              <el-tag type="danger" size="small">已到期</el-tag>
              <span style="margin-left: 6px; color: #909399; font-size: 12px">{{ row.next_time }}</span>
            </template>
            <template v-else>
              <el-tag type="success" size="small">等待中</el-tag>
              <span style="margin-left: 6px">{{ row.next_time || '-' }}</span>
            </template>
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!scheduledPreview.length" description="暂无计划任务" />
    </el-card>

    <el-card v-if="isCloud" class="queue-preview">
      <template #header>
        <div class="card-header">
          <span>已获取的云端任务</span>
          <el-button link @click="refreshData">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </template>

      <el-table :data="cloudJobsPreview" stripe>
        <el-table-column prop="job_id" label="Job ID" width="100" />
        <el-table-column prop="account_login_id" label="账号" width="200">
          <template #default="{ row }">
            {{ row.account_login_id || row.account_id || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="task_type" label="任务类型" width="120" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === '执行中' ? 'primary' : 'warning'" size="small">
              {{ row.status }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!cloudJobsPreview.length" description="暂无已获取的云端任务" />
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'
import { API_ENDPOINTS, apiRequest } from '@/config'
import { getDashboard, getRealtimeStats } from '@/api/dashboard'
import { getMode } from '@/api/request'

const isCloud = computed(() => getMode() === 'cloud')

const stats = ref({ active_accounts: 0, running_accounts: 0, queue_size: 0, coop_active_accounts: 0 })
const runningTasks = ref([])
const queuePreview = ref([])
const scheduledPreview = ref([])
const cloudJobsPreview = ref([])
const schedulerRunning = ref(false)
const taskSwitches = reactive({ '召唤礼包': false })
const runtimeLogs = ref([])
const runtimeLogFilter = reactive({ level: '', emulator_id: null })
const runtimeEmulatorOptions = ref([])

const runtimeLogCursor = ref(null)

let coreRefreshTimer = null
let runtimeLogTimer = null
let isFetchingData = false
let pendingFetchData = false

const fetchSchedulerStatus = async () => {
  const response = await apiRequest(API_ENDPOINTS.tasks.scheduler.status)
  if (!response.ok) {
    throw new Error(`scheduler status request failed: ${response.status}`)
  }
  return response.json()
}

const fetchData = async () => {
  if (isFetchingData) {
    pendingFetchData = true
    return
  }

  isFetchingData = true
  try {
    const [dashboardData, realtimeData, schedulerData] = await Promise.all([
      getDashboard(),
      getRealtimeStats(),
      fetchSchedulerStatus()
    ])

    stats.value.active_accounts = dashboardData.active_accounts
    stats.value.running_accounts = dashboardData.running_accounts
    stats.value.coop_active_accounts = dashboardData.coop_active_accounts || 0
    stats.value.queue_size = realtimeData?.tasks?.queue ?? 0
    runningTasks.value = dashboardData.running_tasks || []
    queuePreview.value = dashboardData.queue_preview || []
    scheduledPreview.value = dashboardData.scheduled_preview || []
    cloudJobsPreview.value = dashboardData.cloud_jobs_preview || []
    schedulerRunning.value = Boolean(schedulerData.running)
  } catch (error) {
    console.error('Failed to fetch dashboard data:', error)
  } finally {
    isFetchingData = false
    if (pendingFetchData) {
      pendingFetchData = false
      void fetchData()
    }
  }
}

const checkSchedulerStatus = async () => {
  try {
    const data = await fetchSchedulerStatus()
    schedulerRunning.value = Boolean(data.running)
  } catch (error) {
    console.error('Failed to fetch scheduler status:', error)
  }
}


const startScheduler = async () => {
  try {
    await apiRequest(API_ENDPOINTS.tasks.scheduler.start, { method: 'POST' })
    schedulerRunning.value = true
    ElMessage.success(
      isCloud.value
        ? '执行引擎已启动（cloud poller + executor）'
        : '执行引擎已启动（feeder + executor）'
    )
  } catch (error) {
    ElMessage.error('启动执行引擎失败')
  }
}

const stopScheduler = async () => {
  try {
    await apiRequest(API_ENDPOINTS.tasks.scheduler.stop, { method: 'POST' })
    schedulerRunning.value = false
    ElMessage.success(
      isCloud.value
        ? '执行引擎已停止（cloud poller + executor）'
        : '执行引擎已停止（feeder + executor）'
    )
  } catch (error) {
    ElMessage.error('停止执行引擎失败')
  }
}

const refreshData = () => {
  fetchData()
  ElMessage.success('数据已刷新')
}

const fetchTaskSwitches = async () => {
  try {
    const response = await apiRequest(API_ENDPOINTS.system.taskSwitches)
    const data = await response.json()
    const switches = data.switches || {}
    taskSwitches['召唤礼包'] = Boolean(switches['召唤礼包'])
  } catch (error) {
    console.error('获取全局任务开关失败:', error)
  }
}

const saveTaskSwitches = async () => {
  try {
    await apiRequest(API_ENDPOINTS.system.taskSwitches, {
      method: 'PUT',
      body: JSON.stringify({ switches: { '召唤礼包': taskSwitches['召唤礼包'] } })
    })
    ElMessage.success('全局任务开关已保存')
  } catch (error) {
    ElMessage.error('保存全局任务开关失败')
  }
}

const mergeRuntimeLogs = (currentLogs, incomingLogs, maxItems = 80) => {
  const seen = new Set()
  const merged = []

  for (const item of [...currentLogs, ...incomingLogs]) {
    const key = `${item.timestamp_epoch || ''}|${item.module || ''}|${item.message || ''}|${item.emulator_id || ''}`
    if (seen.has(key)) continue
    seen.add(key)
    merged.push(item)
  }

  merged.sort((a, b) => (a.timestamp_epoch || 0) - (b.timestamp_epoch || 0))
  return merged.slice(-maxItems)
}

const handleRuntimeFilterChange = () => {
  fetchRuntimeLogs(true)
}

const fetchRuntimeLogs = async (reset = false) => {
  try {
    if (reset) {
      runtimeLogCursor.value = null
      runtimeLogs.value = []
    }

    const params = new URLSearchParams()
    params.set('limit', '80')
    if (runtimeLogFilter.level) params.set('level', runtimeLogFilter.level)
    if (runtimeLogFilter.emulator_id !== null && runtimeLogFilter.emulator_id !== undefined) {
      params.set('emulator_id', String(runtimeLogFilter.emulator_id))
    }
    if (runtimeLogCursor.value) {
      params.set('cursor', runtimeLogCursor.value)
    }

    const response = await apiRequest(`${API_ENDPOINTS.tasks.runtimeLogs}?${params}`)
    const data = await response.json()
    const incoming = data.logs || []

    runtimeLogs.value = mergeRuntimeLogs(runtimeLogs.value, incoming, 80)

    if (data.next_cursor) {
      runtimeLogCursor.value = data.next_cursor
    }

    const emulatorSet = new Set(
      runtimeLogs.value
        .map((x) => x.emulator_id)
        .filter((x) => x !== null && x !== undefined)
    )
    runtimeEmulatorOptions.value = Array.from(emulatorSet).sort((a, b) => a - b)
  } catch (error) {
    console.error('Failed to fetch runtime logs:', error)
  }
}

const formatTime = (time) => {
  if (!time) return '-'
  return dayjs(time).format('YYYY-MM-DD HH:mm:ss')
}

const formatModuleName = (name) => {
  if (!name) return '-'
  return name.replace('app.modules.', '')
}

const getPriorityType = (priority) => {
  if (priority >= 80) return 'danger'
  if (priority >= 60) return 'warning'
  if (priority >= 40) return 'success'
  return 'info'
}

onMounted(async () => {
  await fetchData()
  await fetchRuntimeLogs(true)
  await fetchTaskSwitches()
  coreRefreshTimer = setInterval(fetchData, 5000)
  runtimeLogTimer = setInterval(() => fetchRuntimeLogs(false), 15000)
})

onUnmounted(() => {
  if (coreRefreshTimer) clearInterval(coreRefreshTimer)
  if (runtimeLogTimer) clearInterval(runtimeLogTimer)
})
</script>

<style scoped lang="scss">
.dashboard {
  .stat-cards {
    margin-bottom: 20px;
  }
  .running-tasks,
  .runtime-logs-card,
  .runtime-panels,
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

