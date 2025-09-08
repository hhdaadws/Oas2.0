<template>
  <div class="accounts">
    <!-- 操作栏 -->
    <el-card class="action-bar">
      <el-button type="primary" @click="showAddEmailDialog">
        <el-icon><Plus /></el-icon>
        添加邮箱账号
      </el-button>
      <el-button @click="showAddGameDialog">
        <el-icon><Plus /></el-icon>
        添加ID账号
      </el-button>
      <el-button @click="fetchAccounts">
        <el-icon><Refresh /></el-icon>
        刷新
      </el-button>
    </el-card>
    
    <!-- 账号列表 -->
    <el-row :gutter="20">
      <!-- 左侧账号树 -->
      <el-col :span="8">
        <el-card class="account-tree">
          <template #header>
            <span>账号列表</span>
          </template>
          
          <el-tree
            :data="accountTree"
            :props="treeProps"
            node-key="id"
            default-expand-all
            @node-click="handleNodeClick"
          >
            <template #default="{ node, data }">
              <span class="tree-node">
                <el-icon v-if="data.type === 'email'">
                  <Message />
                </el-icon>
                <el-icon v-else>
                  <User />
                </el-icon>
                <span>{{ data.label }}</span>
                <el-tag
                  v-if="data.status"
                  :type="getStatusType(data.status)"
                  size="small"
                  class="status-tag"
                >
                  {{ getStatusText(data.status) }}
                </el-tag>
                <el-button
                  link
                  type="danger"
                  size="small"
                  style="margin-left: 8px"
                  @click.stop="deleteAccount(data)"
                >
                  <el-icon><Delete /></el-icon>
                </el-button>
              </span>
            </template>
          </el-tree>
        </el-card>
      </el-col>
      
      <!-- 右侧详情 -->
      <el-col :span="16">
        <el-card v-if="selectedAccount" class="account-detail">
          <template #header>
            <span>账号详情: {{ selectedAccount.login_id }}</span>
          </template>
          
          <!-- 基础信息 -->
          <el-descriptions :column="2" border>
            <el-descriptions-item label="Login ID">
              {{ selectedAccount.login_id }}
            </el-descriptions-item>
            <el-descriptions-item label="区服">
              {{ selectedAccount.zone }}
            </el-descriptions-item>
            <el-descriptions-item label="起号状态">
              <el-select
                v-model="selectedAccount.progress"
                size="small"
                @change="updateAccountInfo"
              >
                <el-option value="init" label="待起号" />
                <el-option value="ok" label="已完成" />
              </el-select>
            </el-descriptions-item>
            <el-descriptions-item label="等级">
              <el-input-number
                v-model="selectedAccount.level"
                :min="1"
                :max="999"
                size="small"
                @change="updateAccountInfo"
              />
            </el-descriptions-item>
            <el-descriptions-item label="体力">
              <el-input-number
                v-model="selectedAccount.stamina"
                :min="0"
                :max="9999"
                size="small"
                @change="updateAccountInfo"
              />
            </el-descriptions-item>
            <el-descriptions-item label="状态">
              <el-select
                v-model="selectedAccount.status"
                size="small"
                @change="updateAccountInfo"
              >
                <el-option :value="1" label="可执行" />
                <el-option :value="2" label="失效" />
              </el-select>
            </el-descriptions-item>
            <el-descriptions-item label="当前任务" :span="2">
              {{ selectedAccount.current_task || '无' }}
            </el-descriptions-item>
          </el-descriptions>
          
          <!-- 任务配置 -->
          <el-divider>任务配置</el-divider>
          <el-form label-width="100px">
            <el-form-item label="寄养">
              <el-switch
                v-model="taskConfig.寄养.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.寄养.enabled"
                v-model="taskConfig.寄养.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
            </el-form-item>
            <el-form-item label="委托">
              <el-switch
                v-model="taskConfig.委托.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.委托.enabled"
                v-model="taskConfig.委托.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
            </el-form-item>
            <el-form-item label="勾协">
              <el-switch
                v-model="taskConfig.勾协.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.勾协.enabled"
                v-model="taskConfig.勾协.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
            </el-form-item>
            <el-form-item label="探索突破">
              <el-switch
                v-model="taskConfig.探索突破.enabled"
                @change="updateTaskConfigData"
              />
              <el-input-number
                v-if="taskConfig.探索突破.enabled"
                v-model="taskConfig.探索突破.stamina_threshold"
                :min="100"
                :max="9999"
                placeholder="体力阈值"
                style="margin-left: 10px; width: 150px"
                @change="updateTaskConfigData"
              />
              <span v-if="taskConfig.探索突破.enabled" class="config-item">体力</span>
            </el-form-item>
            <el-form-item label="结界卡合成">
              <el-switch
                v-model="taskConfig.结界卡合成.enabled"
                @change="updateTaskConfigData"
              />
              <span v-if="taskConfig.结界卡合成.enabled" style="margin-left: 10px">
                已探索：
                <el-input-number
                  v-model="taskConfig.结界卡合成.explore_count"
                  :min="0"
                  :max="100"
                  size="small"
                  style="width: 80px; margin: 0 5px"
                  @change="updateTaskConfigData"
                />
                /40 次
              </span>
            </el-form-item>
            <el-form-item label="加好友">
              <el-switch
                v-model="taskConfig.加好友.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.加好友.enabled"
                v-model="taskConfig.加好友.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
            </el-form-item>
          </el-form>
          
          <!-- 休息配置 -->
          <el-divider>休息配置</el-divider>
          <el-form label-width="100px">
            <el-form-item label="休息模式">
              <el-radio-group
                v-model="restConfig.mode"
                @change="updateRestConfigData"
              >
                <el-radio label="random">随机（2-3小时）</el-radio>
                <el-radio label="custom">自定义</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item v-if="restConfig.mode === 'custom'" label="开始时间">
              <el-time-picker
                v-model="restConfig.start_time"
                format="HH:mm"
                value-format="HH:mm"
                placeholder="选择时间"
                @change="updateRestConfigData"
              />
            </el-form-item>
            <el-form-item v-if="restConfig.mode === 'custom'" label="持续时长">
              <el-input-number
                v-model="restConfig.duration"
                :min="1"
                :max="5"
                @change="updateRestConfigData"
              />
              小时
            </el-form-item>
          </el-form>
          
          <!-- 今日休息时段 -->
          <el-divider>今日休息时段</el-divider>
          <div class="rest-plan">
            <el-tag v-if="restPlan.start_time">
              {{ restPlan.start_time }} - {{ restPlan.end_time }}
            </el-tag>
            <span v-else>暂无休息计划</span>
          </div>
        </el-card>
        
        <el-empty v-else description="请选择一个账号查看详情" />
      </el-col>
    </el-row>
    
    <!-- 添加邮箱账号对话框 -->
    <el-dialog
      v-model="emailDialogVisible"
      title="添加邮箱账号"
      width="400px"
    >
      <el-form :model="emailForm" label-width="80px">
        <el-form-item label="邮箱" required>
          <el-input v-model="emailForm.email" placeholder="请输入邮箱" />
        </el-form-item>
        <el-form-item label="密码" required>
          <el-input
            v-model="emailForm.password"
            type="password"
            placeholder="请输入密码"
            show-password
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="emailDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleAddEmail">确定</el-button>
      </template>
    </el-dialog>
    
    <!-- 添加游戏账号对话框 -->
    <el-dialog
      v-model="gameDialogVisible"
      title="添加ID账号"
      width="400px"
    >
      <el-form :model="gameForm" label-width="80px">
        <el-form-item label="Login ID" required>
          <el-input v-model="gameForm.login_id" placeholder="请输入Login ID" />
        </el-form-item>
        <el-form-item label="区服" required>
          <el-select v-model="gameForm.zone" placeholder="请选择区服">
            <el-option label="樱之华" value="樱之华" />
            <el-option label="春之樱" value="春之樱" />
            <el-option label="两情相悦" value="两情相悦" />
            <el-option label="枫之舞" value="枫之舞" />
          </el-select>
        </el-form-item>
        <el-form-item label="等级">
          <el-input-number v-model="gameForm.level" :min="1" :max="999" />
        </el-form-item>
        <el-form-item label="体力">
          <el-input-number v-model="gameForm.stamina" :min="0" :max="9999" />
        </el-form-item>
        <el-form-item label="金币">
          <el-input-number v-model="gameForm.coin" :min="0" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="gameDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleAddGame">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import {
  getAccounts,
  createEmailAccount,
  createGameAccount,
  updateAccount,
  updateTaskConfig,
  updateRestConfig,
  getRestPlan
} from '@/api/accounts'
import { ElMessage, ElMessageBox } from 'element-plus'

