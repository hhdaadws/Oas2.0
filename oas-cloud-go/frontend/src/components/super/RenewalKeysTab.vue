<script setup>
import { onMounted, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { parseApiError, superApi } from "../../lib/http";
import {
  keyStatusTagType,
  keyStatusLabel,
  formatTime,
  patchSummary,
} from "../../lib/helpers";
import { usePagination } from "../../composables/usePagination";
import { useBatchSelection } from "../../composables/useBatchSelection";
import { useDebouncedFilter } from "../../composables/useDebouncedFilter";
import TableSkeleton from "../shared/TableSkeleton.vue";
import BatchActionBar from "../shared/BatchActionBar.vue";

const props = defineProps({
  token: { type: String, default: "" },
});

const loading = reactive({ createKey: false, keys: false });
const renewalForm = reactive({ duration_days: 30 });
const latestRenewal = reactive({ code: "", duration_days: 0 });
const keyFilters = reactive({ keyword: "", status: "" });
const keySummary = reactive({ total: 0, unused: 0, used: 0, revoked: 0, deleted: 0 });
const renewalKeys = ref([]);
const tableRef = ref(null);
const showCreateDialog = ref(false);

const { pagination, updateTotal, resetPage, paginationParams } = usePagination();
const { selectedIds, selectedCount, hasSelection, onSelectionChange, clearSelection } = useBatchSelection();

useDebouncedFilter(() => keyFilters, () => { resetPage(); loadRenewalKeys(); });

watch(
  () => props.token,
  async (value) => {
    if (!value) { renewalKeys.value = []; return; }
    await loadRenewalKeys();
  },
  { immediate: true },
);

onMounted(async () => {
  if (props.token) await loadRenewalKeys();
});

async function createRenewalKey() {
  if (!props.token) { ElMessage.warning("请先登录超级管理员"); return; }
  loading.createKey = true;
  try {
    const response = await superApi.createManagerRenewalKey(props.token, {
      duration_days: renewalForm.duration_days,
    });
    latestRenewal.code = response.code || "";
    latestRenewal.duration_days = response.duration_days || renewalForm.duration_days;
    ElMessage.success("管理员续费秘钥已生成");
    await loadRenewalKeys();
  } catch (error) {
    ElMessage.error(parseApiError(error));
  } finally {
    loading.createKey = false;
  }
}

async function deleteRenewalKey(row) {
  if (!row?.id) { ElMessage.warning("无效秘钥记录"); return; }
  try {
    await ElMessageBox.confirm(
      `确定要删除秘钥 "${row.code}" 吗？删除后无法恢复。`,
      "确认删除",
      { confirmButtonText: "确定删除", cancelButtonText: "取消", type: "warning" },
    );
  } catch { return; }
  row._deleting = true;
  try {
    await superApi.deleteRenewalKey(props.token, row.id);
    ElMessage.success("续费秘钥已删除");
    await loadRenewalKeys();
  } catch (error) {
    ElMessage.error(parseApiError(error));
  } finally {
    row._deleting = false;
  }
}

async function batchDeleteKeys() {
  if (!hasSelection.value) return;
  try {
    await ElMessageBox.confirm(
      `确定要批量删除 ${selectedCount.value} 个秘钥吗？删除后无法恢复。`,
      "确认批量删除",
      { confirmButtonText: "确定删除", cancelButtonText: "取消", type: "warning" },
    );
  } catch { return; }
  try {
    const res = await superApi.batchDeleteRenewalKeys(props.token, { key_ids: selectedIds.value });
    ElMessage.success(`已删除 ${res.deleted} 个秘钥`);
    clearSelection();
    if (tableRef.value) tableRef.value.clearSelection();
    await loadRenewalKeys();
  } catch (error) {
    ElMessage.error(parseApiError(error));
  }
}

async function loadRenewalKeys() {
  if (!props.token) return;
  loading.keys = true;
  try {
    const response = await superApi.listManagerRenewalKeys(props.token, {
      keyword: keyFilters.keyword || undefined,
      status: keyFilters.status || undefined,
      ...paginationParams(),
    });
    renewalKeys.value = (response.items || []).map((item) => ({
      ...item,
      _deleting: false,
    }));
    patchSummary(keySummary, response.summary, ["total", "unused", "used", "revoked", "deleted"]);
    updateTotal(response.total || 0);
  } catch (error) {
    ElMessage.error(parseApiError(error));
  } finally {
    loading.keys = false;
  }
}

function canSelectRow(row) {
  return row.status === "unused";
}

async function copyKeyCode(code) {
  try {
    await navigator.clipboard.writeText(code);
    ElMessage.success("已复制到剪贴板");
  } catch {
    ElMessage.warning("复制失败，请手动选择");
  }
}
</script>

<template>
  <section class="panel-card panel-card--compact">
    <div class="panel-headline">
      <h3>秘钥筛选</h3>
      <el-button text type="primary" :loading="loading.keys" @click="loadRenewalKeys">刷新</el-button>
    </div>
    <el-form label-width="100px" class="compact-form">
      <el-form-item label="关键词">
        <el-input v-model="keyFilters.keyword" placeholder="按秘钥检索" clearable />
      </el-form-item>
      <el-form-item label="状态">
        <el-select v-model="keyFilters.status" clearable placeholder="全部状态">
          <el-option label="未使用" value="unused" />
          <el-option label="已使用" value="used" />
          <el-option label="已删除" value="deleted" />
        </el-select>
      </el-form-item>
    </el-form>
  </section>

  <section class="panel-card panel-card--compact">
    <div class="panel-headline">
      <h3>秘钥状态统计</h3>
      <span class="muted">全量维度</span>
    </div>
    <div class="stats-grid">
      <div class="stat-item">
        <span class="stat-label">总数</span>
        <strong class="stat-value">{{ keySummary.total }}</strong>
      </div>
      <div class="stat-item">
        <span class="stat-label">未使用</span>
        <strong class="stat-value">{{ keySummary.unused }}</strong>
      </div>
      <div class="stat-item">
        <span class="stat-label">已使用</span>
        <strong class="stat-value">{{ keySummary.used }}</strong>
      </div>
      <div class="stat-item">
        <span class="stat-label">已删除</span>
        <strong class="stat-value">{{ keySummary.deleted }}</strong>
      </div>
    </div>
  </section>

  <section class="panel-card">
    <div class="panel-headline">
      <h3>秘钥状态总表</h3>
      <div class="row-actions">
        <span class="muted">共 {{ pagination.total }} 条</span>
        <el-button type="primary" size="small" @click="showCreateDialog = true">生成秘钥</el-button>
      </div>
    </div>

    <TableSkeleton v-if="loading.keys && renewalKeys.length === 0" :rows="5" :columns="8" />
    <div v-else class="data-table-wrapper">
      <el-table
        ref="tableRef"
        :data="renewalKeys"
        border
        stripe
        empty-text="暂无秘钥数据"
        v-loading="loading.keys"
        @selection-change="onSelectionChange"
      >
        <el-table-column type="selection" width="48" :selectable="canSelectRow" />
        <el-table-column prop="id" label="ID" width="80" sortable />
        <el-table-column label="秘钥" min-width="220">
          <template #default="scope">
            <span class="clickable-cell" @click="copyKeyCode(scope.row.code)" title="点击复制">{{ scope.row.code }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="duration_days" label="天数" width="100" sortable />
        <el-table-column prop="status" label="状态" width="120" sortable>
          <template #default="scope">
            <el-tag :type="keyStatusTagType(scope.row.status)">{{ keyStatusLabel(scope.row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="使用者" min-width="180">
          <template #default="scope">
            <span>{{ scope.row.used_by_manager_username || scope.row.used_by_manager_id || "-" }}</span>
          </template>
        </el-table-column>
        <el-table-column label="使用时间" min-width="180" sortable>
          <template #default="scope">{{ formatTime(scope.row.used_at) }}</template>
        </el-table-column>
        <el-table-column label="创建时间" min-width="180" sortable>
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
              @click="deleteRenewalKey(scope.row)"
            >
              删除
            </el-button>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <BatchActionBar :selected-count="selectedCount" @clear="() => { clearSelection(); tableRef?.clearSelection(); }">
      <el-button type="danger" @click="batchDeleteKeys">批量删除</el-button>
    </BatchActionBar>

    <div class="pagination-wrapper">
      <el-pagination
        v-if="pagination.total > pagination.pageSize"
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.pageSize"
        :page-sizes="[20, 50, 100, 200]"
        :total="pagination.total"
        layout="total, sizes, prev, pager, next, jumper"
        @size-change="() => { resetPage(); loadRenewalKeys(); }"
        @current-change="loadRenewalKeys"
      />
    </div>
  </section>

  <el-dialog v-model="showCreateDialog" title="生成续费秘钥" width="420px"
    @close="latestRenewal.code = ''">
    <el-form :model="renewalForm" label-width="100px">
      <el-form-item label="续期天数">
        <el-input-number v-model="renewalForm.duration_days" :min="1" :max="3650" style="width:100%" />
      </el-form-item>
    </el-form>
    <div v-if="latestRenewal.code" style="margin-top:12px;display:flex;align-items:flex-start;gap:8px;">
      <el-alert type="success" :closable="false"
        :title="`秘钥：${latestRenewal.code}`"
        :description="`续期天数：${latestRenewal.duration_days} 天`"
        style="flex:1"
      />
      <el-button size="small" type="success" plain @click="copyKeyCode(latestRenewal.code)">复制</el-button>
    </div>
    <template #footer>
      <el-button @click="showCreateDialog = false">关闭</el-button>
      <el-button type="primary" :loading="loading.createKey" @click="createRenewalKey">生成秘钥</el-button>
    </template>
  </el-dialog>
</template>
