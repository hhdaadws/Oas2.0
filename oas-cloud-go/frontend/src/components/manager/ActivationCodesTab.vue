<template>
  <div class="role-dashboard">
    <section class="panel-card panel-card--compact">
      <div class="panel-headline">
        <h3>激活码管理</h3>
        <div class="row-actions">
          <el-button text type="primary" :loading="loading.codes" @click="loadActivationCodes">刷新</el-button>
          <el-button type="primary" size="small" @click="showCreateDialog = true">生成激活码</el-button>
        </div>
      </div>
      <div class="filter-row" style="margin-bottom:12px">
        <el-input v-model="filters.keyword" placeholder="按激活码检索" clearable />
        <el-select v-model="filters.status" clearable placeholder="全部状态">
          <el-option label="未使用" value="unused" />
          <el-option label="已使用" value="used" />
          <el-option label="已删除" value="deleted" />
        </el-select>
        <el-select v-model="filters.user_type" clearable placeholder="全部类型">
          <el-option v-for="item in userTypeOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
      </div>

      <div class="stats-grid">
        <div class="stat-item">
          <span class="stat-label">总数</span>
          <strong class="stat-value">{{ summary.total }}</strong>
        </div>
        <div class="stat-item">
          <span class="stat-label">未使用</span>
          <strong class="stat-value">{{ summary.unused }}</strong>
        </div>
        <div class="stat-item">
          <span class="stat-label">已使用</span>
          <strong class="stat-value">{{ summary.used }}</strong>
        </div>
        <div class="stat-item">
          <span class="stat-label">已删除</span>
          <strong class="stat-value">{{ summary.deleted }}</strong>
        </div>
      </div>
    </section>

    <section class="panel-card">
      <div class="panel-headline">
        <h3>激活码列表</h3>
        <span class="muted">共 {{ pagination.total }} 条</span>
      </div>

      <TableSkeleton v-if="activationCodes.length === 0 && loading.codes" :rows="5" :columns="8" />

      <div v-else class="data-table-wrapper">
        <el-table
          ref="tableRef"
          v-loading="loading.codes"
          :data="activationCodes"
          border
          stripe
          row-key="id"
          empty-text="暂无激活码数据"
          @selection-change="onSelectionChange"
        >
          <el-table-column type="selection" width="45" :selectable="(row) => row.status === 'unused'" />
          <el-table-column prop="id" label="ID" width="80" sortable />
          <el-table-column label="激活码" min-width="220">
            <template #default="scope">
              <span class="clickable-cell" @click="copyCode(scope.row.code)" title="点击复制">{{ scope.row.code }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="user_type" label="类型" width="120">
            <template #default="scope">
              <el-tag type="info">{{ userTypeLabel(scope.row.user_type) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="duration_days" label="天数" width="100" />
          <el-table-column prop="status" label="状态" width="120" sortable>
            <template #default="scope">
              <el-tag :type="keyStatusTagType(scope.row.status)">{{ keyStatusLabel(scope.row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="used_by_account_no" label="使用账号" min-width="170" />
          <el-table-column label="使用时间" min-width="170" sortable>
            <template #default="scope">{{ formatTime(scope.row.used_at) }}</template>
          </el-table-column>
          <el-table-column label="创建时间" min-width="170" sortable>
            <template #default="scope">{{ formatTime(scope.row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="120">
            <template #default="scope">
              <el-button
                v-if="scope.row.status === 'unused'"
                type="danger"
                plain
                size="small"
                :loading="scope.row._deleting"
                @click="deleteActivationCode(scope.row)"
              >
                删除
              </el-button>
              <span v-else class="muted">-</span>
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
          @current-change="loadActivationCodes"
          @size-change="loadActivationCodes"
        />
      </div>

      <transition name="batch-bar">
        <BatchActionBar v-if="hasSelection" :selected-count="selectedCount" @clear="doClearSelection">
          <el-button type="danger" :loading="loading.batchDelete" @click="batchDelete">批量删除</el-button>
        </BatchActionBar>
      </transition>
    </section>

    <el-dialog v-model="showCreateDialog" title="生成激活码" width="440px"
      @close="latestActivationCode = ''; generatedCodes.value = []">
      <el-form :model="activationForm" label-width="100px">
        <el-form-item label="激活天数">
          <el-input-number v-model="activationForm.duration_days" :min="1" :max="3650" style="width:100%" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="activationForm.user_type" style="width:100%">
            <el-option v-for="item in userTypeOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="数量">
          <el-input-number v-model="activationForm.count" :min="1" :max="50" style="width:100%" />
        </el-form-item>
      </el-form>
      <template v-if="generatedCodes.length > 0">
        <div style="margin-top:12px;display:flex;justify-content:space-between;align-items:center">
          <span class="muted">已生成 {{ generatedCodes.length }} 个激活码</span>
          <el-button size="small" type="primary" plain @click="copyAllCodes">全部复制</el-button>
        </div>
        <div style="max-height:200px;overflow-y:auto;margin-top:8px;display:flex;flex-direction:column;gap:6px">
          <div v-for="(item, idx) in generatedCodes" :key="idx"
            style="display:flex;align-items:center;gap:8px;padding:6px 8px;background:var(--glass-2);border-radius:6px">
            <el-tag type="info" size="small">{{ userTypeLabel(item.user_type) }}</el-tag>
            <code style="flex:1;font-size:12px">{{ item.code }}</code>
            <el-button size="small" plain @click="copyCode(item.code)">复制</el-button>
          </div>
        </div>
      </template>
      <template #footer>
        <el-button @click="showCreateDialog = false">关闭</el-button>
        <el-button type="primary" :loading="loading.activation" @click="createActivationCode">{{ activationForm.count > 1 ? `批量生成 (${activationForm.count}个)` : '生成激活码' }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { managerApi, parseApiError } from "../../lib/http";
import {
  keyStatusTagType,
  keyStatusLabel,
  userTypeLabel,
  formatTime,
  patchSummary,
  USER_TYPE_OPTIONS,
  copyToClipboard,
} from "../../lib/helpers";
import { usePagination } from "../../composables/usePagination";
import { useBatchSelection } from "../../composables/useBatchSelection";
import { useDebouncedFilter } from "../../composables/useDebouncedFilter";
import BatchActionBar from "../shared/BatchActionBar.vue";
import TableSkeleton from "../shared/TableSkeleton.vue";

const props = defineProps({
  token: {
    type: String,
    default: "",
  },
});

const loading = reactive({
  activation: false,
  codes: false,
  batchDelete: false,
});

const activationForm = reactive({ duration_days: 30, user_type: "daily", count: 1 });
const filters = reactive({ keyword: "", status: "", user_type: "" });
const latestActivationCode = ref("");
const latestActivationType = ref("daily");
const generatedCodes = ref([]);
const activationCodes = ref([]);
const tableRef = ref(null);
const userTypeOptions = USER_TYPE_OPTIONS;
const showCreateDialog = ref(false);

const summary = reactive({
  total: 0,
  unused: 0,
  used: 0,
  revoked: 0,
  deleted: 0,
});

const { pagination, updateTotal, resetPage, paginationParams } = usePagination({ defaultPageSize: 50 });
const { selectedIds, selectedCount, hasSelection, onSelectionChange, clearSelection } = useBatchSelection();

useDebouncedFilter(() => filters, loadActivationCodes, { delay: 400, resetPage });

function doClearSelection() {
  clearSelection();
  if (tableRef.value) {
    tableRef.value.clearSelection();
  }
}

async function createActivationCode() {
  loading.activation = true;
  generatedCodes.value = [];
  try {
    const total = Math.max(1, Math.min(50, activationForm.count || 1));
    for (let i = 0; i < total; i++) {
      const response = await managerApi.createActivationCode(props.token, {
        duration_days: activationForm.duration_days,
        user_type: activationForm.user_type,
      });
      generatedCodes.value.push({ code: response.code || "", user_type: response.user_type || activationForm.user_type });
    }
    latestActivationCode.value = generatedCodes.value[0]?.code || "";
    latestActivationType.value = generatedCodes.value[0]?.user_type || activationForm.user_type;
    ElMessage.success(total > 1 ? `已生成 ${total} 个激活码` : "用户激活码已生成");
    await loadActivationCodes();
  } catch (error) {
    ElMessage.error(parseApiError(error));
  } finally {
    loading.activation = false;
  }
}

async function copyCode(code) {
  try {
    await copyToClipboard(code);
    ElMessage.success("已复制到剪贴板");
  } catch {
    ElMessage.warning("复制失败，请手动选择");
  }
}

async function copyAllCodes() {
  const text = generatedCodes.value.map((item) => item.code).join("\n");
  try {
    await copyToClipboard(text);
    ElMessage.success(`已复制 ${generatedCodes.value.length} 个激活码`);
  } catch {
    ElMessage.warning("复制失败，请手动选择");
  }
}

async function loadActivationCodes() {
  if (!props.token) return;
  loading.codes = true;
  try {
    const params = {
      ...paginationParams(),
      keyword: filters.keyword || undefined,
      status: filters.status || undefined,
      user_type: filters.user_type || undefined,
    };
    const response = await managerApi.listActivationCodes(props.token, params);
    activationCodes.value = (response.items || []).map((item) => ({
      ...item,
      _deleting: false,
    }));
    patchSummary(summary, response.summary, ["total", "unused", "used", "revoked", "deleted"]);
    updateTotal(response.total || response.summary?.total || activationCodes.value.length);
  } catch (error) {
    ElMessage.error(parseApiError(error));
  } finally {
    loading.codes = false;
  }
}

async function deleteActivationCode(row) {
  if (!row?.id) {
    ElMessage.warning("无效激活码记录");
    return;
  }
  try {
    await ElMessageBox.confirm(
      `确定要删除激活码 "${row.code}" 吗？删除后无法恢复。`,
      "确认删除",
      { confirmButtonText: "确定删除", cancelButtonText: "取消", type: "warning" },
    );
  } catch {
    return;
  }
  row._deleting = true;
  try {
    await managerApi.deleteActivationCode(props.token, row.id);
    ElMessage.success("激活码已删除");
    await loadActivationCodes();
  } catch (error) {
    ElMessage.error(parseApiError(error));
  } finally {
    row._deleting = false;
  }
}

async function batchDelete() {
  if (!hasSelection.value) return;
  const ids = [...selectedIds.value];
  try {
    await ElMessageBox.confirm(
      `确定要批量删除 ${ids.length} 个激活码吗？删除后无法恢复。`,
      "批量删除确认",
      { confirmButtonText: "确定删除", cancelButtonText: "取消", type: "warning" },
    );
  } catch {
    return;
  }
  loading.batchDelete = true;
  try {
    await managerApi.batchDeleteActivationCodes(props.token, { code_ids: ids });
    ElMessage.success(`已批量删除 ${ids.length} 个激活码`);
    doClearSelection();
    await loadActivationCodes();
  } catch (error) {
    ElMessage.error(parseApiError(error));
  } finally {
    loading.batchDelete = false;
  }
}

watch(
  () => props.token,
  async (value) => {
    if (!value) {
      activationCodes.value = [];
      return;
    }
    await loadActivationCodes();
  },
  { immediate: true },
);

onMounted(async () => {
  if (props.token) {
    await loadActivationCodes();
  }
});
</script>
