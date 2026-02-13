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
  activity_name: '.MainActivity'
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

onMounted(async () => {
  await Promise.all([load(), fetchEmulators(), loadFailDelays()])
})
</script>

<style scoped>
.config-form {
  max-width: 800px;
}
</style>
