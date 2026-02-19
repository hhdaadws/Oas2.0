<template>
  <div class="role-dashboard">
    <section class="panel-card">
      <div class="panel-headline">
        <h3>下属用户列表</h3>
        <el-button type="warning" size="small" @click="showQuickCreateDialog = true">创建用户</el-button>
      </div>
      <div class="filter-row" style="margin-bottom:12px">
        <el-input v-model="filters.keyword" placeholder="搜索账号" clearable />
        <el-select v-model="filters.status" clearable placeholder="状态过滤">
          <el-option label="活跃" value="active" />
          <el-option label="已过期" value="expired" />
          <el-option label="已禁用" value="disabled" />
        </el-select>
        <el-select v-model="filters.userType" clearable placeholder="类型过滤">
          <el-option v-for="item in userTypeOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
      </div>

      <div class="stats-grid">
        <div class="stat-item">
          <span class="stat-label">总数</span>
          <strong class="stat-value">{{ userSummary.total }}</strong>
        </div>
        <div class="stat-item">
          <span class="stat-label">活跃</span>
          <strong class="stat-value">{{ userSummary.active }}</strong>
        </div>
        <div class="stat-item">
          <span class="stat-label">已过期</span>
          <strong class="stat-value">{{ userSummary.expired }}</strong>
        </div>
        <div class="stat-item">
          <span class="stat-label">已禁用</span>
          <strong class="stat-value">{{ userSummary.disabled }}</strong>
        </div>
        <div class="stat-item">
          <span class="stat-label">日常</span>
          <strong class="stat-value">{{ userSummary.daily }}</strong>
        </div>
        <div class="stat-item">
          <span class="stat-label">对弈竞猜</span>
          <strong class="stat-value">{{ userSummary.duiyi }}</strong>
        </div>
        <div class="stat-item">
          <span class="stat-label">刷卡</span>
          <strong class="stat-value">{{ userSummary.shuaka }}</strong>
        </div>
      </div>

      <TableSkeleton v-if="users.length === 0 && loading.users" :rows="5" :columns="5" />

      <div v-else class="data-table-wrapper">
        <el-table
          ref="userTableRef"
          v-loading="loading.users"
          :data="users"
          border
          stripe
          row-key="id"
          empty-text="暂无下属数据"
          @selection-change="onSelectionChange"
        >
          <el-table-column type="selection" width="45" />
          <el-table-column prop="id" label="ID" width="80" sortable />
          <el-table-column label="账号" min-width="180">
            <template #default="scope">
              <span class="clickable-cell" @click="copyAccountNo(scope.row.account_no)" title="点击复制">{{ scope.row.account_no }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="login_id" label="游戏ID" min-width="130">
            <template #default="scope">
              <span class="muted" style="font-size:12px">{{ scope.row.login_id || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="account_status" label="游戏状态" width="100">
            <template #default="scope">
              <el-tag v-if="scope.row.account_status === 'active'" type="success" size="small">正常</el-tag>
              <el-tag v-else-if="scope.row.account_status === 'invalid'" type="danger" size="small">异常</el-tag>
              <el-tag v-else-if="scope.row.account_status === 'cangbaoge'" type="warning" size="small">藏宝阁</el-tag>
              <el-tag v-else type="info" size="small">-</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="user_type" label="类型" width="120">
            <template #default="scope">
              <el-tag type="info">{{ userTypeLabel(scope.row.user_type) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="120" sortable>
            <template #default="scope">
              <el-tag :type="statusTagType(scope.row.status)">{{ statusLabel(scope.row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="current_task" label="当前任务" width="120">
            <template #default="scope">
              <span class="muted" style="font-size:12px">{{ scope.row.current_task || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="到期时间" min-width="190" sortable>
            <template #default="scope">{{ formatTime(scope.row.expires_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="160">
            <template #default="scope">
              <el-button type="primary" plain size="small" @click="selectUser(scope.row)">详情</el-button>
              <el-button plain size="small" @click="openDrawer(scope.row)">扩展配置</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :total="pagination.total"
          :page-sizes="[50, 100, 200, 500]"
          layout="total, sizes, prev, pager, next"
          @current-change="loadUsers"
          @size-change="loadUsers"
        />
      </div>

      <transition name="batch-bar">
        <BatchActionBar v-if="hasSelection" :selected-count="selectedCount" @clear="doClearSelection">
          <el-button type="primary" @click="showBatchLifecycleDialog = true">批量生命周期</el-button>
          <el-button type="success" @click="showBatchAssetsDialog = true">批量资产设置</el-button>
        </BatchActionBar>
      </transition>
    </section>

    <!-- Quick Create Dialog -->
    <el-dialog v-model="showQuickCreateDialog" title="创建下属账号" width="480px" @close="createdAccounts.value = []">
      <el-form :model="quickForm" label-width="100px">
        <el-form-item label="建号天数">
          <el-input-number v-model="quickForm.duration_days" :min="1" :max="3650" style="width:100%" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="quickForm.user_type" style="width:100%">
            <el-option v-for="item in userTypeOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="数量">
          <el-input-number v-model="quickForm.count" :min="1" :max="20" style="width:100%" />
        </el-form-item>
      </el-form>
      <template v-if="createdAccounts.length > 0">
        <div style="margin-top:12px;display:flex;justify-content:space-between;align-items:center">
          <span class="muted">已创建 {{ createdAccounts.length }} 个账号</span>
          <el-button size="small" type="primary" plain @click="copyAllAccounts">全部复制</el-button>
        </div>
        <div style="max-height:200px;overflow-y:auto;margin-top:8px;display:flex;flex-direction:column;gap:6px">
          <div v-for="(item, idx) in createdAccounts" :key="idx"
            style="display:flex;align-items:center;gap:8px;padding:6px 8px;background:var(--glass-2);border-radius:6px">
            <el-tag type="info" size="small">{{ userTypeLabel(item.user_type) }}</el-tag>
            <code style="flex:1;font-size:12px">{{ item.account_no }}</code>
            <el-button size="small" plain @click="copyAccountNo(item.account_no)">复制</el-button>
          </div>
        </div>
      </template>
      <template #footer>
        <el-button @click="showQuickCreateDialog = false">关闭</el-button>
        <el-button type="warning" :loading="loading.quickCreate" @click="quickCreateUser">{{ quickForm.count > 1 ? `批量创建 (${quickForm.count}个)` : '创建账号' }}</el-button>
      </template>
    </el-dialog>

    <!-- User Detail Dialog -->
    <el-dialog v-model="showUserDetailDialog" title="下属账号详情" width="1000px" :close-on-click-modal="false">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid var(--line-soft)">
        <strong style="font-size:15px">{{ props.selectedUserAccountNo || '-' }}</strong>
        <el-tag :type="statusTagType(props.selectedUserStatus)">{{ statusLabel(props.selectedUserStatus) }}</el-tag>
        <el-tag type="info">{{ userTypeLabel(props.selectedUserType) }}</el-tag>
        <span class="muted" style="font-size:12px;margin-left:auto">到期：{{ formatTime(props.selectedUserExpiresAt) }}</span>
      </div>

      <el-tabs>
        <el-tab-pane label="生命周期">
          <el-form :model="lifecycleForm" label-width="100px" style="margin-top:12px">
            <el-form-item label="延长天数">
              <el-input-number v-model="lifecycleForm.extend_days" :min="0" :max="3650" />
            </el-form-item>
            <el-form-item label="到期时间">
              <el-date-picker v-model="lifecycleForm.expires_at" type="datetime"
                value-format="YYYY-MM-DD HH:mm" placeholder="选择到期日期时间" style="width:210px" />
            </el-form-item>
            <el-form-item label="状态">
              <el-select v-model="lifecycleForm.status" clearable placeholder="自动判定" style="width:120px">
                <el-option label="活跃" value="active" />
                <el-option label="已过期" value="expired" />
                <el-option label="已禁用" value="disabled" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="loading.lifecycle" @click="saveUserLifecycle">更新生命周期</el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="资产">
          <div class="stats-grid" style="margin-top:12px">
            <div v-for="asset in assetFields" :key="asset.key" class="stat-item">
              <span class="stat-label">{{ asset.label }}</span>
              <el-input-number v-model="selectedUserAssets[asset.key]" :min="0" :max="99999999" controls-position="right" />
            </div>
          </div>
          <div class="row-actions" style="margin-top:12px">
            <el-button type="success" :loading="loading.saveAssets" @click="saveSelectedUserAssets">保存资产</el-button>
            <el-button plain :loading="loading.userAssets" @click="loadSelectedUserAssets">刷新</el-button>
          </div>
        </el-tab-pane>

        <el-tab-pane label="任务配置">
          <div style="margin-top:12px">
            <div class="data-table-wrapper">
              <el-table :data="taskRows" border stripe empty-text="暂无任务模板">
                <el-table-column prop="name" label="任务类型" min-width="180" />
                <el-table-column label="启用" width="100">
                  <template #default="scope">
                    <el-switch v-model="scope.row.config.enabled" />
                  </template>
                </el-table-column>
                <el-table-column label="执行时间" min-width="280">
                  <template #default="scope">
                    <div class="next-time-row">
                      <el-radio-group v-model="scope.row._nextTimeMode" size="small"
                        @change="(mode) => { if (mode === 'daily' && !isHHmmPattern(scope.row.config.next_time)) scope.row.config.next_time = '08:00'; }">
                        <el-radio-button value="daily">每日</el-radio-button>
                        <el-radio-button value="datetime">指定</el-radio-button>
                      </el-radio-group>
                      <el-time-select v-if="scope.row._nextTimeMode === 'daily'"
                        v-model="scope.row.config.next_time"
                        start="00:00" end="23:30" step="00:30"
                        placeholder="时:分" size="small" style="width:100px" />
                      <el-date-picker v-else v-model="scope.row.config.next_time"
                        type="datetime" value-format="YYYY-MM-DD HH:mm"
                        placeholder="选择日期时间" size="small" style="width:170px" />
                    </div>
                  </template>
                </el-table-column>
                <el-table-column label="失败延迟(分)" width="130">
                  <template #default="scope">
                    <el-input-number v-model="scope.row.config.fail_delay" :min="0" :max="100000" size="small" />
                  </template>
                </el-table-column>
              </el-table>
            </div>

            <el-collapse class="collapse-section">
              <el-collapse-item title="高级配置编辑（完整字段）" name="json">
                <el-input v-model="selectedTaskConfigRaw" type="textarea" :rows="10"
                  placeholder='{"签到":{"enabled":true,"next_time":"08:30"}}' />
                <el-button type="primary" plain style="margin-top:8px" @click="applyTaskConfigFromRaw">应用配置</el-button>
              </el-collapse-item>
            </el-collapse>

            <div class="row-actions" style="margin-top:12px">
              <el-button plain :loading="loading.tasks" @click="loadSelectedUserTasks">加载</el-button>
              <el-button type="primary" :loading="loading.saveTasks" @click="saveSelectedUserTasks">保存任务配置</el-button>
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>

      <template #footer>
        <el-button @click="showUserDetailDialog = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- Batch Lifecycle Dialog -->
    <el-dialog v-model="showBatchLifecycleDialog" title="批量生命周期操作" width="480px">
      <el-form :model="batchLifecycleForm" label-width="100px">
        <el-form-item label="延长天数">
          <el-input-number v-model="batchLifecycleForm.extend_days" :min="0" :max="3650" />
        </el-form-item>
        <el-form-item label="到期时间">
          <el-date-picker
            v-model="batchLifecycleForm.expires_at"
            type="datetime"
            value-format="YYYY-MM-DD HH:mm"
            placeholder="选择到期日期时间"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="batchLifecycleForm.status" clearable placeholder="不改变" style="width: 100%">
            <el-option label="活跃" value="active" />
            <el-option label="已过期" value="expired" />
            <el-option label="已禁用" value="disabled" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showBatchLifecycleDialog = false">取消</el-button>
        <el-button type="primary" :loading="loading.batchLifecycle" @click="batchExtendUsers">确认执行</el-button>
      </template>
    </el-dialog>

    <!-- Batch Assets Dialog -->
    <el-dialog v-model="showBatchAssetsDialog" title="批量资产设置" width="520px">
      <el-form label-width="100px">
        <el-form-item v-for="asset in assetFields" :key="asset.key" :label="asset.label">
          <el-input-number v-model="batchAssetsForm[asset.key]" :min="0" :max="99999999" controls-position="right" style="width: 100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showBatchAssetsDialog = false">取消</el-button>
        <el-button type="success" :loading="loading.batchAssets" @click="batchSetUserAssets">确认设置</el-button>
      </template>
    </el-dialog>

    <!-- User Detail Drawer -->
    <UserDetailDrawer
      ref="userDetailDrawerRef"
      v-model="showUserDetailDrawer"
      :token="props.token"
      :user-id="drawerUserId"
      :user-account-no="drawerUserAccountNo"
      @profile-updated="loadUsers"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { managerApi, parseApiError } from "../../lib/http";
import {
  statusTagType,
  statusLabel,
  userTypeLabel,
  formatTime,
  isHHmmPattern,
  patchSummary,
  ensureTaskConfig,
  parseTaskConfigFromRaw,
  ASSET_FIELDS,
  USER_TYPE_OPTIONS,
  copyToClipboard,
} from "../../lib/helpers";
import { usePagination } from "../../composables/usePagination";
import { useBatchSelection } from "../../composables/useBatchSelection";
import { useDebouncedFilter } from "../../composables/useDebouncedFilter";
import BatchActionBar from "../shared/BatchActionBar.vue";
import TableSkeleton from "../shared/TableSkeleton.vue";
import UserDetailDrawer from "./UserDetailDrawer.vue";

const props = defineProps({
  token: { type: String, default: "" },
  selectedUserId: { type: Number, default: 0 },
  selectedUserType: { type: String, default: "daily" },
  selectedUserAccountNo: { type: String, default: "" },
  selectedUserStatus: { type: String, default: "" },
  selectedUserExpiresAt: { type: String, default: "" },
  templateCache: { type: Object, default: () => ({}) },
  ensureTaskTemplates: { type: Function, required: true },
});

const emit = defineEmits(["user-selected"]);

const loading = reactive({
  quickCreate: false,
  users: false,
  tasks: false,
  saveTasks: false,
  lifecycle: false,
  userAssets: false,
  saveAssets: false,
  batchLifecycle: false,
  batchAssets: false,
});

const quickForm = reactive({ duration_days: 30, user_type: "daily", count: 1 });
const filters = reactive({ keyword: "", status: "", userType: "" });
const quickCreatedAccount = ref("");
const quickCreatedUserType = ref("daily");
const createdAccounts = ref([]);
const users = ref([]);
const userTableRef = ref(null);
const selectedTaskConfigRaw = ref("{}");
const taskRows = ref([]);
const userTypeOptions = ref([...USER_TYPE_OPTIONS]);
const assetFields = ASSET_FIELDS;

const showUserDetailDialog = ref(false);
const showQuickCreateDialog = ref(false);
const showBatchLifecycleDialog = ref(false);
const showBatchAssetsDialog = ref(false);
const showUserDetailDrawer = ref(false);
const drawerUserId = ref(0);
const drawerUserAccountNo = ref("");
const userDetailDrawerRef = ref(null);

const batchLifecycleForm = reactive({
  extend_days: 0,
  expires_at: "",
  status: "",
});

const batchAssetsForm = reactive({
  level: 1,
  stamina: 0,
  gouyu: 0,
  lanpiao: 0,
  gold: 0,
  gongxun: 0,
  xunzhang: 0,
  tupo_ticket: 0,
  fanhe_level: 1,
  jiuhu_level: 1,
  liao_level: 0,
});

const lifecycleForm = reactive({
  extend_days: 0,
  expires_at: "",
  status: "",
});

const selectedUserAssets = reactive({
  level: 1,
  stamina: 0,
  gouyu: 0,
  lanpiao: 0,
  gold: 0,
  gongxun: 0,
  xunzhang: 0,
  tupo_ticket: 0,
  fanhe_level: 1,
  jiuhu_level: 1,
  liao_level: 0,
});

const userSummary = reactive({
  total: 0,
  active: 0,
  expired: 0,
  disabled: 0,
  daily: 0,
  duiyi: 0,
  shuaka: 0,
});

const { pagination, updateTotal, resetPage, paginationParams } = usePagination({ defaultPageSize: 50 });
const { selectedIds, selectedCount, hasSelection, onSelectionChange, clearSelection } = useBatchSelection();

useDebouncedFilter(() => filters, loadUsers, { delay: 400, resetPage });

const currentTemplate = computed(() => {
  return (
    props.templateCache[props.selectedUserType] || {
      order: [],
      defaultConfig: {},
    }
  );
});

function doClearSelection() {
  clearSelection();
  if (userTableRef.value) {
    userTableRef.value.clearSelection();
  }
}

function buildTaskRows(config) {
  const tpl = currentTemplate.value;
  taskRows.value = tpl.order.map((name) => {
    const cfg = reactive(ensureTaskConfig(config[name]));
    return {
      name,
      config: cfg,
      _nextTimeMode: isHHmmPattern(cfg.next_time) ? "daily" : "datetime",
    };
  });
}

function stringifyTaskConfig(config) {
  selectedTaskConfigRaw.value = JSON.stringify(config || {}, null, 2);
}

function applyTaskConfigFromRaw() {
  const config = parseTaskConfigFromRaw(selectedTaskConfigRaw.value);
  buildTaskRows(config);
  ElMessage.success("已从 JSON 同步到任务表格");
}

async function quickCreateUser() {
  loading.quickCreate = true;
  createdAccounts.value = [];
  try {
    const total = Math.max(1, Math.min(20, quickForm.count || 1));
    for (let i = 0; i < total; i++) {
      const response = await managerApi.quickCreateUser(props.token, {
        duration_days: quickForm.duration_days,
        user_type: quickForm.user_type,
      });
      createdAccounts.value.push({ account_no: response.account_no || "", user_type: response.user_type || quickForm.user_type });
    }
    quickCreatedAccount.value = createdAccounts.value[0]?.account_no || "";
    quickCreatedUserType.value = createdAccounts.value[0]?.user_type || quickForm.user_type;
    ElMessage.success(total > 1 ? `已创建 ${total} 个账号` : "下属账号创建成功");
    await loadUsers();
  } catch (error) {
    ElMessage.error(parseApiError(error));
  } finally {
    loading.quickCreate = false;
  }
}

async function copyAccountNo(accountNo) {
  try {
    await copyToClipboard(accountNo);
    ElMessage.success("已复制到剪贴板");
  } catch {
    ElMessage.warning("复制失败，请手动选择");
  }
}

async function copyAllAccounts() {
  const text = createdAccounts.value.map((item) => item.account_no).join("\n");
  try {
    await copyToClipboard(text);
    ElMessage.success(`已复制 ${createdAccounts.value.length} 个账号`);
  } catch {
    ElMessage.warning("复制失败，请手动选择");
  }
}

async function loadUsers() {
  if (!props.token) return;
  loading.users = true;
  try {
    const params = {
      ...paginationParams(),
      keyword: filters.keyword || undefined,
      status: filters.status || undefined,
      user_type: filters.userType || undefined,
    };
    const response = await managerApi.listUsers(props.token, params);
    users.value = response.items || [];
    patchSummary(userSummary, response.summary, ["total", "active", "expired", "disabled", "daily", "duiyi", "shuaka"]);
    updateTotal(response.total || response.summary?.total || users.value.length);
  } catch (error) {
    ElMessage.error(parseApiError(error));
  } finally {
    loading.users = false;
  }
}

async function selectUser(row) {
  emit("user-selected", row);
  lifecycleForm.expires_at = row.expires_at || "";
  lifecycleForm.extend_days = 0;
  lifecycleForm.status = "";
  showUserDetailDialog.value = true;
  await props.ensureTaskTemplates(row.user_type || "daily", userTypeOptions);
  await Promise.all([loadSelectedUserTasks(), loadSelectedUserAssets()]);
}

function openDrawer(row) {
  drawerUserId.value = row.id;
  drawerUserAccountNo.value = row.account_no || "";
  showUserDetailDrawer.value = true;
  if (userDetailDrawerRef.value) {
    userDetailDrawerRef.value.prefillFromRow(row);
  }
}

async function loadSelectedUserTasks() {
  if (!props.selectedUserId) return;
  loading.tasks = true;
  try {
    const response = await managerApi.getUserTasks(props.token, props.selectedUserId);
    const userType = response.user_type || props.selectedUserType || "daily";
    const template = await props.ensureTaskTemplates(userType, userTypeOptions);
    const merged = {
      ...(template.defaultConfig || {}),
      ...(response.task_config || {}),
    };
    buildTaskRows(merged);
    stringifyTaskConfig(merged);
  } catch (error) {
    ElMessage.error(parseApiError(error));
  } finally {
    loading.tasks = false;
  }
}

async function saveSelectedUserTasks() {
  if (!props.selectedUserId) {
    ElMessage.warning("请先选择下属账号");
    return;
  }
  const normalizedConfig = {};
  const rows = taskRows.value;
  rows.forEach((row) => {
    normalizedConfig[row.name] = { ...row.config };
  });
  loading.saveTasks = true;
  try {
    const response = await managerApi.putUserTasks(props.token, props.selectedUserId, {
      task_config: normalizedConfig,
    });
    const savedConfig = response.task_config || normalizedConfig;
    buildTaskRows(savedConfig);
    stringifyTaskConfig(savedConfig);
    ElMessage.success("任务配置更新成功");
  } catch (error) {
    ElMessage.error(parseApiError(error));
  } finally {
    loading.saveTasks = false;
  }
}

async function loadSelectedUserAssets() {
  if (!props.selectedUserId) return;
  loading.userAssets = true;
  try {
    const response = await managerApi.getUserAssets(props.token, props.selectedUserId);
    const incoming = response.assets || {};
    Object.keys(selectedUserAssets).forEach((key) => {
      selectedUserAssets[key] = Number(incoming[key] ?? selectedUserAssets[key] ?? 0);
    });
    lifecycleForm.expires_at = response.expires_at || lifecycleForm.expires_at;
  } catch (error) {
    ElMessage.error(parseApiError(error));
  } finally {
    loading.userAssets = false;
  }
}

async function saveSelectedUserAssets() {
  if (!props.selectedUserId) return;
  loading.saveAssets = true;
  try {
    await managerApi.putUserAssets(props.token, props.selectedUserId, {
      assets: { ...selectedUserAssets },
    });
    ElMessage.success("用户资产已更新");
  } catch (error) {
    ElMessage.error(parseApiError(error));
  } finally {
    loading.saveAssets = false;
  }
}

async function saveUserLifecycle() {
  if (!props.selectedUserId) return;
  const payload = {};
  if (lifecycleForm.extend_days > 0) payload.extend_days = lifecycleForm.extend_days;
  const trimmedExpires = (lifecycleForm.expires_at || "").trim();
  if (trimmedExpires) payload.expires_at = trimmedExpires;
  if (lifecycleForm.status) payload.status = lifecycleForm.status;
  if (Object.keys(payload).length === 0) {
    ElMessage.warning("请填写到期时间、延长天数或状态");
    return;
  }
  loading.lifecycle = true;
  try {
    await managerApi.patchUserLifecycle(props.token, props.selectedUserId, payload);
    ElMessage.success("用户过期时间/状态更新成功");
    lifecycleForm.extend_days = 0;
    lifecycleForm.status = "";
    await loadUsers();
    const updatedUser = users.value.find((u) => u.id === props.selectedUserId);
    if (updatedUser) {
      emit("user-selected", updatedUser);
      lifecycleForm.expires_at = updatedUser.expires_at || "";
    }
  } catch (error) {
    ElMessage.error(parseApiError(error));
  } finally {
    loading.lifecycle = false;
  }
}

async function batchExtendUsers() {
  if (!hasSelection.value) return;
  const ids = [...selectedIds.value];
  const payload = { user_ids: ids };
  if (batchLifecycleForm.extend_days > 0) payload.extend_days = batchLifecycleForm.extend_days;
  const trimmedExpires = (batchLifecycleForm.expires_at || "").trim();
  if (trimmedExpires) payload.expires_at = trimmedExpires;
  if (batchLifecycleForm.status) payload.status = batchLifecycleForm.status;
  if (!payload.extend_days && !payload.expires_at && !payload.status) {
    ElMessage.warning("请填写至少一个生命周期字段");
    return;
  }
  loading.batchLifecycle = true;
  try {
    await managerApi.batchUserLifecycle(props.token, payload);
    ElMessage.success(`已批量更新 ${ids.length} 个用户的生命周期`);
    showBatchLifecycleDialog.value = false;
    batchLifecycleForm.extend_days = 0;
    batchLifecycleForm.expires_at = "";
    batchLifecycleForm.status = "";
    doClearSelection();
    await loadUsers();
  } catch (error) {
    ElMessage.error(parseApiError(error));
  } finally {
    loading.batchLifecycle = false;
  }
}

async function batchSetUserAssets() {
  if (!hasSelection.value) return;
  const ids = [...selectedIds.value];
  loading.batchAssets = true;
  try {
    await managerApi.batchUserAssets(props.token, {
      user_ids: ids,
      assets: { ...batchAssetsForm },
    });
    ElMessage.success(`已批量设置 ${ids.length} 个用户的资产`);
    showBatchAssetsDialog.value = false;
    doClearSelection();
  } catch (error) {
    ElMessage.error(parseApiError(error));
  } finally {
    loading.batchAssets = false;
  }
}

watch(
  () => props.token,
  async (value) => {
    if (!value) {
      users.value = [];
      taskRows.value = [];
      selectedTaskConfigRaw.value = "{}";
      return;
    }
    await props.ensureTaskTemplates("daily", userTypeOptions);
    await loadUsers();
  },
  { immediate: true },
);

onMounted(async () => {
  if (props.token) {
    await props.ensureTaskTemplates("daily", userTypeOptions);
    await loadUsers();
  }
});
</script>
