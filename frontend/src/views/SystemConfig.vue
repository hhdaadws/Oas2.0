<template>
  <div class="system-config">
    <el-card>
      <template #header>
        <span>系统配置</span>
      </template>

      <el-form :model="form" label-width="140px" class="config-form">
        <el-form-item label="启动方式">
          <el-radio-group v-model="form.launch_mode">
            <el-radio label="adb_monkey">ADB Monkey</el-radio>
            <el-radio label="adb_intent">ADB Intent(带 MAIN/LAUNCHER)</el-radio>
            <el-radio label="am_start">AM Start(显式组件)</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="截图方式">
          <el-radio-group v-model="form.capture_method">
            <el-radio label="adb">ADB 截图</el-radio>
            <el-radio label="ipc">IPC 截图</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="自动检测最优截图">
          <el-space>
            <el-select v-model="benchmark.emulator_id" placeholder="选择模拟器" style="width: 360px">
              <el-option
                v-for="emu in emulators"
                :key="emu.id"
                :label="`${emu.name} (${emu.adb_addr || '无ADB'})`"
                :value="emu.id"
              />
            </el-select>
            <el-input-number v-model="benchmark.rounds" :min="1" :max="20" :step="1" />
            <el-button
              type="primary"
              plain
              :disabled="!benchmark.emulator_id"
              :loading="benchmarkLoading"
              @click="runCaptureBenchmark"
            >
              自动检测
            </el-button>
          </el-space>
          <div v-if="benchmarkResult" style="margin-top: 8px; color: #606266;">
            最优方式：<b>{{ benchmarkResult.best_method }}</b>
            （已自动写入系统配置）
          </div>
        </el-form-item>

        <el-form-item label="ADB 路径">
          <el-input v-model="form.adb_path" placeholder="例如 C:\\Android\\platform-tools\\adb.exe 或 adb" />
        </el-form-item>

        <el-form-item label="IPC DLL 路径">
          <el-input v-model="form.ipc_dll_path" placeholder="例如 C:\\path\\to\\external_renderer_ipc.dll（用于 IPC 截图）" />
        </el-form-item>

        <el-form-item label="MuMu 安装目录">
          <el-input v-model="form.nemu_folder" placeholder="例如 C:\\Program Files\\Netease\\MuMuPlayer-12.0（用于 IPC 截图）" />
        </el-form-item>

        <el-form-item label="MuMu 管理器路径">
          <el-input v-model="form.mumu_manager_path" placeholder="例如 C:\\Program Files\\MuMu\\emulator\\shell\\MuMuManager.exe（用于一键启动模拟器）" />
        </el-form-item>

        <el-form-item label="包名">
          <el-input v-model="form.pkg_name" placeholder="com.netease.onmyoji" />
        </el-form-item>

        <el-form-item label="Activity 名称" v-if="form.launch_mode === 'adb_intent' || form.launch_mode === 'am_start'">
          <el-input v-model="form.activity_name" placeholder="例如 .MainActivity（adb intent 启动时使用）" />
        </el-form-item>

        <el-form-item label="保存失败截图">
          <el-switch v-model="form.save_fail_screenshot" />
          <span style="margin-left: 8px; color: #909399; font-size: 12px;">
            开启后，任务失败时自动截图保存到 fail_screenshots 目录
          </span>
        </el-form-item>

        <el-form-item label="跨模拟器共享缓存">
          <el-switch v-model="form.cross_emulator_cache_enabled" />
          <span style="margin-left: 8px; color: #909399; font-size: 12px;">
            开启后，识图缓存可在不同模拟器间复用；关闭则仅本模拟器内缓存（默认）
          </span>
        </el-form-item>

        <el-form-item>
          <el-button @click="load" :loading="loading">刷新</el-button>
          <el-button type="primary" @click="save" :loading="loading">保存</el-button>
        </el-form-item>
        <el-alert type="info" :closable="false" show-icon>
          <template #title>
            配置保存在数据库，保存后立即生效。
          </template>
        </el-alert>
      </el-form>
    </el-card>

    <el-card style="margin-top: 16px">
      <template #header>
        <span>任务默认失败延迟（分钟）</span>
      </template>
      <el-alert type="info" :closable="false" show-icon style="margin-bottom: 16px">
        <template #title>
          配置各任务类型失败后的重试等待时间。新建账号将继承这些值，不影响已有账号。
        </template>
      </el-alert>
      <el-form label-width="140px" class="config-form">
        <el-form-item
          v-for="taskName in failDelayTaskNames"
          :key="taskName"
          :label="taskName"
        >
          <el-input-number
            v-model="failDelayForm[taskName]"
            :min="1"
            :max="1440"
            :step="5"
            style="width: 180px"
          />
          <span style="margin-left: 8px; color: #909399;">分钟</span>
        </el-form-item>
        <el-form-item>
          <el-button @click="loadFailDelays" :loading="failDelayLoading">刷新</el-button>
          <el-button type="primary" @click="saveFailDelays" :loading="failDelayLoading">保存</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card style="margin-top: 16px">
      <template #header>
        <span>新建账号任务默认启用</span>
      </template>
      <el-alert type="info" :closable="false" show-icon style="margin-bottom: 16px">
        <template #title>
          配置新建账号时各任务的默认开启/关闭状态。修改后仅影响后续新建的账号，不影响已有账号。
        </template>
      </el-alert>
      <el-form label-width="140px" class="config-form">
        <el-form-item
          v-for="taskName in taskEnabledNames"
          :key="taskName"
          :label="taskName"
        >
          <el-switch
            v-model="taskEnabledForm[taskName]"
            active-text="开启"
            inactive-text="关闭"
          />
        </el-form-item>
        <el-form-item>
          <el-button @click="loadTaskEnabledDefaults" :loading="taskEnabledLoading">刷新</el-button>
          <el-button type="primary" @click="saveTaskEnabledDefaults" :loading="taskEnabledLoading">保存</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card style="margin-top: 16px">
      <template #header>
        <span>全局休息开关</span>
      </template>
      <el-alert type="warning" :closable="false" show-icon style="margin-bottom: 16px">
        <template #title>
          关闭后所有账号的休息功能将强制失效，即使账号单独开启了休息也不会生效。
        </template>
      </el-alert>
      <el-form label-width="140px" class="config-form">
        <el-form-item label="全局休息">
          <el-switch
            v-model="globalRestForm.enabled"
            active-text="开启"
            inactive-text="关闭"
          />
        </el-form-item>
        <el-form-item>
          <el-button @click="loadGlobalRest" :loading="globalRestLoading">刷新</el-button>
          <el-button type="primary" @click="saveGlobalRest" :loading="globalRestLoading">保存</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card style="margin-top: 16px">
      <template #header>
        <span>新建账号默认休息配置</span>
      </template>
      <el-alert type="info" :closable="false" show-icon style="margin-bottom: 16px">
        <template #title>
          配置新建账号时休息功能的默认设置。修改后仅影响后续新建的账号，不影响已有账号。
        </template>
      </el-alert>
      <el-form label-width="140px" class="config-form">
        <el-form-item label="默认启用休息">
          <el-switch
            v-model="defaultRestForm.enabled"
            active-text="开启"
            inactive-text="关闭"
          />
        </el-form-item>
        <el-form-item label="休息模式">
          <el-radio-group v-model="defaultRestForm.mode">
            <el-radio label="random">随机（2-3小时）</el-radio>
            <el-radio label="custom">自定义</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="defaultRestForm.mode === 'custom'" label="开始时间">
          <el-time-picker
            v-model="defaultRestForm.start_time"
            format="HH:mm"
            value-format="HH:mm"
            placeholder="选择时间"
          />
        </el-form-item>
        <el-form-item label="持续时长">
          <el-input-number
            v-model="defaultRestForm.duration"
            :min="1"
            :max="5"
          />
          <span style="margin-left: 8px; color: #909399;">小时</span>
        </el-form-item>
        <el-form-item>
          <el-button @click="loadDefaultRestConfig" :loading="defaultRestLoading">刷新</el-button>
          <el-button type="primary" @click="saveDefaultRestConfig" :loading="defaultRestLoading">保存</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card style="margin-top: 16px">
      <template #header>
        <span>对弈竞猜答案配置</span>
        <el-tag v-if="duiyiDate" type="success" size="small" style="margin-left: 8px">
          {{ duiyiDate }}
        </el-tag>
        <el-tag v-else type="info" size="small" style="margin-left: 8px">今日未配置</el-tag>
      </template>
      <el-alert type="info" :closable="false" show-icon style="margin-bottom: 16px">
        <template #title>
          配置今日每个时间窗口的答案（左/右）。未配置答案的窗口不会执行。每日答案独立，次日自动清空。
        </template>
      </el-alert>
      <el-form label-width="140px" class="config-form">
        <el-form-item
          v-for="w in duiyiWindows"
          :key="w.key"
          :label="w.label"
        >
          <el-radio-group v-model="duiyiAnswersForm[w.key]">
            <el-radio :value="null">不配置</el-radio>
            <el-radio value="左">左</el-radio>
            <el-radio value="右">右</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item>
          <el-button @click="loadDuiyiAnswers" :loading="duiyiAnswersLoading">刷新</el-button>
          <el-button type="primary" @click="saveDuiyiAnswers" :loading="duiyiAnswersLoading">保存</el-button>
        </el-form-item>
      </el-form>
      <el-divider />
      <h4 style="margin-bottom: 12px">领取奖励点击区域</h4>
      <el-alert type="info" :closable="false" show-icon style="margin-bottom: 16px">
        <template #title>
          配置领取胜利奖励时的点击区域（左上角和右下角坐标），识别到赢了后在此区域内随机点击。未配置则使用模板匹配位置。
        </template>
      </el-alert>
      <el-form label-width="140px" class="config-form">
        <el-form-item label="左上角 (x1, y1)">
          <el-input-number v-model="duiyiRewardCoordForm.x1" :min="0" :max="959" :step="1" controls-position="right" style="width: 120px" />
          <el-input-number v-model="duiyiRewardCoordForm.y1" :min="0" :max="539" :step="1" controls-position="right" style="width: 120px; margin-left: 12px" />
        </el-form-item>
        <el-form-item label="右下角 (x2, y2)">
          <el-input-number v-model="duiyiRewardCoordForm.x2" :min="0" :max="959" :step="1" controls-position="right" style="width: 120px" />
          <el-input-number v-model="duiyiRewardCoordForm.y2" :min="0" :max="539" :step="1" controls-position="right" style="width: 120px; margin-left: 12px" />
        </el-form-item>
        <el-form-item>
          <el-button @click="loadDuiyiRewardCoord" :loading="duiyiRewardCoordLoading">刷新</el-button>
          <el-button type="primary" @click="saveDuiyiRewardCoord" :loading="duiyiRewardCoordLoading">保存</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { API_ENDPOINTS, apiRequest } from '@/config'

