<template>
  <div class="emulators">
    <!-- 模拟器列表 -->
    <el-card>
      <template #header>
        <div class="card-header">
          <span>模拟器配置</span>
          <el-button type="primary" @click="showAddDialog">
            <el-icon><Plus /></el-icon>
            添加模拟器
          </el-button>
        </div>
      </template>
      
      <el-table :data="emulators" stripe>
        <el-table-column prop="name" label="名称" width="150" />
        <el-table-column prop="role" label="执行任务类型" width="120">
          <template #default="{ row }">
            <el-tag :type="getRoleType(row.role)">
              {{ getRoleText(row.role) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="adb_addr" label="ADB地址" width="180" />
        <el-table-column prop="instance_id" label="实例ID" width="100">
          <template #default="{ row }">
            {{ getInstanceId(row.adb_addr) }}
          </template>
        </el-table-column>
        <el-table-column prop="state" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStateType(row.state)">
              {{ getStateText(row.state) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150">
          <template #default="{ row }">
            <el-button link @click="editEmulator(row)">
              <el-icon><Edit /></el-icon>
              编辑
            </el-button>
            <el-button link type="danger" @click="deleteEmulator(row)">
              <el-icon><Delete /></el-icon>
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      
      <el-empty v-if="!emulators.length" description="暂无模拟器配置" />
    </el-card>
    
    <!-- 添加/编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? '编辑模拟器' : '添加模拟器'"
      width="500px"
    >
      <el-form :model="form" label-width="100px" :rules="rules" ref="formRef">
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入模拟器名称" />
        </el-form-item>
        <el-form-item label="执行任务类型" prop="role">
          <el-select v-model="form.role" placeholder="请选择任务类型">
            <el-option label="通用任务" value="general" />
            <el-option label="勾协专用" value="coop" />
            <el-option label="起号专用" value="init" />
          </el-select>
        </el-form-item>
        <el-form-item label="ADB端口" prop="adb_port">
          <el-input-number 
            v-model="form.adb_port" 
            :min="16384" 
            :max="16800" 
            :step="32"
            placeholder="如: 16384"
          />
          <div style="font-size: 12px; color: #909399; margin-top: 4px">
            实例ID: {{ getInstanceIdFromPort(form.adb_port) }}
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import dayjs from 'dayjs'
import { API_ENDPOINTS, apiRequest } from '@/config'

// 数据
const emulators = ref([])
const dialogVisible = ref(false)
const isEdit = ref(false)
const formRef = ref()

// 表单数据
const form = reactive({
  id: null,
  name: '',
  role: 'general',
  adb_port: 7555
})

// 表单验证规则
const rules = {
  name: [{ required: true, message: '请输入模拟器名称', trigger: 'blur' }],
  role: [{ required: true, message: '请选择任务类型', trigger: 'change' }],
  adb_port: [{ required: true, message: '请输入ADB端口', trigger: 'blur' }]
}

// 获取模拟器列表
const fetchEmulators = async () => {
  try {
    const response = await apiRequest(API_ENDPOINTS.emulators)
    const data = await response.json()
    emulators.value = data
  } catch (error) {
    console.error('API错误:', error)
    ElMessage.error('获取模拟器列表失败')
  }
}

// 端口到实例ID的计算公式
const getInstanceIdFromPort = (port) => {
  if (!port) return 0
  return Math.floor((port - 16384) / 32)  // 16384对应实例0，16416对应实例1，以此类推
}

// 从ADB地址提取实例ID
const getInstanceId = (adbAddr) => {
  if (!adbAddr) return 0
  const match = adbAddr.match(/:(\d+)$/)
  if (match) {
    const port = parseInt(match[1])
    return getInstanceIdFromPort(port)
  }
  return 0
}

// 显示添加对话框
const showAddDialog = () => {
  isEdit.value = false
  Object.assign(form, {
    id: null,
    name: '',
    role: 'general',
    adb_port: 16384
  })
  dialogVisible.value = true
}

// 编辑模拟器
const editEmulator = (emulator) => {
  isEdit.value = true
  // 从ADB地址提取端口号
  const match = emulator.adb_addr.match(/:(\d+)$/)
  const port = match ? parseInt(match[1]) : 16384
  
  Object.assign(form, {
    id: emulator.id,
    name: emulator.name,
    role: emulator.role,
    adb_port: port
  })
  dialogVisible.value = true
}

// 提交表单
const handleSubmit = async () => {
  try {
    await formRef.value.validate()
    
    const endpoint = isEdit.value 
      ? API_ENDPOINTS.emulatorUpdate(form.id)
      : API_ENDPOINTS.emulators
    
    const method = isEdit.value ? 'PUT' : 'POST'
    
    // 构建完整的ADB地址和实例ID
    const adb_addr = `127.0.0.1:${form.adb_port}`
    const instance_id = getInstanceIdFromPort(form.adb_port)
    
    const response = await apiRequest(endpoint, {
      method,
      body: JSON.stringify({
        name: form.name,
        role: form.role,
        adb_addr: adb_addr,
        instance_id: instance_id
      })
    })
    
    if (response.ok) {
      ElMessage.success(isEdit.value ? '模拟器更新成功' : '模拟器创建成功')
      dialogVisible.value = false
      await fetchEmulators()
    } else {
      throw new Error('操作失败')
    }
  } catch (error) {
    ElMessage.error('操作失败')
  }
}

// 删除模拟器
const deleteEmulator = async (emulator) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除模拟器"${emulator.name}"吗？`,
      '确认删除',
      { type: 'warning' }
    )
    
    const response = await apiRequest(API_ENDPOINTS.emulatorDelete(emulator.id), {
      method: 'DELETE'
    })
    
    if (response.ok) {
      ElMessage.success('模拟器删除成功')
      await fetchEmulators()
    } else {
      throw new Error('删除失败')
    }
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

// 格式化时间
const formatTime = (time) => {
  return dayjs(time).format('YYYY-MM-DD HH:mm:ss')
}

// 获取角色类型
const getRoleType = (role) => {
  const map = {
    'general': 'primary',
    'coop': 'warning',
    'init': 'success'
  }
  return map[role] || 'info'
}

// 获取角色文本
const getRoleText = (role) => {
  const map = {
    'general': '通用任务',
    'coop': '勾协专用',
    'init': '起号专用'
  }
  return map[role] || role
}

// 获取状态类型
const getStateType = (state) => {
  const map = {
    'running': 'success',
    'stopped': 'info',
    'error': 'danger'
  }
  return map[state] || 'info'
}

// 获取状态文本
const getStateText = (state) => {
  const map = {
    'running': '运行中',
    'stopped': '已停止',
    'error': '错误'
  }
  return map[state] || state
}

onMounted(() => {
  fetchEmulators()
})
</script>

<style scoped lang="scss">
.emulators {
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
}
</style>