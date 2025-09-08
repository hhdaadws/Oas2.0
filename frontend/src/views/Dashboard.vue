<template>
  <div class="dashboard">
    <!-- 调度器控制 -->
    <el-card class="scheduler-control" style="margin-bottom: 20px">
      <div style="display: flex; align-items: center; justify-content: space-between">
        <div style="display: flex; align-items: center">
          <span style="margin-right: 10px">调度器状态：</span>
          <el-tag :type="schedulerRunning ? 'success' : 'danger'">
            {{ schedulerRunning ? '运行中' : '已停止' }}
          </el-tag>
        </div>
        <div>
          <el-button
            v-if="!schedulerRunning"
            type="success"
            @click="startScheduler"
          >
            启动调度器
          </el-button>
          <el-button
            v-else
            type="danger"
            @click="stopScheduler"
          >
            停止调度器
          </el-button>
        </div>
      </div>
    </el-card>
    
    <!-- 统计卡片 -->
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
          <el-statistic title="今日完成" :value="stats.today_completed" />
        </el-card>
      </el-col>
    </el-row>
    
    <!-- 实时任务执行列表 -->
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
    
    <!-- 任务队列预览 -->
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
            <el-tag :type="getPriorityType(row.priority)">
              {{ row.priority }}
            </el-tag>
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
    
    <!-- 系统日志 -->
    <el-card class="system-logs" style="margin-top: 20px">
      <template #header>
        <div class="card-header">
          <span>系统日志</span>
          <div>
            <el-select
              v-model="logFilter.level"
              placeholder="日志级别"
              clearable
              style="width: 120px; margin-right: 10px"
              @change="fetchLogs"
            >
              <el-option label="INFO" value="INFO" />
              <el-option label="WARNING" value="WARNING" />
              <el-option label="ERROR" value="ERROR" />
            </el-select>
            <el-select
              v-model="logFilter.account_id"
              placeholder="账号"
              clearable
              style="width: 120px; margin-right: 10px"
              @change="fetchLogs"
            >
              <el-option label="全部账号" :value="null" />
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
            <el-tag :type="getLevelType(row.level)" size="small">
              {{ row.level }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="type" label="类型" width="120" />
        <el-table-column prop="account_id" label="账号ID" width="80" />
        <el-table-column prop="message" label="消息" min-width="200" />
      </el-table>
      
      <div style="margin-top: 10px; text-align: center; color: #909399; font-size: 12px">
        显示最新 {{ systemLogs.length }} 条日志
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { getDashboard, getRealtimeStats } from '@/api/dashboard'
import { ElMessage } from 'element-plus'
import dayjs from 'dayjs'
import { API_ENDPOINTS, apiRequest } from '@/config'

// 数据
const stats = ref({
  active_accounts: 0,
  running_accounts: 0,
  queue_size: 0,
  today_completed: 0
})
const runningTasks = ref([])
const queuePreview = ref([])
const schedulerRunning = ref(true)
const systemLogs = ref([])

// 日志筛选
const logFilter = reactive({
  level: '',
  account_id: null
})

// 日志配置（固定30条）
const LOG_LIMIT = 30

// 定时器
let refreshTimer = null

// 获取数据
const fetchData = async () => {
  try {
    // 获取仪表盘数据
    const dashboardData = await getDashboard()
    stats.value.active_accounts = dashboardData.active_accounts
    stats.value.running_accounts = dashboardData.running_accounts
    runningTasks.value = dashboardData.running_tasks || []
    queuePreview.value = dashboardData.queue_preview || []
    
    // 获取实时统计
    const realtimeData = await getRealtimeStats()
    stats.value.queue_size = realtimeData.tasks.queue
    stats.value.today_completed = realtimeData.tasks.today_completed
    
    // 获取调度器状态
    await checkSchedulerStatus()
  } catch (error) {
    console.error('获取数据失败:', error)
  }
}

// 检查调度器状态
const checkSchedulerStatus = async () => {
  try {
    const response = await apiRequest(API_ENDPOINTS.tasks.scheduler.status)
    const data = await response.json()
    schedulerRunning.value = data.running
  } catch (error) {
    console.error('获取调度器状态失败:', error)
  }
}

// 启动调度器
const startScheduler = async () => {
  try {
    await apiRequest(API_ENDPOINTS.tasks.scheduler.start, { method: 'POST' })
    schedulerRunning.value = true
    ElMessage.success('调度器已启动')
  } catch (error) {
    ElMessage.error('启动调度器失败')
  }
}

// 停止调度器
const stopScheduler = async () => {
  try {
    await apiRequest(API_ENDPOINTS.tasks.scheduler.stop, { method: 'POST' })
    schedulerRunning.value = false
    ElMessage.success('调度器已停止')
  } catch (error) {
    ElMessage.error('停止调度器失败')
  }
}

// 刷新数据
const refreshData = () => {
  fetchData()
  ElMessage.success('数据已刷新')
}

// 格式化时间
const formatTime = (time) => {
  if (!time) return '-'
  return dayjs(time).format('YYYY-MM-DD HH:mm:ss')
}

// 格式化时长
const formatDuration = (seconds) => {
  if (!seconds) return '-'
  const minutes = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${minutes}分${secs}秒`
}

// 获取优先级标签类型
const getPriorityType = (priority) => {
  if (priority >= 80) return 'danger'
  if (priority >= 60) return 'warning'
  if (priority >= 40) return 'success'
  return 'info'
}

// 获取日志级别标签类型
const getLevelType = (level) => {
  const map = {
    'INFO': 'success',
    'WARNING': 'warning', 
    'ERROR': 'danger'
  }
  return map[level] || 'info'
}

// 获取系统日志（最新30条）
const fetchLogs = async () => {
  try {
    const params = new URLSearchParams()
    params.set('limit', LOG_LIMIT.toString())
    params.set('offset', '0')  // 始终从第一条开始
    
    if (logFilter.level) {
      params.set('level', logFilter.level)
    }
    if (logFilter.account_id) {
      params.set('account_id', logFilter.account_id.toString())
    }
    
    const response = await apiRequest(`${API_ENDPOINTS.tasks.logs}?${params}`)
    const data = await response.json()
    
    systemLogs.value = data.logs || []
  } catch (error) {
    console.error('获取系统日志失败:', error)
  }
}

onMounted(() => {
  fetchData()
  fetchLogs()
  // 每5秒刷新一次
  refreshTimer = setInterval(fetchData, 5000)
})

onUnmounted(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
  }
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
}</style>