// 数据
const accountTree = ref([])
const selectedAccount = ref(null)
const taskConfig = reactive({
  寄养: { enabled: true, next_time: "2020-01-01 00:00" },
  委托: { enabled: true, next_time: "2020-01-01 00:00" },
  勾协: { enabled: true, next_time: "2020-01-01 00:00" },
  探索突破: { enabled: true, stamina_threshold: 1000 },
  结界卡合成: { enabled: true, explore_count: 0 },
  加好友: { enabled: true, next_time: "2020-01-01 00:00" }
})
const restConfig = reactive({
  mode: 'random',
  start_time: '',
  duration: 2
})
const restPlan = ref({})

// 对话框
const emailDialogVisible = ref(false)
const gameDialogVisible = ref(false)
const emailForm = reactive({
  email: '',
  password: ''
})
const gameForm = reactive({
  login_id: '',
  zone: '樱之华',
  level: 1,
  stamina: 0,
  coin: 0
})

// 树形控件配置
const treeProps = {
  children: 'children',
  label: 'label'
}

// 获取账号列表
const fetchAccounts = async () => {
  try {
    const data = await getAccounts()
    accountTree.value = formatAccountTree(data)
  } catch (error) {
    ElMessage.error('获取账号列表失败')
  }
}

// 格式化账号树
const formatAccountTree = (data) => {
  return data.map(item => {
    if (item.type === 'email') {
      return {
        ...item,
        label: item.email,
        children: item.children.map(child => ({
          ...child,
          label: child.login_id
        }))
      }
    } else {
      return {
        ...item,
        label: item.login_id
      }
    }
  })
}