const form = reactive({
  adb_path: '',
  mumu_manager_path: '',
  nemu_folder: '',
  pkg_name: '',
  launch_mode: 'adb_monkey',
  capture_method: 'adb',
  ipc_dll_path: '',
  activity_name: '.MainActivity',
  save_fail_screenshot: false,
  cross_emulator_cache_enabled: false
})
const loading = ref(false)
const emulators = ref([])
const benchmarkLoading = ref(false)
const benchmark = reactive({ emulator_id: null, rounds: 5 })
const benchmarkResult = ref(null)

// 失败延迟配置
const failDelayForm = reactive({})
const failDelayLoading = ref(false)
const failDelayTaskNames = computed(() => Object.keys(failDelayForm))

// 新建账号默认任务启用配置
const taskEnabledForm = reactive({})
const taskEnabledLoading = ref(false)
const taskEnabledNames = computed(() => Object.keys(taskEnabledForm))

// 全局休息开关
const globalRestForm = reactive({ enabled: true })
const globalRestLoading = ref(false)

// 新建账号默认休息配置
const defaultRestForm = reactive({
  enabled: false,
  mode: 'random',
  start_time: null,
  duration: 2
})
const defaultRestLoading = ref(false)

// 对弈竞猜答案配置
const duiyiWindows = [
  { key: '10:00', label: '10:00-12:00' },
  { key: '12:00', label: '12:00-14:00' },
  { key: '14:00', label: '14:00-16:00' },
  { key: '16:00', label: '16:00-18:00' },
  { key: '18:00', label: '18:00-20:00' },
  { key: '20:00', label: '20:00-22:00' },
  { key: '22:00', label: '22:00-00:00' },
]
const duiyiAnswersForm = reactive({
  '10:00': null, '12:00': null, '14:00': null, '16:00': null,
  '18:00': null, '20:00': null, '22:00': null,
})
const duiyiAnswersLoading = ref(false)
const duiyiDate = ref(null)

