<template>
  <div class="account-pull">
    <!-- 抓取表单 -->
    <el-card class="pull-card">
      <template #header>
        <div class="card-header">
          <span>账号抓取</span>
        </div>
      </template>

      <el-form :model="form" label-width="100px" :rules="rules" ref="formRef">
        <el-form-item label="选择模拟器" prop="emulator_id">
          <el-select v-model="form.emulator_id" placeholder="请选择模拟器" style="width: 300px;">
            <el-option
              v-for="emu in emulators"
              :key="emu.id"
              :label="`${emu.name} (${emu.adb_addr})`"
              :value="emu.id"
              :disabled="emu.state !== 'connected'"
            >
              <span>{{ emu.name }}</span>
              <span style="margin-left: 10px; color: #909399;">{{ emu.adb_addr }}</span>
              <el-tag v-if="emu.state !== 'connected'" size="small" type="danger" style="margin-left: 10px;">未连接</el-tag>
            </el-option>
          </el-select>
        </el-form-item>

        <el-form-item label="抓取类型" prop="pull_type">
          <el-radio-group v-model="form.pull_type">
            <el-radio value="gouxie">勾协账号</el-radio>
            <el-radio value="putong">普通账号</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="账号ID" prop="account_id">
          <el-input
            v-model="form.account_id"
            placeholder="输入账号ID（将作为保存文件夹名）"
            style="width: 300px;"
          />
        </el-form-item>

        <el-form-item label="抓取后建号">
          <el-radio-group v-model="postPullMode" @change="savePostPullSettings">
            <el-radio value="none">不创建</el-radio>
            <el-radio value="auto">自动创建</el-radio>
            <el-radio value="confirm">弹窗确认</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item v-if="postPullMode !== 'none'" label="默认区服">
          <el-select v-model="defaultZone" placeholder="请选择默认区服" style="width: 300px;" @change="savePostPullSettings">
            <el-option v-for="z in ZONES" :key="z" :label="z" :value="z" />
          </el-select>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="handlePull" :loading="pulling">
            <el-icon><Download /></el-icon>
            开始抓取
          </el-button>
          <el-button
            type="success"
            plain
            style="margin-left: 12px;"
            :disabled="!form.emulator_id"
            :loading="pushing"
            @click="handlePushData"
          >
            <el-icon><Upload /></el-icon>
            上传信息
          </el-button>
          <el-button
            type="danger"
            plain
            style="margin-left: 12px;"
            :disabled="!form.emulator_id"
            @click="handleDeleteLoginData"
          >
            <el-icon><Delete /></el-icon>
            删除登录数据
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 已抓取账号列表 -->
    <el-card class="list-card">
      <template #header>
        <div class="card-header">
          <span>已抓取账号</span>
          <el-radio-group v-model="listType" @change="fetchAccounts">
            <el-radio-button value="gouxie">勾协账号</el-radio-button>
            <el-radio-button value="putong">普通账号</el-radio-button>
          </el-radio-group>
        </div>
      </template>

      <el-table :data="accounts" stripe>
        <el-table-column prop="account_id" label="账号ID" width="200" />
        <el-table-column label="数据状态" width="250">
          <template #default="{ row }">
            <el-tag v-if="row.has_shared_prefs" type="success" size="small" style="margin-right: 5px;">shared_prefs</el-tag>
            <el-tag v-else type="danger" size="small" style="margin-right: 5px;">shared_prefs缺失</el-tag>
            <el-tag v-if="row.has_clientconfig" type="success" size="small">clientconfig</el-tag>
            <el-tag v-else type="danger" size="small">clientconfig缺失</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="path" label="保存路径" />
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button link type="danger" @click="handleDelete(row)">
              <el-icon><Delete /></el-icon>
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!accounts.length" description="暂无已抓取账号" />
    </el-card>

    <!-- 建号确认对话框 -->
    <el-dialog
      v-model="createAccountDialogVisible"
      title="创建游戏账号"
      width="400px"
    >
      <el-form :model="createAccountForm" label-width="80px">
        <el-form-item label="账号ID">
          <el-input v-model="createAccountForm.login_id" disabled />
        </el-form-item>
        <el-form-item label="区服" required>
          <el-select v-model="createAccountForm.zone" placeholder="请选择区服" style="width: 100%;">
            <el-option v-for="z in ZONES" :key="z" :label="z" :value="z" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createAccountDialogVisible = false">跳过</el-button>
        <el-button type="primary" @click="handleConfirmCreateAccount" :loading="creatingAccount">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { API_BASE_URL, apiRequest, API_ENDPOINTS } from '@/config'

