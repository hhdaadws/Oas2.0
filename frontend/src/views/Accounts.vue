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
      <el-button type="danger" plain :disabled="selectedGameIds.length === 0" @click="handleBatchDelete">
        批量删除
      </el-button>
    </el-card>

    <!-- 账号列表 -->
    <el-row :gutter="20">
      <!-- 左侧账号树 -->
      <el-col :span="8">
        <el-card class="account-tree">
          <template #header>
            <div class="tree-header">
              <span>账号列表</span>
              <div style="display: flex; gap: 8px; align-items: center;">
                <el-select
                  v-model="statusFilter"
                  placeholder="状态"
                  clearable
                  size="small"
                  style="width: 100px"
                >
                  <el-option label="正常" :value="1" />
                  <el-option label="失效" :value="2" />
                </el-select>
                <el-input
                  v-model="searchText"
                  placeholder="搜索 账号ID/备注"
                  clearable
                  size="small"
                  style="max-width: 220px"
                />
              </div>
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
                <el-tag
                  v-if="data.type === 'game' && data.remark"
                  type="info"
                  size="small"
                  class="remark-tag"
                  :title="data.remark"
                >
                  {{ data.remark.length > 6 ? data.remark.substring(0, 6) + '...' : data.remark }}
                </el-tag>
                <el-popconfirm
                  v-if="data.type === 'email'"
                  width="260"
                  confirm-button-text="删除"
                  confirm-button-type="danger"
                  cancel-button-text="取消"
                  title="删除该邮箱及其下所有ID账号？此操作不可恢复"
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
                  title="删除该ID账号？此操作不可恢复"
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

      <!-- 右侧详情 -->
      <el-col :span="16">
        <el-card v-if="selectedAccount" class="account-detail">
          <template #header>
            <div style="display: flex; align-items: center; justify-content: space-between;">
              <span>账号详情: {{ selectedAccount.login_id }}</span>
              <el-button type="primary" size="small" @click="openLineupDialog">
                配置阵容
              </el-button>
            </div>
          </template>

          <!-- 基础信息 -->
          <el-descriptions :column="2" border>
            <el-descriptions-item label="账号ID">
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
                :max="99999"
                size="small"
                @change="updateAccountInfo"
              />
            </el-descriptions-item>
            <el-descriptions-item label="勾玉">
              {{ selectedAccount.gouyu || 0 }}
            </el-descriptions-item>
            <el-descriptions-item label="蓝票">
              {{ selectedAccount.lanpiao || 0 }}
            </el-descriptions-item>
            <el-descriptions-item label="金币">
              {{ selectedAccount.gold || 0 }}
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
            <el-descriptions-item label="备注" :span="2">
              <el-input
                v-model="selectedAccount.remark"
                placeholder="输入备注信息"
                size="small"
                clearable
                maxlength="500"
                show-word-limit
                @change="updateAccountInfo"
              />
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
            <el-form-item label="弥助">
              <el-switch
                v-model="taskConfig.弥助.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.弥助.enabled"
                v-model="taskConfig.弥助.next_time"
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
                :max="99999"
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
            <el-form-item label="领取登录礼包">
              <el-switch
                v-model="taskConfig.领取登录礼包.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.领取登录礼包.enabled"
                v-model="taskConfig.领取登录礼包.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
            </el-form-item>
            <el-form-item label="领取邮件">
              <el-switch
                v-model="taskConfig.领取邮件.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.领取邮件.enabled"
                v-model="taskConfig.领取邮件.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
            </el-form-item>
            <el-form-item label="爬塔">
              <el-switch
                v-model="taskConfig.爬塔.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.爬塔.enabled"
                v-model="taskConfig.爬塔.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
            </el-form-item>
            <el-form-item label="逢魔">
              <el-switch
                v-model="taskConfig.逢魔.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.逢魔.enabled"
                v-model="taskConfig.逢魔.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
            </el-form-item>
            <el-form-item label="地鬼">
              <el-switch
                v-model="taskConfig.地鬼.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.地鬼.enabled"
                v-model="taskConfig.地鬼.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
            </el-form-item>
            <el-form-item label="道馆">
              <el-switch
                v-model="taskConfig.道馆.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.道馆.enabled"
                v-model="taskConfig.道馆.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
            </el-form-item>
            <el-form-item label="寮商店">
              <el-switch
                v-model="taskConfig.寮商店.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.寮商店.enabled"
                v-model="taskConfig.寮商店.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
            </el-form-item>
            <el-form-item label="领取寮金币">
              <el-switch
                v-model="taskConfig.领取寮金币.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.领取寮金币.enabled"
                v-model="taskConfig.领取寮金币.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
            </el-form-item>
            <el-form-item label="每日一抽">
              <el-switch
                v-model="taskConfig.每日一抽.enabled"
                @change="updateTaskConfigData"
              />
              <el-date-picker
                v-if="taskConfig.每日一抽.enabled"
                v-model="taskConfig.每日一抽.next_time"
                type="datetime"
                placeholder="下次执行时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="margin-left: 10px; width: 200px"
                @change="updateTaskConfigData"
              />
            </el-form-item>
            <el-form-item label="签到">
              <el-switch
                v-model="taskConfig.签到.enabled"
                @change="updateTaskConfigData"
              />
              <el-tag
                v-if="taskConfig.签到.enabled"
                :type="taskConfig.签到.status === '已签到' ? 'success' : 'warning'"
                style="margin-left: 10px"
              >
                {{ taskConfig.签到.status || '未签到' }}
              </el-tag>
              <span v-if="taskConfig.签到.enabled && taskConfig.签到.signed_date" class="config-item" style="margin-left: 10px;">
                {{ taskConfig.签到.signed_date }}
              </span>
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
        <el-form-item label="账号ID" required>
          <el-input v-model="gameForm.login_id" placeholder="请输入账号ID" />
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
          <el-input-number v-model="gameForm.stamina" :min="0" :max="99999" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="gameDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleAddGame">确定</el-button>
      </template>
    </el-dialog>

    <!-- 配置阵容对话框 -->
    <el-dialog
      v-model="lineupDialogVisible"
      :title="`配置阵容 - ${selectedAccount?.login_id || ''}`"
      width="500px"
    >
      <el-table :data="lineupTableData" border style="width: 100%">
        <el-table-column prop="task" label="任务" width="100" />
        <el-table-column label="分组" width="180">
          <template #default="{ row }">
            <el-select v-model="row.group" size="small" style="width: 100%">
              <el-option v-for="n in 7" :key="n" :label="`分组${n}`" :value="n" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="阵容" width="180">
          <template #default="{ row }">
            <el-select v-model="row.position" size="small" style="width: 100%">
              <el-option v-for="n in 7" :key="n" :label="`阵容${n}`" :value="n" />
            </el-select>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="lineupDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveLineupConfig">保存</el-button>
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
  deleteEmailAccount,
  deleteGameAccounts,
  getLineupConfig,
  updateLineupConfig
} from '@/api/accounts'
import { ElMessage, ElMessageBox } from 'element-plus'