// 对弈竞猜领奖点击区域
const duiyiRewardCoordForm = reactive({ x1: null, y1: null, x2: null, y2: null })
const duiyiRewardCoordLoading = ref(false)

const fetchEmulators = async () => {
  try {
    const resp = await apiRequest(API_ENDPOINTS.emulators)
    const data = await resp.json()
    emulators.value = Array.isArray(data) ? data : []
  } catch (e) {
    emulators.value = []
  }
}

const load = async () => {
  loading.value = true
  try {
    const resp = await apiRequest(API_ENDPOINTS.system.settings)
    const data = await resp.json()
    Object.assign(form, data)
  } catch (e) {
    ElMessage.error('加载配置失败')
  } finally {
    loading.value = false
  }
}

const save = async () => {
  loading.value = true
  try {
    const resp = await apiRequest(API_ENDPOINTS.system.settings, {
      method: 'PUT',
      body: JSON.stringify(form)
    })
    if (!resp.ok) throw new Error('bad status')
    ElMessage.success('保存成功')
  } catch (e) {
    ElMessage.error('保存失败')
  } finally {
    loading.value = false
  }
}

const runCaptureBenchmark = async () => {
  if (!benchmark.emulator_id) {
    ElMessage.warning('请先选择模拟器')
    return
  }
  benchmarkLoading.value = true
  try {
    const resp = await apiRequest(API_ENDPOINTS.system.captureBenchmark, {
      method: 'POST',
      body: JSON.stringify({
        emulator_id: benchmark.emulator_id,
        rounds: benchmark.rounds
      })
    })
    const data = await resp.json()
    if (!resp.ok) {
      throw new Error(data?.detail || data?.message || '检测失败')
    }
    benchmarkResult.value = data
    if (data.best_method) {
      form.capture_method = data.best_method
    }
    ElMessage.success(data.message || '自动检测完成')
  } catch (e) {
    ElMessage.error(e.message || '自动检测失败')
  } finally {
    benchmarkLoading.value = false
  }
}