// 模拟器列表
const emulators = ref([])

// 已抓取账号列表
const accounts = ref([])
const listType = ref('gouxie')

// 表单
const formRef = ref()
const form = reactive({
  emulator_id: null,
  pull_type: 'gouxie',
  account_id: ''
})

// 表单验证规则
const rules = {
  emulator_id: [{ required: true, message: '请选择模拟器', trigger: 'change' }],
  pull_type: [{ required: true, message: '请选择抓取类型', trigger: 'change' }],
  account_id: [
    { required: true, message: '请输入账号ID', trigger: 'blur' },
    { pattern: /^[a-zA-Z0-9_-]+$/, message: '账号ID只能包含字母、数字、下划线和横线', trigger: 'blur' }
  ]
}

// 抓取状态
const pulling = ref(false)
const pushing = ref(false)

// 抓取后建号配置
const postPullMode = ref('none')  // 'none' | 'auto' | 'confirm'
const defaultZone = ref('樱之华')
const ZONES = ['樱之华', '春之樱', '两情相悦', '枫之舞']

// 建号对话框
const createAccountDialogVisible = ref(false)
const creatingAccount = ref(false)
const createAccountForm = reactive({
  login_id: '',
  zone: '樱之华'
})

// 通过 API 持久化抓取后建号配置
const loadPostPullSettings = async () => {
  try {
    const response = await apiRequest('/api/system/settings')
    if (response.ok) {
      const data = await response.json()
      if (data.pull_post_mode) postPullMode.value = data.pull_post_mode
      if (data.pull_default_zone) defaultZone.value = data.pull_default_zone
    }
  } catch (e) {
    console.warn('加载抓取后建号配置失败:', e)
  }
}

const savePostPullSettings = async () => {
  try {
    await apiRequest('/api/system/settings', {
      method: 'PUT',
      body: JSON.stringify({
        pull_post_mode: postPullMode.value,
        pull_default_zone: defaultZone.value
      })
    })
  } catch (e) {
    console.warn('保存抓取后建号配置失败:', e)
  }
}

// 获取模拟器列表
const fetchEmulators = async () => {
  try {
    const response = await apiRequest(API_ENDPOINTS.emulators)
    const data = await response.json()
    emulators.value = data
  } catch (error) {
    console.error('获取模拟器列表失败:', error)
    ElMessage.error('获取模拟器列表失败')
  }
}

// 获取已抓取账号列表
const fetchAccounts = async () => {
  try {
    const response = await apiRequest(`/api/account-pull/list/${listType.value}`)
    const data = await response.json()
    accounts.value = data
  } catch (error) {
    console.error('获取账号列表失败:', error)
    ElMessage.error('获取账号列表失败')
  }
}

// 静默创建游戏账号（不触发 axios 自动错误提示）
const tryCreateAccountSilent = async (loginId, zone) => {
  const response = await apiRequest('/api/accounts/game', {
    method: 'POST',
    body: JSON.stringify({ login_id: loginId, zone, level: 1, stamina: 0 })
  })
  if (response.ok) {
    return 'created'
  }
  const data = await response.json()
  if (response.status === 400 && (data.detail || '').includes('已存在')) {
    return 'exists'
  }
  throw new Error(data.detail || '创建账号失败')
}

// 抓取后建号逻辑
const handlePostPullAction = async (accountId) => {
  if (postPullMode.value === 'none') return

  if (postPullMode.value === 'auto') {
    try {
      const result = await tryCreateAccountSilent(accountId, defaultZone.value)
      if (result === 'created') {
        ElMessage.success(`游戏账号 ${accountId} 已自动创建（${defaultZone.value}）`)
      }
    } catch (error) {
      console.error('自动创建账号失败:', error)
      ElMessage.warning(`自动创建账号失败: ${error.message}`)
    }
    return
  }

  if (postPullMode.value === 'confirm') {
    createAccountForm.login_id = accountId
    createAccountForm.zone = defaultZone.value
    createAccountDialogVisible.value = true
  }
}

// 确认对话框中点击创建
const handleConfirmCreateAccount = async () => {
  if (!createAccountForm.zone) {
    ElMessage.warning('请选择区服')
    return
  }
  creatingAccount.value = true
  try {
    const result = await tryCreateAccountSilent(createAccountForm.login_id, createAccountForm.zone)
    if (result === 'created') {
      ElMessage.success(`游戏账号 ${createAccountForm.login_id} 创建成功`)
    } else if (result === 'exists') {
      ElMessage.info(`游戏账号 ${createAccountForm.login_id} 已存在，跳过创建`)
    }
    createAccountDialogVisible.value = false
  } catch (error) {
    console.error('创建账号失败:', error)
    ElMessage.error(`创建账号失败: ${error.message}`)
  } finally {
    creatingAccount.value = false
  }
}