// 数据
const accountTree = ref([])
const searchText = ref('')
const statusFilter = ref('')
const selectedAccount = ref(null)
const accountTreeRef = ref(null)
const selectedGameIds = ref([])
const taskConfig = reactive({
  寄养: { enabled: true, next_time: "2020-01-01 00:00" },
  委托: { enabled: true, next_time: "2020-01-01 00:00" },
  弥助: { enabled: true, next_time: "2020-01-01 00:00" },
  勾协: { enabled: true, next_time: "2020-01-01 00:00" },
  探索突破: { enabled: true, stamina_threshold: 1000 },
  结界卡合成: { enabled: true, explore_count: 0 },
  加好友: { enabled: true, next_time: "2020-01-01 00:00" },
  领取登录礼包: { enabled: true, next_time: "2020-01-01 00:00" },
  领取邮件: { enabled: true, next_time: "2020-01-01 00:00" },
  爬塔: { enabled: true, next_time: "2020-01-01 00:00" },
  逢魔: { enabled: true, next_time: "2020-01-01 00:00" },
  地鬼: { enabled: true, next_time: "2020-01-01 00:00" },
  道馆: { enabled: true, next_time: "2020-01-01 00:00" },
  寮商店: { enabled: true, next_time: "2020-01-01 00:00" },
  领取寮金币: { enabled: true, next_time: "2020-01-01 00:00" },
  每日一抽: { enabled: true, next_time: "2020-01-01 00:00" },
  签到: { enabled: false, status: '未签到', signed_date: null }
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
  stamina: 0
})