const loadFailDelays = async () => {
  failDelayLoading.value = true
  try {
    const resp = await apiRequest(API_ENDPOINTS.system.failDelays)
    const data = await resp.json()
    // 清空现有数据再赋值
    Object.keys(failDelayForm).forEach(k => delete failDelayForm[k])
    Object.assign(failDelayForm, data.delays || {})
  } catch (e) {
    ElMessage.error('加载失败延迟配置失败')
  } finally {
    failDelayLoading.value = false
  }
}

const saveFailDelays = async () => {
  failDelayLoading.value = true
  try {
    const resp = await apiRequest(API_ENDPOINTS.system.failDelays, {
      method: 'PUT',
      body: JSON.stringify({ delays: { ...failDelayForm } })
    })
    if (!resp.ok) {
      const data = await resp.json()
      throw new Error(data?.detail || '保存失败')
    }
    ElMessage.success('失败延迟配置保存成功')
  } catch (e) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    failDelayLoading.value = false
  }
}

const loadTaskEnabledDefaults = async () => {
  taskEnabledLoading.value = true
  try {
    const resp = await apiRequest(API_ENDPOINTS.system.taskEnabledDefaults)
    const data = await resp.json()
    Object.keys(taskEnabledForm).forEach(k => delete taskEnabledForm[k])
    Object.assign(taskEnabledForm, data.enabled || {})
  } catch (e) {
    ElMessage.error('加载默认任务启用配置失败')
  } finally {
    taskEnabledLoading.value = false
  }
}

const saveTaskEnabledDefaults = async () => {
  taskEnabledLoading.value = true
  try {
    const resp = await apiRequest(API_ENDPOINTS.system.taskEnabledDefaults, {
      method: 'PUT',
      body: JSON.stringify({ enabled: { ...taskEnabledForm } })
    })
    if (!resp.ok) {
      const data = await resp.json()
      throw new Error(data?.detail || '保存失败')
    }
    ElMessage.success('默认任务启用配置保存成功')
  } catch (e) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    taskEnabledLoading.value = false
  }
}

// 全局休息开关
const loadGlobalRest = async () => {
  globalRestLoading.value = true
  try {
    const resp = await apiRequest(API_ENDPOINTS.system.globalRest)
    const data = await resp.json()
    globalRestForm.enabled = data.enabled ?? true
  } catch (e) {
    ElMessage.error('加载全局休息开关失败')
  } finally {
    globalRestLoading.value = false
  }
}

const saveGlobalRest = async () => {
  globalRestLoading.value = true
  try {
    const resp = await apiRequest(API_ENDPOINTS.system.globalRest, {
      method: 'PUT',
      body: JSON.stringify({ enabled: globalRestForm.enabled })
    })
    if (!resp.ok) {
      const data = await resp.json()
      throw new Error(data?.detail || '保存失败')
    }
    ElMessage.success('全局休息开关保存成功')
  } catch (e) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    globalRestLoading.value = false
  }
}