// 执行抓取
const handlePull = async () => {
  try {
    await formRef.value.validate()

    pulling.value = true

    const response = await apiRequest('/api/account-pull/pull', {
      method: 'POST',
      body: JSON.stringify({
        emulator_id: form.emulator_id,
        pull_type: form.pull_type,
        account_id: form.account_id
      })
    })

    const data = await response.json()

    if (response.ok && data.success) {
      ElMessage.success(data.message)
      // 刷新列表
      listType.value = form.pull_type
      await fetchAccounts()
      // 保存账号ID后清空表单
      const pulledAccountId = form.account_id
      form.account_id = ''
      // 抓取后建号
      await handlePostPullAction(pulledAccountId)
    } else {
      ElMessage.error(data.message || data.detail || '抓取失败')
    }
  } catch (error) {
    if (error !== 'cancel') {
      console.error('抓取失败:', error)
      ElMessage.error('抓取失败')
    }
  } finally {
    pulling.value = false
  }
}

// 删除账号数据
const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除账号"${row.account_id}"的数据吗？`,
      '确认删除',
      { type: 'warning' }
    )

    const response = await apiRequest(`/api/account-pull/delete/${row.pull_type}/${row.account_id}`, {
      method: 'DELETE'
    })

    if (response.ok) {
      ElMessage.success('删除成功')
      await fetchAccounts()
    } else {
      const data = await response.json()
      ElMessage.error(data.detail || '删除失败')
    }
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除失败:', error)
      ElMessage.error('删除失败')
    }
  }
}

// 删除选中模拟器中的登录数据（默认仅删 shared_prefs）
const handleDeleteLoginData = async () => {
  if (!form.emulator_id) {
    ElMessage.warning('请先选择模拟器')
    return
  }

  const selectedEmu = emulators.value.find((emu) => emu.id === form.emulator_id)
  const emuName = selectedEmu ? `${selectedEmu.name} (${selectedEmu.adb_addr})` : `${form.emulator_id}`

  try {
    await ElMessageBox.confirm(
      `确定要删除模拟器 ${emuName} 的登录数据吗？\n默认仅删除 shared_prefs，不删除 clientconfig。`,
      '确认删除登录数据',
      { type: 'warning' }
    )

    const response = await apiRequest(`/api/account-pull/device-login-data/${form.emulator_id}`, {
      method: 'DELETE'
    })
    const data = await response.json()

    if (response.ok && data.success) {
      ElMessage.success(data.message || '删除成功')
    } else {
      ElMessage.error(data.detail || data.message || '删除失败')
    }
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除登录数据失败:', error)
      ElMessage.error('删除登录数据失败')
    }
  }
}

// 上传本地登录数据到选中模拟器
const handlePushData = async () => {
  try {
    await formRef.value.validate()

    const selectedEmu = emulators.value.find((emu) => emu.id === form.emulator_id)
    const emuName = selectedEmu ? `${selectedEmu.name} (${selectedEmu.adb_addr})` : `${form.emulator_id}`

    await ElMessageBox.confirm(
      `将账号 ${form.account_id} 的本地数据上传到模拟器 ${emuName}？\n将推送 shared_prefs 与 clientconfig。`,
      '确认上传信息',
      { type: 'warning' }
    )

    pushing.value = true

    const response = await apiRequest('/api/account-pull/push', {
      method: 'POST',
      body: JSON.stringify({
        emulator_id: form.emulator_id,
        pull_type: form.pull_type,
        account_id: form.account_id
      })
    })

    const data = await response.json()

    if (response.ok && data.success) {
      ElMessage.success(data.message || '上传成功')
    } else {
      ElMessage.error(data.detail || data.message || '上传失败')
    }
  } catch (error) {
    if (error !== 'cancel') {
      console.error('上传信息失败:', error)
      ElMessage.error('上传信息失败')
    }
  } finally {
    pushing.value = false
  }
}

onMounted(() => {
  loadPostPullSettings()
  fetchEmulators()
  fetchAccounts()
})
</script>

<style scoped lang="scss">
.account-pull {
  .pull-card {
    margin-bottom: 20px;
  }

  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
}
</style>
