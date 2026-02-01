<template>
  <div class="accounts">
    <!-- 鎿嶄綔鏍?-->
    <el-card class="action-bar">
      <el-button type="primary" @click="showAddEmailDialog">
        <el-icon><Plus /></el-icon>
        添加邮箱账号
      </el-button>
      <el-button @click="showAddGameDialog">
        <el-icon><Plus /></el-icon>
        添加ID账号
      </el-button>
      <el-button @click="fetchAccounts">
        <el-icon><Refresh /></el-icon>
        鍒锋柊
      </el-button>
      <el-button type="danger" plain :disabled="selectedGameIds.length === 0" @click="handleBatchDelete">
        批量删除
      </el-button>
    </el-card>
    
    <!-- 账号鍒楄〃 -->
    <el-row :gutter="20">
      <!-- 宸︿晶账号鏍?-->
      <el-col :span="8">
        <el-card class="account-tree">
          <template #header>
            <div class="tree-header">
              <span>账号鍒楄〃</span>
              <el-input
                v-model="searchText"
                placeholder="鎼滅储 Login ID"
                clearable
                size="small"
                style="max-width: 220px"
              />
            </div>
          </template>
          
          <el-tree
            :data="filteredAccountTree"
            :props="treeProps"
            node-key="id"
            show-checkbox
            ref="accountTreeRef"
            check-on-click-node
            default-expand-all
            @check="handleTreeCheck"
            @check-change="handleTreeCheck"
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
                <el-popconfirm
                  v-if="data.type === 'email'"
                  width="260"
                  confirm-button-text="删除"
                  confirm-button-type="danger"
                  cancel-button-text="取消"
                  title="删除璇ラ偖绠卞強鍏朵笅鎵€鏈塈D账号锛熸鎿嶄綔涓嶅彲鎭㈠"
                  @confirm="() => handleDeleteEmail(data.email)"
                >
                  <template #reference>
                    <el-button link type="danger" size="small">删除</el-button>
                  </template>
                </el-popconfirm>
                <el-popconfirm
                  v-else
                  width="220"
                  confirm-button-text="删除"
                  confirm-button-type="danger"
                  cancel-button-text="取消"
                  title="删除璇D账号锛熸鎿嶄綔涓嶅彲鎭㈠"
                  @confirm="() => handleDeleteGame(data.id)"
                >
                  <template #reference>
                    <el-button link type="danger" size="small">删除</el-button>
                  </template>
                </el-popconfirm>
              </span>
            </template>
          </el-tree>
        </el-card>
      </el-col>
      
      <!-- 鍙充晶璇︽儏 -->
      <el-col :span="16">
        <el-card v-if="selectedAccount" class="account-detail">
          <template #header>
            <span>账号璇︽儏: {{ selectedAccount.login_id }}</span>
          </template>
          
          <!-- 鍩虹信息 -->
          <el-descriptions :column="2" border>
            <el-descriptions-item label="Login ID">
              {{ selectedAccount.login_id }}
            </el-descriptions-item>
            <el-descriptions-item label="区服">
              {{ selectedAccount.zone }}
            </el-descriptions-item>
            <el-descriptions-item label="璧峰彿鐘舵€?>
              <el-select
                v-model="selectedAccount.progress"
                size="small"
                @change="updateAccountInfo"
              >
                <el-option value="init" label="寰呰捣鍙? />
                <el-option value="ok" label="宸插畬鎴? />
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
            <el-descriptions-item label="鐘舵€?>
              <el-select
                v-model="selectedAccount.status"
                size="small"
                @change="updateAccountInfo"
              >
                <el-option :value="1" label="鍙墽琛? />
                <el-option :value="2" label="澶辨晥" />
              </el-select>
            </el-descriptions-item>
            <el-descriptions-item label="当前任务" :span="2">
              {{ selectedAccount.current_task || '无 }}
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
                placeholder="涓嬫鎵ц鏃堕棿"
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
                placeholder="涓嬫鎵ц鏃堕棿"
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
                placeholder="涓嬫鎵ц鏃堕棿"
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
                placeholder="体力闃堝€?
                style="margin-left: 10px; width: 150px"
                @change="updateTaskConfigData"
              />
              <span v-if="taskConfig.探索突破.enabled" class="config-item">体力</span>
            </el-form-item>
            <el-form-item label="结界卡合成>
              <el-switch
                v-model="taskConfig.结界卡合成enabled"
                @change="updateTaskConfigData"
              />
              <span v-if="taskConfig.结界卡合成enabled" style="margin-left: 10px">
                宸叉帰绱細
                <el-input-number
                  v-model="taskConfig.结界卡合成explore_count"
                  :min="0"
                  :max="100"
                  size="small"
                  style="width: 80px; margin: 0 5px"
                  @change="updateTaskConfigData"
                />
                /40 娆?
              </span>
            </el-form-item>
            <el-form-item label="加好友>
              <el-switch
                v-model="taskConfig.加好友enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.加好友enabled"
                v-model="taskConfig.加好友next_time"
                type="datetime"
                placeholder="涓嬫鎵ц鏃堕棿"
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
            <el-form-item label="浼戞伅妯″紡">
              <el-radio-group
                v-model="restConfig.mode"
                @change="updateRestConfigData"
              >
                <el-radio label="random">闅忔満锛?-3灏忔椂锛?/el-radio>
                <el-radio label="custom">鑷畾涔?/el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item v-if="restConfig.mode === 'custom'" label="寮€濮嬫椂闂?>
              <el-time-picker
                v-model="restConfig.start_time"
                format="HH:mm"
                value-format="HH:mm"
                placeholder="閫夋嫨鏃堕棿"
                @change="updateRestConfigData"
              />
            </el-form-item>
            <el-form-item v-if="restConfig.mode === 'custom'" label="鎸佺画鏃堕暱">
              <el-input-number
                v-model="restConfig.duration"
                :min="1"
                :max="5"
                @change="updateRestConfigData"
              />
              灏忔椂
            </el-form-item>
          </el-form>
          
          <!-- 浠婃棩浼戞伅鏃舵 -->
          <el-divider>浠婃棩浼戞伅鏃舵</el-divider>
          <div class="rest-plan">
            <el-tag v-if="restPlan.start_time">
              {{ restPlan.start_time }} - {{ restPlan.end_time }}
            </el-tag>
            <span v-else>鏆傛棤浼戞伅璁″垝</span>
          </div>
        </el-card>
        
        <el-empty v-else description="请选择涓€涓处鍙锋煡鐪嬭鎯? />
      </el-col>
    </el-row>
    
    <!-- 添加邮箱账号瀵硅瘽妗?-->
    <el-dialog
      v-model="emailDialogVisible"
      title="添加邮箱账号"
      width="400px"
    >
      <el-form :model="emailForm" label-width="80px">
        <el-form-item label="邮箱" required>
          <el-input v-model="emailForm.email" placeholder="璇疯緭鍏ラ偖绠? />
        </el-form-item>
        <el-form-item label="瀵嗙爜" required>
          <el-input
            v-model="emailForm.password"
            type="password"
            placeholder="璇疯緭鍏ュ瘑鐮?
            show-password
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="emailDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleAddEmail">确畾</el-button>
      </template>
    </el-dialog>
    
    <!-- 添加游戏账号瀵硅瘽妗?-->
    <el-dialog
      v-model="gameDialogVisible"
      title="添加ID账号"
      width="400px"
    >
      <el-form :model="gameForm" label-width="80px">
        <el-form-item label="Login ID" required>
          <el-input v-model="gameForm.login_id" placeholder="璇疯緭鍏ogin ID" />
        </el-form-item>
        <el-form-item label="区服" required>
          <el-select v-model="gameForm.zone" placeholder="请选择区服">
            <el-option label="樱之卫" value="樱之卫" />
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
        
      </el-form>
      <template #footer>
        <el-button @click="gameDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleAddGame">确畾</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import {
  getAccounts,
  createEmailAccount,
  createGameAccount,
  updateAccount,
  updateTaskConfig,
  updateRestConfig,
  getRestPlan,
  deleteGameAccount,
  deleteEmailAccount
} from '@/api/accounts'
import { deleteGameAccounts } from '@/api/accounts'
import { ElMessage } from 'element-plus'
import { ElMessageBox } from 'element-plus'

// 鏁版嵁
const accountTree = ref([])
const searchText = ref('')
const selectedAccount = ref(null)
const accountTreeRef = ref(null)
const selectedGameIds = ref([])
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

// 瀵硅瘽妗?
const emailDialogVisible = ref(false)
const gameDialogVisible = ref(false)
const emailForm = reactive({
  email: '',
  password: ''
})
const gameForm = reactive({
  login_id: '',
  zone: '樱之卫',
  level: 1,
  stamina: 0,
  
})

// 鏍戝舰鎺т欢閰嶇疆
const treeProps = {
  children: 'children',
  label: 'label'
}

// 杩囨护鍚庣殑鏍戞暟鎹紙鎸?login_id 妯＄硦鍖归厤锛?
const filteredAccountTree = computed(() => {
  const q = (searchText.value || '').trim().toLowerCase()
  if (!q) return accountTree.value

  const matchLogin = (s) => String(s ?? '').toLowerCase().includes(q)

  const result = []
  for (const node of accountTree.value) {
    if (node.type === 'email') {
      const children = (node.children || []).filter((c) => matchLogin(c.login_id))
      if (children.length > 0) {
        result.push({ ...node, children })
      }
    } else if (node.type === 'game') {
      if (matchLogin(node.login_id)) {
        result.push(node)
      }
    }
  }
  return result
})

// 获取账号列表
const fetchAccounts = async () => {
  try {
    const data = await getAccounts()
    accountTree.value = formatAccountTree(data)
  } catch (error) {
    ElMessage.error('获取账号列表失败')
  }
}

// 鏍煎紡鍖栬处鍙锋爲
const formatAccountTree = (data) => {
  return data.map(item => {
    if (item.type === 'email') {
      return {
        ...item,
        // 涓洪偖绠辫妭鐐硅ˉ涓€涓敮涓€ id锛岄伩鍏?el-tree node-key 缂哄け瀵艰嚧鍕鹃€夊紓甯?
        id: `email:${item.email}`,
        label: item.email,
        children: (item.children || []).map(child => ({
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

// 鍕鹃€夊彉鍖栵紝鏀堕泦琚€変腑鐨勬父鎴忚处鍙稩D
const handleTreeCheck = () => {
  const keys = accountTreeRef.value?.getCheckedKeys(false) || []
  const ids = keys
    .map(k => (typeof k === 'string' && /^\d+$/.test(k)) ? Number(k) : k)
    .filter(k => typeof k === 'number')
  selectedGameIds.value = ids
}

// 批量删除
const handleBatchDelete = async () => {
  if (!selectedGameIds.value.length) return
  try {
    await ElMessageBox.confirm(`确认删除选中的 ${selectedGameIds.value.length} 个账号？此操作不可恢复`, '提示', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning'
    })
  } catch {
    return
  }

  try {
    await deleteGameAccounts(selectedGameIds.value)
    ElMessage.success('批量删除成功')
    if (accountTreeRef.value) accountTreeRef.value.setCheckedKeys([])
    selectedGameIds.value = []
    selectedAccount.value = null
    restPlan.value = {}
    await fetchAccounts()
  } catch (e) {
    ElMessage.error('批量删除失败')
  }
}

// 澶勭悊鑺傜偣鐐瑰嚮
const handleNodeClick = async (data) => {
  if (data.type === 'game') {
    selectedAccount.value = data
    // 鍔犺浇任务配置锛屾敮鎸佹柊鐨勯厤缃粨鏋?
    const savedConfig = data.task_config || {}
    
    // 寄养锛氭敮鎸乶ext_time锛岄粯璁?020骞?
    taskConfig.寄养 = { 
      enabled: savedConfig.寄养?.enabled ?? true,
      next_time: savedConfig.寄养?.next_time ?? "2020-01-01 00:00"
    }
    
    // 委托锛氭敮鎸乶ext_time锛岄粯璁?020骞?
    taskConfig.委托 = { 
      enabled: savedConfig.委托?.enabled ?? true,
      next_time: savedConfig.委托?.next_time ?? "2020-01-01 00:00"
    }
    
    // 勾协锛氭敮鎸乶ext_time锛岄粯璁?020骞?
    taskConfig.勾协 = { 
      enabled: savedConfig.勾协?.enabled ?? true,
      next_time: savedConfig.勾协?.next_time ?? "2020-01-01 00:00"
    }
    
    // 探索突破锛氭敮鎸乻tamina_threshold
    if (savedConfig.探索突破) {
      taskConfig.探索突破 = { 
        enabled: savedConfig.探索突破.enabled ?? true,
        stamina_threshold: savedConfig.探索突破.stamina_threshold ?? 1000
      }
    } else {
      // 鍏煎鏃ф暟鎹?
      const exploreEnabled = savedConfig.探索?.enabled ?? true
      const breakthroughEnabled = savedConfig.突破?.enabled ?? true
      taskConfig.探索突破 = { 
        enabled: exploreEnabled || breakthroughEnabled,
        stamina_threshold: 1000
      }
    }
    
    // 缁撶晫鍗″悎鎴愶細鏀寔explore_count
    taskConfig.结界卡合成= { 
      enabled: savedConfig.结界卡合成.enabled ?? true,
      explore_count: savedConfig.结界卡合成.explore_count ?? 0
    }
    
    // 鍔犲ソ鍙嬶細鏀寔next_time锛岄粯璁?020骞?
    taskConfig.加好友= { 
      enabled: savedConfig.加好友.enabled ?? true,
      next_time: savedConfig.加好友.next_time ?? "2020-01-01 00:00"
    }
    // 鑾峰彇浼戞伅璁″垝
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
    
    // 更新账号鏍戜腑鐨勬暟鎹?
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
    // 鏋勫缓鏂扮殑鏁版嵁缁撴瀯锛屽寘鍚畬鏁寸殑閰嶇疆信息
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
        enabled: taskConfig.结界卡合成enabled,
        explore_count: taskConfig.结界卡合成explore_count
      },
      加好友: { 
        enabled: taskConfig.加好友enabled,
        next_time: taskConfig.加好友next_time
      }
    }
    await updateTaskConfig(selectedAccount.value.id, configToSend)
    
    // 更新鏈湴selectedAccount鏁版嵁锛岀‘淇濈晫闈㈠悓姝?
    selectedAccount.value.task_config = configToSend
    
    // 鍚屾椂更新账号鏍戜腑鐨勬暟鎹?
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
    
    // 鍒锋柊浼戞伅璁″垝
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

// 鏄剧ず添加邮箱瀵硅瘽妗?
const showAddEmailDialog = () => {
  emailForm.email = ''
  emailForm.password = ''
  emailDialogVisible.value = true
}

// 鏄剧ず添加游戏瀵硅瘽妗?
const showAddGameDialog = () => {
  gameForm.login_id = ''
  gameForm.zone = '樱之卫'
  gameForm.level = 1
  gameForm.stamina = 0
  
  gameDialogVisible.value = true
}

// 添加邮箱账号
const handleAddEmail = async () => {
  if (!emailForm.email || !emailForm.password) {
    ElMessage.warning('璇峰～鍐欏畬鏁翠俊鎭?)
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
    ElMessage.warning('璇峰～鍐欏畬鏁翠俊鎭?)
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

// 鑾峰彇鐘舵€佺被鍨?
const getStatusType = (status) => {
  return status === 1 ? 'success' : 'danger'
}

// 鑾峰彇鐘舵€佹枃鏈?
const getStatusText = (status) => {
  return status === 1 ? '姝ｅ父' : '澶辨晥'
}

// 删除邮箱账号
const handleDeleteEmail = async (email) => {
  try {
    await deleteEmailAccount(email)
    ElMessage.success('邮箱及其ID账号已删除')
    selectedAccount.value = null
    restPlan.value = {}
    await fetchAccounts()
  } catch (e) {
    ElMessage.error('删除失败')
  }
}

// 删除游戏账号
const handleDeleteGame = async (id) => {
  try {
    await deleteGameAccount(id)
    ElMessage.success('账号已删除)
    if (selectedAccount.value && selectedAccount.value.id === id) {
      selectedAccount.value = null
      restPlan.value = {}
    }
    await fetchAccounts()
  } catch (e) {
    ElMessage.error('删除失败')
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
    
    .tree-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
    }
    
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