// 新建账号默认休息配置
const loadDefaultRestConfig = async () => {
  defaultRestLoading.value = true
  try {
    const resp = await apiRequest(API_ENDPOINTS.system.defaultRestConfig)
    const data = await resp.json()
    defaultRestForm.enabled = data.enabled ?? false
    defaultRestForm.mode = data.mode || 'random'
    defaultRestForm.start_time = data.start_time || null
    defaultRestForm.duration = data.duration ?? 2
  } catch (e) {
    ElMessage.error('加载默认休息配置失败')
  } finally {
    defaultRestLoading.value = false
  }
}

const saveDefaultRestConfig = async () => {
  defaultRestLoading.value = true
  try {
    const resp = await apiRequest(API_ENDPOINTS.system.defaultRestConfig, {
      method: 'PUT',
      body: JSON.stringify({
        enabled: defaultRestForm.enabled,
        mode: defaultRestForm.mode,
        start_time: defaultRestForm.start_time,
        duration: defaultRestForm.duration
      })
    })
    if (!resp.ok) {
      const data = await resp.json()
      throw new Error(data?.detail || '保存失败')
    }
    ElMessage.success('默认休息配置保存成功')
  } catch (e) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    defaultRestLoading.value = false
  }
}

// 对弈竞猜答案配置
const loadDuiyiAnswers = async () => {
  duiyiAnswersLoading.value = true
  try {
    const resp = await apiRequest(API_ENDPOINTS.system.duiyiAnswers)
    const data = await resp.json()
    duiyiDate.value = data.date || null
    const answers = data.answers || {}
    for (const w of duiyiWindows) {
      duiyiAnswersForm[w.key] = answers[w.key] ?? null
    }
  } catch (e) {
    ElMessage.error('加载对弈竞猜答案配置失败')
  } finally {
    duiyiAnswersLoading.value = false
  }
}

const saveDuiyiAnswers = async () => {
  duiyiAnswersLoading.value = true
  try {
    const resp = await apiRequest(API_ENDPOINTS.system.duiyiAnswers, {
      method: 'PUT',
      body: JSON.stringify({ answers: { ...duiyiAnswersForm } })
    })
    const data = await resp.json()
    if (!resp.ok) {
      throw new Error(data?.detail || '保存失败')
    }
    duiyiDate.value = data.date || null
    ElMessage.success('对弈竞猜答案配置保存成功')
  } catch (e) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    duiyiAnswersLoading.value = false
  }
}

// 对弈竞猜领奖点击区域
const loadDuiyiRewardCoord = async () => {
  duiyiRewardCoordLoading.value = true
  try {
    const resp = await apiRequest(API_ENDPOINTS.system.duiyiRewardCoord)
    const data = await resp.json()
    duiyiRewardCoordForm.x1 = data.x1 ?? null
    duiyiRewardCoordForm.y1 = data.y1 ?? null
    duiyiRewardCoordForm.x2 = data.x2 ?? null
    duiyiRewardCoordForm.y2 = data.y2 ?? null
  } catch (e) {
    ElMessage.error('加载领奖坐标配置失败')
  } finally {
    duiyiRewardCoordLoading.value = false
  }
}

const saveDuiyiRewardCoord = async () => {
  const { x1, y1, x2, y2 } = duiyiRewardCoordForm
  if (x1 == null || y1 == null || x2 == null || y2 == null) {
    ElMessage.warning('请填写完整的坐标')
    return
  }
  if (x1 >= x2) {
    ElMessage.warning('x1 必须小于 x2')
    return
  }
  if (y1 >= y2) {
    ElMessage.warning('y1 必须小于 y2')
    return
  }
  duiyiRewardCoordLoading.value = true
  try {
    const resp = await apiRequest(API_ENDPOINTS.system.duiyiRewardCoord, {
      method: 'PUT',
      body: JSON.stringify({ x1, y1, x2, y2 })
    })
    const data = await resp.json()
    if (!resp.ok) {
      throw new Error(data?.detail || '保存失败')
    }
    ElMessage.success('领奖坐标配置保存成功')
  } catch (e) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    duiyiRewardCoordLoading.value = false
  }
}

onMounted(async () => {
  await Promise.all([
    load(),
    fetchEmulators(),
    loadFailDelays(),
    loadTaskEnabledDefaults(),
    loadGlobalRest(),
    loadDefaultRestConfig(),
    loadDuiyiAnswers(),
    loadDuiyiRewardCoord()
  ])
})
</script>

<style scoped>
.config-form {
  max-width: 800px;
}
</style>