// 处理节点点击
const handleNodeClick = async (data) => {
  if (data.type === 'game') {
    selectedAccount.value = data
    // 加载任务配置，支持新的配置结构
    const savedConfig = data.task_config || {}
    
    // 寄养：支持next_time，默认2020年
    taskConfig.寄养 = { 
      enabled: savedConfig.寄养?.enabled ?? true,
      next_time: savedConfig.寄养?.next_time ?? "2020-01-01 00:00"
    }
    
    // 委托：支持next_time，默认2020年
    taskConfig.委托 = { 
      enabled: savedConfig.委托?.enabled ?? true,
      next_time: savedConfig.委托?.next_time ?? "2020-01-01 00:00"
    }
    
    // 勾协：支持next_time，默认2020年
    taskConfig.勾协 = { 
      enabled: savedConfig.勾协?.enabled ?? true,
      next_time: savedConfig.勾协?.next_time ?? "2020-01-01 00:00"
    }
    
    // 探索突破：支持stamina_threshold
    if (savedConfig.探索突破) {
      taskConfig.探索突破 = { 
        enabled: savedConfig.探索突破.enabled ?? true,
        stamina_threshold: savedConfig.探索突破.stamina_threshold ?? 1000
      }
    } else {
      // 兼容旧数据
      const exploreEnabled = savedConfig.探索?.enabled ?? true
      const breakthroughEnabled = savedConfig.突破?.enabled ?? true
      taskConfig.探索突破 = { 
        enabled: exploreEnabled || breakthroughEnabled,
        stamina_threshold: 1000
      }
    }
    
    // 结界卡合成：支持explore_count
    taskConfig.结界卡合成 = { 
      enabled: savedConfig.结界卡合成?.enabled ?? true,
      explore_count: savedConfig.结界卡合成?.explore_count ?? 0
    }
    
    // 加好友：支持next_time，默认2020年
    taskConfig.加好友 = { 
      enabled: savedConfig.加好友?.enabled ?? true,
      next_time: savedConfig.加好友?.next_time ?? "2020-01-01 00:00"
    }
    // 获取休息计划
    try {
      const plan = await getRestPlan(data.id)
      restPlan.value = plan
    } catch (error) {
      restPlan.value = {}
    }
  }
}

