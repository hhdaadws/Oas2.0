<template>
  <div class="role-dashboard">
    <section class="panel-card">
      <div class="panel-headline">
        <h3>勾协账号管理</h3>
        <el-button type="primary" size="small" @click="showAddDialog = true">添加勾协账号</el-button>
      </div>

      <el-table :data="coopAccounts" border stripe v-loading="loading.list" empty-text="暂无勾协账号">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="login_id" label="游戏ID" min-width="150" />
        <el-table-column prop="status" label="状态" width="90">
          <template #default="scope">
            <el-tag :type="scope.row.status === 'active' ? 'success' : 'info'" size="small">
              {{ scope.row.status === 'active' ? '正常' : '已过期' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="过期日期" width="120">
          <template #default="scope">{{ scope.row.expire_date ? scope.row.expire_date.substring(0,10) : '-' }}</template>
        </el-table-column>
        <el-table-column prop="note" label="备注" min-width="120" />
        <el-table-column label="操作" width="140">
          <template #default="scope">
            <el-button size="small" plain @click="editCoop(scope.row)">编辑</el-button>
            <el-button size="small" type="danger" plain @click="deleteCoop(scope.row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <h4 style="margin-top:20px;margin-bottom:8px">今日时间窗用量</h4>
      <el-table :data="coopWindows" border stripe size="small" empty-text="暂无数据">
        <el-table-column prop="coop_account_id" label="勾协ID" width="90" />
        <el-table-column prop="slot" label="时段" width="80">
          <template #default="scope">{{ scope.row.slot }}点档</template>
        </el-table-column>
        <el-table-column prop="used_count" label="已用次数" width="100" />
      </el-table>
    </section>

    <!-- Add/Edit Dialog -->
    <el-dialog v-model="showAddDialog" :title="editingCoop ? '编辑勾协账号' : '添加勾协账号'" width="420px" @close="resetForm">
      <el-form :model="coopForm" label-width="90px">
        <el-form-item label="游戏ID" v-if="!editingCoop">
          <el-input v-model="coopForm.login_id" placeholder="勾协游戏ID" />
        </el-form-item>
        <el-form-item label="状态" v-if="editingCoop">
          <el-select v-model="coopForm.status">
            <el-option label="正常" value="active" />
            <el-option label="已过期" value="expired" />
          </el-select>
        </el-form-item>
        <el-form-item label="过期日期">
          <el-date-picker v-model="coopForm.expire_date" type="date" value-format="YYYY-MM-DD" placeholder="选择过期日期" style="width:100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="coopForm.note" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" :loading="loading.save" @click="saveCoop">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { managerApi, parseApiError } from "../../lib/http";

const props = defineProps({ token: { type: String, default: "" } });

const loading = reactive({ list: false, save: false });
const coopAccounts = ref([]);
const coopWindows = ref([]);
const showAddDialog = ref(false);
const editingCoop = ref(null);

const coopForm = reactive({ login_id: "", status: "active", expire_date: "", note: "" });

function resetForm() {
  editingCoop.value = null;
  coopForm.login_id = "";
  coopForm.status = "active";
  coopForm.expire_date = "";
  coopForm.note = "";
}

function editCoop(row) {
  editingCoop.value = row;
  coopForm.status = row.status;
  coopForm.expire_date = row.expire_date ? row.expire_date.substring(0,10) : "";
  coopForm.note = row.note || "";
  showAddDialog.value = true;
}

async function loadCoopAccounts() {
  if (!props.token) return;
  loading.list = true;
  try {
    const res = await managerApi.listCoopAccounts(props.token);
    coopAccounts.value = res.items || [];
  } catch (e) {
    ElMessage.error(parseApiError(e));
  } finally {
    loading.list = false;
  }
}

async function loadCoopWindows() {
  if (!props.token) return;
  try {
    const res = await managerApi.getCoopWindows(props.token);
    coopWindows.value = res.items || [];
  } catch {
    // silently fail
  }
}

async function saveCoop() {
  loading.save = true;
  try {
    if (editingCoop.value) {
      const payload = {};
      if (coopForm.status) payload.status = coopForm.status;
      if (coopForm.expire_date) payload.expire_date = coopForm.expire_date;
      if (coopForm.note !== undefined) payload.note = coopForm.note;
      await managerApi.patchCoopAccount(props.token, editingCoop.value.id, payload);
      ElMessage.success("已更新");
    } else {
      if (!coopForm.login_id) { ElMessage.warning("请填写游戏ID"); loading.save = false; return; }
      const payload = { login_id: coopForm.login_id, note: coopForm.note };
      if (coopForm.expire_date) payload.expire_date = coopForm.expire_date;
      await managerApi.createCoopAccount(props.token, payload);
      ElMessage.success("已添加");
    }
    showAddDialog.value = false;
    resetForm();
    await loadCoopAccounts();
  } catch (e) {
    ElMessage.error(parseApiError(e));
  } finally {
    loading.save = false;
  }
}

async function deleteCoop(id) {
  try {
    await ElMessageBox.confirm("确认删除此勾协账号？", "确认", { type: "warning" });
    await managerApi.deleteCoopAccount(props.token, id);
    ElMessage.success("已删除");
    await loadCoopAccounts();
  } catch (e) {
    if (e === "cancel") return;
    ElMessage.error(parseApiError(e));
  }
}

watch(() => props.token, (val) => {
  if (val) { loadCoopAccounts(); loadCoopWindows(); }
}, { immediate: true });
</script>
