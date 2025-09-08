<template>
  <div class="accounts">
    <!-- 鎿嶄綔鏍?-->
    <el-card class="action-bar">
      <el-button type="primary" @click="showAddEmailDialog">
        <el-icon><Plus /></el-icon>
        娣诲姞閭璐﹀彿
      </el-button>
      <el-button @click="showAddGameDialog">
        <el-icon><Plus /></el-icon>
        娣诲姞ID璐﹀彿
      </el-button>
      <el-button @click="fetchAccounts">
        <el-icon><Refresh /></el-icon>
        鍒锋柊
      </el-button>
      <el-button type="danger" plain :disabled="selectedGameIds.length === 0" @click="handleBatchDelete">
        鎵归噺鍒犻櫎
      </el-button>
    </el-card>
    
    <!-- 璐﹀彿鍒楄〃 -->
    <el-row :gutter="20">
      <!-- 宸︿晶璐﹀彿鏍?-->
      <el-col :span="8">
        <el-card class="account-tree">
          <template #header>
            <div class="tree-header">
              <span>璐﹀彿鍒楄〃</span>
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
                  confirm-button-text="鍒犻櫎"
                  confirm-button-type="danger"
                  cancel-button-text="鍙栨秷"
                  title="鍒犻櫎璇ラ偖绠卞強鍏朵笅鎵€鏈塈D璐﹀彿锛熸鎿嶄綔涓嶅彲鎭㈠"
                  @confirm="() => handleDeleteEmail(data.email)"
                >
                  <template #reference>
                    <el-button link type="danger" size="small">鍒犻櫎</el-button>
                  </template>
                </el-popconfirm>
                <el-popconfirm
                  v-else
                  width="220"
                  confirm-button-text="鍒犻櫎"
                  confirm-button-type="danger"
                  cancel-button-text="鍙栨秷"
                  title="鍒犻櫎璇D璐﹀彿锛熸鎿嶄綔涓嶅彲鎭㈠"
                  @confirm="() => handleDeleteGame(data.id)"
                >
                  <template #reference>
                    <el-button link type="danger" size="small">鍒犻櫎</el-button>
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
            <span>璐﹀彿璇︽儏: {{ selectedAccount.login_id }}</span>
          </template>
          
          <!-- 鍩虹淇℃伅 -->
          <el-descriptions :column="2" border>
            <el-descriptions-item label="Login ID">
              {{ selectedAccount.login_id }}
            </el-descriptions-item>
            <el-descriptions-item label="鍖烘湇">
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
            <el-descriptions-item label="绛夌骇">
              <el-input-number
                v-model="selectedAccount.level"
                :min="1"
                :max="999"
                size="small"
                @change="updateAccountInfo"
              />
            </el-descriptions-item>
            <el-descriptions-item label="浣撳姏">
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
            <el-descriptions-item label="褰撳墠浠诲姟" :span="2">
              {{ selectedAccount.current_task || '鏃? }}
            </el-descriptions-item>
          </el-descriptions>
          
          <!-- 浠诲姟閰嶇疆 -->
          <el-divider>浠诲姟閰嶇疆</el-divider>
          <el-form label-width="100px">
            <el-form-item label="瀵勫吇">
              <el-switch
                v-model="taskConfig.瀵勫吇.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.瀵勫吇.enabled"
                v-model="taskConfig.瀵勫吇.next_time"
                type="datetime"
                placeholder="涓嬫鎵ц鏃堕棿"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
            </el-form-item>
            <el-form-item label="濮旀墭">
              <el-switch
                v-model="taskConfig.濮旀墭.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.濮旀墭.enabled"
                v-model="taskConfig.濮旀墭.next_time"
                type="datetime"
                placeholder="涓嬫鎵ц鏃堕棿"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
            </el-form-item>
            <el-form-item label="鍕惧崗">
              <el-switch
                v-model="taskConfig.鍕惧崗.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.鍕惧崗.enabled"
                v-model="taskConfig.鍕惧崗.next_time"
                type="datetime"
                placeholder="涓嬫鎵ц鏃堕棿"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
            </el-form-item>
            <el-form-item label="鎺㈢储绐佺牬">
              <el-switch
                v-model="taskConfig.鎺㈢储绐佺牬.enabled"
                @change="updateTaskConfigData"
              />
              <el-input-number
                v-if="taskConfig.鎺㈢储绐佺牬.enabled"
                v-model="taskConfig.鎺㈢储绐佺牬.stamina_threshold"
                :min="100"
                :max="9999"
                placeholder="浣撳姏闃堝€?
                style="margin-left: 10px; width: 150px"
                @change="updateTaskConfigData"
              />
              <span v-if="taskConfig.鎺㈢储绐佺牬.enabled" class="config-item">浣撳姏</span>
            </el-form-item>
            <el-form-item label="缁撶晫鍗″悎鎴?>
              <el-switch
                v-model="taskConfig.缁撶晫鍗″悎鎴?enabled"
                @change="updateTaskConfigData"
              />
              <span v-if="taskConfig.缁撶晫鍗″悎鎴?enabled" style="margin-left: 10px">
                宸叉帰绱細
                <el-input-number
                  v-model="taskConfig.缁撶晫鍗″悎鎴?explore_count"
                  :min="0"
                  :max="100"
                  size="small"
                  style="width: 80px; margin: 0 5px"
                  @change="updateTaskConfigData"
                />
                /40 娆?
              </span>
            </el-form-item>
            <el-form-item label="鍔犲ソ鍙?>
              <el-switch
                v-model="taskConfig.鍔犲ソ鍙?enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.鍔犲ソ鍙?enabled"
                v-model="taskConfig.鍔犲ソ鍙?next_time"
                type="datetime"
                placeholder="涓嬫鎵ц鏃堕棿"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
            </el-form-item>
          </el-form>
          
          <!-- 浼戞伅閰嶇疆 -->
          <el-divider>浼戞伅閰嶇疆</el-divider>
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
        
        <el-empty v-else description="璇烽€夋嫨涓€涓处鍙锋煡鐪嬭鎯? />
      </el-col>
    </el-row>
    
    <!-- 娣诲姞閭璐﹀彿瀵硅瘽妗?-->
    <el-dialog
      v-model="emailDialogVisible"
      title="娣诲姞閭璐﹀彿"
      width="400px"
    >
      <el-form :model="emailForm" label-width="80px">
        <el-form-item label="閭" required>
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
        <el-button @click="emailDialogVisible = false">鍙栨秷</el-button>
        <el-button type="primary" @click="handleAddEmail">纭畾</el-button>
      </template>
    </el-dialog>
    
    <!-- 娣诲姞娓告垙璐﹀彿瀵硅瘽妗?-->
    <el-dialog
      v-model="gameDialogVisible"
      title="娣诲姞ID璐﹀彿"
      width="400px"
    >
      <el-form :model="gameForm" label-width="80px">
        <el-form-item label="Login ID" required>
          <el-input v-model="gameForm.login_id" placeholder="璇疯緭鍏ogin ID" />
        </el-form-item>
        <el-form-item label="鍖烘湇" required>
          <el-select v-model="gameForm.zone" placeholder="璇烽€夋嫨鍖烘湇">
            <el-option label="妯变箣鍗? value="妯变箣鍗? />
            <el-option label="鏄ヤ箣妯? value="鏄ヤ箣妯? />
            <el-option label="涓ゆ儏鐩告偊" value="涓ゆ儏鐩告偊" />
            <el-option label="鏋箣鑸? value="鏋箣鑸? />
          </el-select>
        </el-form-item>
        <el-form-item label="绛夌骇">
          <el-input-number v-model="gameForm.level" :min="1" :max="999" />
        </el-form-item>
        <el-form-item label="浣撳姏">
          <el-input-number v-model="gameForm.stamina" :min="0" :max="9999" />
        </el-form-item>
        
      </el-form>
      <template #footer>
        <el-button @click="gameDialogVisible = false">鍙栨秷</el-button>
        <el-button type="primary" @click="handleAddGame">纭畾</el-button>
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
  瀵勫吇: { enabled: true, next_time: "2020-01-01 00:00" },
  濮旀墭: { enabled: true, next_time: "2020-01-01 00:00" },
  鍕惧崗: { enabled: true, next_time: "2020-01-01 00:00" },
  鎺㈢储绐佺牬: { enabled: true, stamina_threshold: 1000 },
  缁撶晫鍗″悎鎴? { enabled: true, explore_count: 0 },
  鍔犲ソ鍙? { enabled: true, next_time: "2020-01-01 00:00" }
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
  zone: '妯变箣鍗?,
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

// 鑾峰彇璐﹀彿鍒楄〃
const fetchAccounts = async () => {
  try {
    const data = await getAccounts()
    accountTree.value = formatAccountTree(data)
  } catch (error) {
    ElMessage.error('鑾峰彇璐﹀彿鍒楄〃澶辫触')
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

// 鎵归噺鍒犻櫎
const handleBatchDelete = async () => {
  if (!selectedGameIds.value.length) return
  try {
    await ElMessageBox.confirm(`纭鍒犻櫎閫変腑鐨?${selectedGameIds.value.length} 涓处鍙凤紵姝ゆ搷浣滀笉鍙仮澶峘, '鎻愮ず', {
      confirmButtonText: '鍒犻櫎',
      cancelButtonText: '鍙栨秷',
      type: 'warning'
    })
  } catch {
    return
  }

  try {
    await deleteGameAccounts(selectedGameIds.value)
    ElMessage.success('鎵归噺鍒犻櫎鎴愬姛')
    if (accountTreeRef.value) accountTreeRef.value.setCheckedKeys([])
    selectedGameIds.value = []
    selectedAccount.value = null
    restPlan.value = {}
    await fetchAccounts()
  } catch (e) {
    ElMessage.error('鎵归噺鍒犻櫎澶辫触')
  }
}

// 澶勭悊鑺傜偣鐐瑰嚮
const handleNodeClick = async (data) => {
  if (data.type === 'game') {
    selectedAccount.value = data
    // 鍔犺浇浠诲姟閰嶇疆锛屾敮鎸佹柊鐨勯厤缃粨鏋?
    const savedConfig = data.task_config || {}
    
    // 瀵勫吇锛氭敮鎸乶ext_time锛岄粯璁?020骞?
    taskConfig.瀵勫吇 = { 
      enabled: savedConfig.瀵勫吇?.enabled ?? true,
      next_time: savedConfig.瀵勫吇?.next_time ?? "2020-01-01 00:00"
    }
    
    // 濮旀墭锛氭敮鎸乶ext_time锛岄粯璁?020骞?
    taskConfig.濮旀墭 = { 
      enabled: savedConfig.濮旀墭?.enabled ?? true,
      next_time: savedConfig.濮旀墭?.next_time ?? "2020-01-01 00:00"
    }
    
    // 鍕惧崗锛氭敮鎸乶ext_time锛岄粯璁?020骞?
    taskConfig.鍕惧崗 = { 
      enabled: savedConfig.鍕惧崗?.enabled ?? true,
      next_time: savedConfig.鍕惧崗?.next_time ?? "2020-01-01 00:00"
    }
    
    // 鎺㈢储绐佺牬锛氭敮鎸乻tamina_threshold
    if (savedConfig.鎺㈢储绐佺牬) {
      taskConfig.鎺㈢储绐佺牬 = { 
        enabled: savedConfig.鎺㈢储绐佺牬.enabled ?? true,
        stamina_threshold: savedConfig.鎺㈢储绐佺牬.stamina_threshold ?? 1000
      }
    } else {
      // 鍏煎鏃ф暟鎹?
      const exploreEnabled = savedConfig.鎺㈢储?.enabled ?? true
      const breakthroughEnabled = savedConfig.绐佺牬?.enabled ?? true
      taskConfig.鎺㈢储绐佺牬 = { 
        enabled: exploreEnabled || breakthroughEnabled,
        stamina_threshold: 1000
      }
    }
    
    // 缁撶晫鍗″悎鎴愶細鏀寔explore_count
    taskConfig.缁撶晫鍗″悎鎴?= { 
      enabled: savedConfig.缁撶晫鍗″悎鎴?.enabled ?? true,
      explore_count: savedConfig.缁撶晫鍗″悎鎴?.explore_count ?? 0
    }
    
    // 鍔犲ソ鍙嬶細鏀寔next_time锛岄粯璁?020骞?
    taskConfig.鍔犲ソ鍙?= { 
      enabled: savedConfig.鍔犲ソ鍙?.enabled ?? true,
      next_time: savedConfig.鍔犲ソ鍙?.next_time ?? "2020-01-01 00:00"
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

// 鏇存柊璐﹀彿淇℃伅
const updateAccountInfo = async () => {
  if (!selectedAccount.value) return
  
  try {
    await updateAccount(selectedAccount.value.id, {
      status: selectedAccount.value.status,
      progress: selectedAccount.value.progress,
      level: selectedAccount.value.level,
      stamina: selectedAccount.value.stamina
    })
    
    // 鏇存柊璐﹀彿鏍戜腑鐨勬暟鎹?
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
    
    ElMessage.success('璐﹀彿淇℃伅宸叉洿鏂?)
  } catch (error) {
    ElMessage.error('鏇存柊澶辫触')
  }
}

// 鏇存柊浠诲姟閰嶇疆
const updateTaskConfigData = async () => {
  if (!selectedAccount.value) return
  
  try {
    // 鏋勫缓鏂扮殑鏁版嵁缁撴瀯锛屽寘鍚畬鏁寸殑閰嶇疆淇℃伅
    const configToSend = {
      瀵勫吇: { 
        enabled: taskConfig.瀵勫吇.enabled,
        next_time: taskConfig.瀵勫吇.next_time
      },
      濮旀墭: { 
        enabled: taskConfig.濮旀墭.enabled,
        next_time: taskConfig.濮旀墭.next_time
      },
      鍕惧崗: { 
        enabled: taskConfig.鍕惧崗.enabled,
        next_time: taskConfig.鍕惧崗.next_time
      },
      鎺㈢储绐佺牬: { 
        enabled: taskConfig.鎺㈢储绐佺牬.enabled,
        stamina_threshold: taskConfig.鎺㈢储绐佺牬.stamina_threshold
      },
      缁撶晫鍗″悎鎴? { 
        enabled: taskConfig.缁撶晫鍗″悎鎴?enabled,
        explore_count: taskConfig.缁撶晫鍗″悎鎴?explore_count
      },
      鍔犲ソ鍙? { 
        enabled: taskConfig.鍔犲ソ鍙?enabled,
        next_time: taskConfig.鍔犲ソ鍙?next_time
      }
    }
    await updateTaskConfig(selectedAccount.value.id, configToSend)
    
    // 鏇存柊鏈湴selectedAccount鏁版嵁锛岀‘淇濈晫闈㈠悓姝?
    selectedAccount.value.task_config = configToSend
    
    // 鍚屾椂鏇存柊璐﹀彿鏍戜腑鐨勬暟鎹?
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
    
    ElMessage.success('浠诲姟閰嶇疆宸叉洿鏂?)
  } catch (error) {
    ElMessage.error('鏇存柊澶辫触')
  }
}

// 鏇存柊浼戞伅閰嶇疆
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
    
    ElMessage.success('浼戞伅閰嶇疆宸叉洿鏂?)
  } catch (error) {
    ElMessage.error('鏇存柊澶辫触')
  }
}

// 鏄剧ず娣诲姞閭瀵硅瘽妗?
const showAddEmailDialog = () => {
  emailForm.email = ''
  emailForm.password = ''
  emailDialogVisible.value = true
}

// 鏄剧ず娣诲姞娓告垙瀵硅瘽妗?
const showAddGameDialog = () => {
  gameForm.login_id = ''
  gameForm.zone = '妯变箣鍗?
  gameForm.level = 1
  gameForm.stamina = 0
  
  gameDialogVisible.value = true
}

// 娣诲姞閭璐﹀彿
const handleAddEmail = async () => {
  if (!emailForm.email || !emailForm.password) {
    ElMessage.warning('璇峰～鍐欏畬鏁翠俊鎭?)
    return
  }
  
  try {
    await createEmailAccount(emailForm)
    ElMessage.success('閭璐﹀彿娣诲姞鎴愬姛锛屽凡鍒涘缓璧峰彿浠诲姟')
    emailDialogVisible.value = false
    fetchAccounts()
  } catch (error) {
    ElMessage.error('娣诲姞澶辫触')
  }
}

// 娣诲姞娓告垙璐﹀彿
const handleAddGame = async () => {
  if (!gameForm.login_id || !gameForm.zone) {
    ElMessage.warning('璇峰～鍐欏畬鏁翠俊鎭?)
    return
  }
  
  try {
    await createGameAccount(gameForm)
    ElMessage.success('娓告垙璐﹀彿娣诲姞鎴愬姛')
    gameDialogVisible.value = false
    fetchAccounts()
  } catch (error) {
    ElMessage.error('娣诲姞澶辫触')
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

// 鍒犻櫎閭璐﹀彿
const handleDeleteEmail = async (email) => {
  try {
    await deleteEmailAccount(email)
    ElMessage.success('閭鍙婂叾ID璐﹀彿宸插垹闄?)
    selectedAccount.value = null
    restPlan.value = {}
    await fetchAccounts()
  } catch (e) {
    ElMessage.error('鍒犻櫎澶辫触')
  }
}

// 鍒犻櫎娓告垙璐﹀彿
const handleDeleteGame = async (id) => {
  try {
    await deleteGameAccount(id)
    ElMessage.success('璐﹀彿宸插垹闄?)
    if (selectedAccount.value && selectedAccount.value.id === id) {
      selectedAccount.value = null
      restPlan.value = {}
    }
    await fetchAccounts()
  } catch (e) {
    ElMessage.error('鍒犻櫎澶辫触')
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