// 更新账号信息
const updateAccountInfo = async () => {
  if (!selectedAccount.value) return
  
  try {
    await updateAccount(selectedAccount.value.id, {
      status: selectedAccount.value.status,
      progress: selectedAccount.value.progress,
      level: selectedAccount.value.level,
      stamina: selectedAccount.value.stamina
    })
    
    // 更新账号树中的数据
    const updateAccountInTree = (nodes) => {
      for (const node of nodes) {
        if (node.type === 'game' && node.id === selectedAccount.value.id) {
          node.status = selectedAccount.value.status
          node.progress = selectedAccount.value.progress
          node.level = selectedAccount.value.level
          node.stamina = selectedAccount.value.stamina
          break
        }
        if (node.children) {
          updateAccountInTree(node.children)
        }
      }
    }
    updateAccountInTree(accountTree.value)
    
    ElMessage.success('账号信息已更新')
  } catch (error) {
    ElMessage.error('更新失败')
  }
}

// 更新任务配置
const updateTaskConfigData = async () => {
  if (!selectedAccount.value) return
  
  try {
    // 构建新的数据结构，包含完整的配置信息
    const configToSend = {
      寄养: { 
        enabled: taskConfig.寄养.enabled,
        next_time: taskConfig.寄养.next_time
      },
      委托: { 
        enabled: taskConfig.委托.enabled,
        next_time: taskConfig.委托.next_time
      },
      勾协: { 
        enabled: taskConfig.勾协.enabled,
        next_time: taskConfig.勾协.next_time
      },
      探索突破: { 
        enabled: taskConfig.探索突破.enabled,
        stamina_threshold: taskConfig.探索突破.stamina_threshold
      },
      结界卡合成: { 
        enabled: taskConfig.结界卡合成.enabled,
        explore_count: taskConfig.结界卡合成.explore_count
      },
      加好友: { 
        enabled: taskConfig.加好友.enabled,
        next_time: taskConfig.加好友.next_time
      }
    }
    await updateTaskConfig(selectedAccount.value.id, configToSend)
    
    // 更新本地selectedAccount数据，确保界面同步
    selectedAccount.value.task_config = configToSend
    
    // 同时更新账号树中的数据
    const updateAccountInTree = (nodes) => {
      for (const node of nodes) {
        if (node.type === 'game' && node.id === selectedAccount.value.id) {
          node.task_config = configToSend
          break
        }
        if (node.children) {
          updateAccountInTree(node.children)
        }
      }
    }
    updateAccountInTree(accountTree.value)
    
    ElMessage.success('任务配置已更新')
  } catch (error) {
    ElMessage.error('更新失败')
  }
}

