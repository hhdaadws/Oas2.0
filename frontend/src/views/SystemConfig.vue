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
  </div>
</template>

<script setup>
import { reactive, ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { API_ENDPOINTS, apiRequest } from '@/config'

const form = reactive({
  adb_path: '',
  mumu_manager_path: '',
  nemu_folder: '',
  pkg_name: '',
  launch_mode: 'adb_monkey',
  ipc_dll_path: '',
  activity_name: '.MainActivity'
})
const loading = ref(false)

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

onMounted(load)
</script>

<style scoped>
.config-form {
  max-width: 800px;
}
</style>