// 阵容配置
const lineupDialogVisible = ref(false)
const LINEUP_TASKS = ['逢魔', '地鬼', '探索', '结界突破', '道馆']
const lineupConfig = reactive({})
const lineupTableData = ref(LINEUP_TASKS.map(task => ({
  task,
  group: 1,
  position: 1
})))

// 树形控件配置
const treeProps = {
  children: 'children',
  label: 'label'
}

// 过滤后的树数据（按 login_id 模糊匹配 + 状态筛选）
const filteredAccountTree = computed(() => {
  const q = (searchText.value || '').trim().toLowerCase()
  const sf = statusFilter.value

  const matchNode = (node) => {
    // 状态筛选
    if (sf && node.status !== sf) return false
    // 关键字搜索
    if (q) {
      const loginMatch = String(node.login_id ?? '').toLowerCase().includes(q)
      const remarkMatch = String(node.remark ?? '').toLowerCase().includes(q)
      if (!loginMatch && !remarkMatch) return false
    }
    return true
  }

  if (!q && !sf) return accountTree.value

  const result = []
  for (const node of accountTree.value) {
    if (node.type === 'email') {
      const children = (node.children || []).filter((c) => matchNode(c))
      if (children.length > 0) {
        result.push({ ...node, children })
      }
    } else if (node.type === 'game') {
      if (matchNode(node)) {
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

// 格式化账号树
const formatAccountTree = (data) => {
  return data.map(item => {
    if (item.type === 'email') {
      return {
        ...item,
        // 为邮箱节点补一个唯一 id，避免 el-tree node-key 缺失导致勾选异常
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

// 勾选变化，收集被选中的游戏账号ID
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

// 处理节点点击
const handleNodeClick = async (data) => {
  if (data.type === 'game') {
    selectedAccount.value = data
    // 加载任务配置，支持新的配置结构
    const savedConfig = data.task_config || {}

    // 寄养：支持next_time，默认2020年
    taskConfig.寄养 = {
      enabled: savedConfig.寄养?.enabled === true,
      next_time: savedConfig.寄养?.next_time ?? "2020-01-01 00:00"
    }

    // 委托：支持next_time，默认2020年
    taskConfig.委托 = {
      enabled: savedConfig.委托?.enabled === true,
      next_time: savedConfig.委托?.next_time ?? "2020-01-01 00:00"
    }

    // 弥助：支持next_time，默认2020年
    taskConfig.弥助 = {
      enabled: savedConfig.弥助?.enabled === true,
      next_time: savedConfig.弥助?.next_time ?? "2020-01-01 00:00"
    }

    // 勾协：支持next_time，默认2020年
    taskConfig.勾协 = {
      enabled: savedConfig.勾协?.enabled === true,
      next_time: savedConfig.勾协?.next_time ?? "2020-01-01 00:00"
    }

    // 探索突破：支持stamina_threshold
    if (savedConfig.探索突破) {
      taskConfig.探索突破 = {
        enabled: savedConfig.探索突破.enabled === true,
        stamina_threshold: savedConfig.探索突破.stamina_threshold ?? 1000
      }
    } else {
      // 兼容旧数据
      const exploreEnabled = savedConfig.探索?.enabled === true
      const breakthroughEnabled = savedConfig.突破?.enabled === true
      taskConfig.探索突破 = {
        enabled: exploreEnabled || breakthroughEnabled,
        stamina_threshold: 1000
      }
    }

    // 结界卡合成：支持explore_count
    taskConfig.结界卡合成 = {
      enabled: savedConfig.结界卡合成?.enabled === true,
      explore_count: savedConfig.结界卡合成?.explore_count ?? 0
    }

    // 加好友：支持next_time，默认2020年
    taskConfig.加好友 = {
      enabled: savedConfig.加好友?.enabled === true,
      next_time: savedConfig.加好友?.next_time ?? "2020-01-01 00:00"
    }

    // 领取登录礼包：支持next_time，默认2020年
    taskConfig.领取登录礼包 = {
      enabled: savedConfig.领取登录礼包?.enabled === true,
      next_time: savedConfig.领取登录礼包?.next_time ?? "2020-01-01 00:00"
    }

    // 领取邮件：支持next_time，默认2020年
    taskConfig.领取邮件 = {
      enabled: savedConfig.领取邮件?.enabled === true,
      next_time: savedConfig.领取邮件?.next_time ?? "2020-01-01 00:00"
    }

    // 爬塔：支持next_time，默认2020年
    taskConfig.爬塔 = {
      enabled: savedConfig.爬塔?.enabled === true,
      next_time: savedConfig.爬塔?.next_time ?? "2020-01-01 00:00"
    }

    // 逢魔：支持next_time，默认2020年
    taskConfig.逢魔 = {
      enabled: savedConfig.逢魔?.enabled === true,
      next_time: savedConfig.逢魔?.next_time ?? "2020-01-01 00:00"
    }

    // 地鬼：支持next_time，默认2020年
    taskConfig.地鬼 = {
      enabled: savedConfig.地鬼?.enabled === true,
      next_time: savedConfig.地鬼?.next_time ?? "2020-01-01 00:00"
    }

    // 道馆：支持next_time，默认2020年
    taskConfig.道馆 = {
      enabled: savedConfig.道馆?.enabled === true,
      next_time: savedConfig.道馆?.next_time ?? "2020-01-01 00:00"
    }

    // 寮商店：支持next_time，默认2020年
    taskConfig.寮商店 = {
      enabled: savedConfig.寮商店?.enabled === true,
      next_time: savedConfig.寮商店?.next_time ?? "2020-01-01 00:00"
    }

    // 领取寮金币：支持next_time，默认2020年
    taskConfig.领取寮金币 = {
      enabled: savedConfig.领取寮金币?.enabled === true,
      next_time: savedConfig.领取寮金币?.next_time ?? "2020-01-01 00:00"
    }

    // 每日一抽：支持next_time，默认2020年
    taskConfig.每日一抽 = {
      enabled: savedConfig.每日一抽?.enabled === true,
      next_time: savedConfig.每日一抽?.next_time ?? "2020-01-01 00:00"
    }

    // 签到：非独立任务，默认未启用
    taskConfig.签到 = {
      enabled: savedConfig.签到?.enabled === true,
      status: savedConfig.签到?.status ?? '未签到',
      signed_date: savedConfig.签到?.signed_date ?? null
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
      stamina: selectedAccount.value.stamina,
      remark: selectedAccount.value.remark
    })

    // 更新账号树中的数据
    const updateAccountInTree = (nodes) => {
      for (const node of nodes) {
        if (node.type === 'game' && node.id === selectedAccount.value.id) {
          node.status = selectedAccount.value.status
          node.progress = selectedAccount.value.progress
          node.level = selectedAccount.value.level
          node.stamina = selectedAccount.value.stamina
          node.remark = selectedAccount.value.remark
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
// Update task config
const updateTaskConfigData = async () => {
  if (!selectedAccount.value) return

  try {
    const configToSend = {
      "寄养": {
        enabled: taskConfig["寄养"].enabled,
        next_time: taskConfig["寄养"].next_time
      },
      "委托": {
        enabled: taskConfig["委托"].enabled,
        next_time: taskConfig["委托"].next_time
      },
      "弥助": {
        enabled: taskConfig["弥助"].enabled,
        next_time: taskConfig["弥助"].next_time
      },
      "勾协": {
        enabled: taskConfig["勾协"].enabled,
        next_time: taskConfig["勾协"].next_time
      },
      "探索突破": {
        enabled: taskConfig["探索突破"].enabled,
        stamina_threshold: taskConfig["探索突破"].stamina_threshold
      },
      "结界卡合成": {
        enabled: taskConfig["结界卡合成"].enabled,
        explore_count: taskConfig["结界卡合成"].explore_count
      },
      "加好友": {
        enabled: taskConfig["加好友"].enabled,
        next_time: taskConfig["加好友"].next_time
      },
      "领取登录礼包": {
        enabled: taskConfig["领取登录礼包"].enabled,
        next_time: taskConfig["领取登录礼包"].next_time
      },
      "领取邮件": {
        enabled: taskConfig["领取邮件"].enabled,
        next_time: taskConfig["领取邮件"].next_time
      },
      "爬塔": {
        enabled: taskConfig["爬塔"].enabled,
        next_time: taskConfig["爬塔"].next_time
      },
      "逢魔": {
        enabled: taskConfig["逢魔"].enabled,
        next_time: taskConfig["逢魔"].next_time
      },
      "地鬼": {
        enabled: taskConfig["地鬼"].enabled,
        next_time: taskConfig["地鬼"].next_time
      },
      "道馆": {
        enabled: taskConfig["道馆"].enabled,
        next_time: taskConfig["道馆"].next_time
      },
      "寮商店": {
        enabled: taskConfig["寮商店"].enabled,
        next_time: taskConfig["寮商店"].next_time
      },
      "领取寮金币": {
        enabled: taskConfig["领取寮金币"].enabled,
        next_time: taskConfig["领取寮金币"].next_time
      },
      "每日一抽": {
        enabled: taskConfig["每日一抽"].enabled,
        next_time: taskConfig["每日一抽"].next_time
      },
      "签到": {
        enabled: taskConfig["签到"].enabled,
        status: taskConfig["签到"].status,
        signed_date: taskConfig["签到"].signed_date
      }
    }

    const response = await updateTaskConfig(selectedAccount.value.id, configToSend)
    const mergedConfig = response?.config || configToSend

    selectedAccount.value.task_config = mergedConfig

    const updateAccountInTree = (nodes) => {
      for (const node of nodes) {
        if (node.type === 'game' && node.id === selectedAccount.value.id) {
          node.task_config = mergedConfig
          break
        }
        if (node.children) {
          updateAccountInTree(node.children)
        }
      }
    }
    updateAccountInTree(accountTree.value)

    if (response?.message && response.message.includes('未变更')) {
      ElMessage.warning(response.message)
    } else {
      ElMessage.success(response?.message || '任务配置已更新')
    }
  } catch (error) {
    ElMessage.error('更新失败')
  }
}
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

// 删除邮箱账号
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
    ElMessage.success('账号已删除')
    if (selectedAccount.value && selectedAccount.value.id === id) {
      selectedAccount.value = null
      restPlan.value = {}
    }
    await fetchAccounts()
  } catch (e) {
    ElMessage.error('删除失败')
  }
}

// 阵容配置
const openLineupDialog = async () => {
  if (!selectedAccount.value) return
  try {
    const config = await getLineupConfig(selectedAccount.value.id)
    lineupTableData.value = LINEUP_TASKS.map(task => ({
      task,
      group: config[task]?.group ?? 1,
      position: config[task]?.position ?? 1
    }))
  } catch {
    lineupTableData.value = LINEUP_TASKS.map(task => ({
      task, group: 1, position: 1
    }))
  }
  lineupDialogVisible.value = true
}

const saveLineupConfig = async () => {
  if (!selectedAccount.value) return
  try {
    const data = {}
    for (const row of lineupTableData.value) {
      data[row.task] = { group: row.group, position: row.position }
    }
    await updateLineupConfig(selectedAccount.value.id, data)
    ElMessage.success('阵容配置已保存')
    lineupDialogVisible.value = false
  } catch {
    ElMessage.error('保存阵容配置失败')
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

      .remark-tag {
        margin-left: 4px;
        max-width: 80px;
        overflow: hidden;
        text-overflow: ellipsis;
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