// 更新休息配置
const updateRestConfigData = async () => {
  if (!selectedAccount.value) return
  
  try {
    await updateRestConfig(selectedAccount.value.id, restConfig)
    
    // 刷新休息计划
    try {
      const plan = await getRestPlan(selectedAccount.value.id)
      restPlan.value = plan
    } catch (error) {
      restPlan.value = {}
    }
    
    ElMessage.success('休息配置已更新')
  } catch (error) {
    ElMessage.error('更新失败')
  }
}

// 显示添加邮箱对话框
const showAddEmailDialog = () => {
  emailForm.email = ''
  emailForm.password = ''
  emailDialogVisible.value = true
}

// 显示添加游戏对话框
const showAddGameDialog = () => {
  gameForm.login_id = ''
  gameForm.zone = '樱之华'
  gameForm.level = 1
  gameForm.stamina = 0
  gameForm.coin = 0
  gameDialogVisible.value = true
}

// 添加邮箱账号
const handleAddEmail = async () => {
  if (!emailForm.email || !emailForm.password) {
    ElMessage.warning('请填写完整信息')
    return
  }
  
  try {
    await createEmailAccount(emailForm)
    ElMessage.success('邮箱账号添加成功，已创建起号任务')
    emailDialogVisible.value = false
    fetchAccounts()
  } catch (error) {
    ElMessage.error('添加失败')
  }
}

// 添加游戏账号
const handleAddGame = async () => {
  if (!gameForm.login_id || !gameForm.zone) {
    ElMessage.warning('请填写完整信息')
    return
  }
  
  try {
    await createGameAccount(gameForm)
    ElMessage.success('游戏账号添加成功')
    gameDialogVisible.value = false
    fetchAccounts()
  } catch (error) {
    ElMessage.error('添加失败')
  }
}

// 获取状态类型
const getStatusType = (status) => {
  return status === 1 ? 'success' : 'danger'
}

// 获取状态文本
const getStatusText = (status) => {
  return status === 1 ? '正常' : '失效'
}

// 删除账号
const deleteAccount = async (accountData) => {
  try {
    const accountType = accountData.type === 'email' ? '邮箱账号' : '游戏账号'
    const accountName = accountData.label
    
    await ElMessageBox.confirm(
      `确定要删除${accountType}"${accountName}"吗？${accountData.type === 'email' ? '这将同时删除其下的所有游戏账号。' : ''}`,
      '确认删除',
      {
        type: 'warning',
        confirmButtonText: '确定删除',
        cancelButtonText: '取消'
      }
    )
    
    let response
    if (accountData.type === 'email') {
      // 删除邮箱账号
      response = await fetch(`http://113.45.64.80:9001/api/accounts/email/${encodeURIComponent(accountData.email)}`, {
        method: 'DELETE'
      })
    } else {
      // 删除游戏账号
      response = await fetch(`http://113.45.64.80:9001/api/accounts/game/${accountData.id}`, {
        method: 'DELETE'
      })
    }
    
    if (response.ok) {
      ElMessage.success(`${accountType}删除成功`)
      await fetchAccounts()  // 刷新账号列表
      
      // 如果删除的是当前选中的账号，清空选中状态
      if (selectedAccount.value && 
          ((accountData.type === 'game' && selectedAccount.value.id === accountData.id) ||
           (accountData.type === 'email' && selectedAccount.value.email === accountData.email))) {
        selectedAccount.value = null
      }
    } else {
      throw new Error('删除失败')
    }
    
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

onMounted(() => {
  fetchAccounts()
})
</script>

<style scoped lang="scss">
.accounts {
  .action-bar {
    margin-bottom: 20px;
  }
  
  .account-tree {
    height: calc(100vh - 200px);
    overflow: auto;
    
    .tree-node {
      display: flex;
      align-items: center;
      gap: 5px;
      
      .status-tag {
        margin-left: auto;
      }
    }
  }
  
  .account-detail {
    height: calc(100vh - 200px);
    overflow: auto;
    
    .config-item {
      margin-left: 20px;
      color: #606266;
    }
    
    .rest-plan {
      padding: 10px 0;
    }
  }
}
</style>