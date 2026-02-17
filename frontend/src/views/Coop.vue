<template>
  <div class="coop">
    <el-card class="action-bar">
      <div class="left">
        <el-button type="primary" @click="openAddDialog">
          <el-icon><Plus /></el-icon>
          新增勾协账号
        </el-button>
        <el-select v-model="statusFilter" placeholder="状态" clearable style="width: 120px; margin-left: 10px" @change="fetchList">
          <el-option label="可用" :value="1" />
          <el-option label="失效" :value="2" />
        </el-select>
        <el-select v-model="expiryFilter" placeholder="过期状态" clearable style="width: 140px; margin-left: 10px" @change="fetchList">
          <el-option label="未过期" value="valid" />
          <el-option label="已过期" value="expired" />
          <el-option label="全部" value="all" />
        </el-select>
        <el-popconfirm :disabled="!selectedIds.length" :title="`确认批量删除选中 ${selectedIds.length} 个账号？`" confirm-button-type="danger" @confirm="handleBatchDelete">
          <template #reference>
            <el-button type="danger" :disabled="!selectedIds.length" style="margin-left: 10px">批量删除</el-button>
          </template>
        </el-popconfirm>
      </div>
      <div class="right">
        <el-input v-model="keyword" placeholder="按登录ID搜索" clearable style="width: 240px" @input="onSearchInput" />
        <el-button link @click="fetchList" style="margin-left: 6px">
          <el-icon><Refresh /></el-icon>刷新
        </el-button>
      </div>
    </el-card>

    <el-card>
      <el-table :data="accounts" stripe @selection-change="onSelectionChange">
        <el-table-column type="selection" width="50" />
        <el-table-column prop="login_id" label="登录ID" min-width="180" />
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-switch :model-value="row.status === 1" @change="(val)=>toggleStatus(row, val)" inline-prompt active-text="可用" inactive-text="失效" />
          </template>
        </el-table-column>
        <el-table-column label="当前窗口" width="220">
          <template #default="{ row }">
            <el-tag type="info" size="small" style="margin-right: 6px">{{ row.window.date }} {{ row.window.slot }}:00</el-tag>
            <el-tag :type="row.window.completed ? 'success' : 'primary'" size="small">{{ row.window.used }}/2</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="过期" width="200">
          <template #default="{ row }">
            <el-tag v-if="row.expired" type="danger" size="small">已过期</el-tag>
            <span v-else>{{ row.expire_date || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="note" label="备注" min-width="160" />
        <el-table-column prop="created_at" label="创建时间" width="180" />
        <el-table-column label="操作" width="160">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEditDialog(row)">编辑</el-button>
            <el-popconfirm title="删除该勾协账号？" confirm-button-type="danger" @confirm="() => handleDelete(row)">
              <template #reference>
                <el-button link type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!accounts.length" description="暂无勾协账号" />
    </el-card>

    <!-- 新增对话框 -->
    <el-dialog v-model="addDialogVisible" title="新增勾协账号" width="420px">
      <el-form :model="addForm" label-width="90px">
        <el-form-item label="登录ID" required>
          <el-input v-model="addForm.login_id" placeholder="请输入登录ID" />
        </el-form-item>
        <el-form-item label="过期日期">
          <el-date-picker v-model="addForm.expire_date" type="date" placeholder="YYYY-MM-DD" format="YYYY-MM-DD" value-format="YYYY-MM-DD" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="addForm.note" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addDialogVisible=false">取消</el-button>
        <el-button type="primary" @click="handleAdd">确定</el-button>
      </template>
    </el-dialog>

    <!-- 编辑对话框 -->
    <el-dialog v-model="editDialogVisible" title="编辑勾协账号" width="420px">
      <el-form :model="editForm" label-width="90px">
        <el-form-item label="登录ID">
          <el-input v-model="editForm.login_id" disabled />
        </el-form-item>
        <el-form-item label="过期日期">
          <el-date-picker v-model="editForm.expire_date" type="date" placeholder="YYYY-MM-DD" format="YYYY-MM-DD" value-format="YYYY-MM-DD" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="editForm.note" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible=false">取消</el-button>
        <el-button type="primary" @click="handleEditSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listCoopAccounts, createCoopAccount, updateCoopAccount, deleteCoopAccount } from '@/api/coop'

const accounts = ref([])
const selectedIds = ref([])
const statusFilter = ref(null) // 1|2|null
const expiryFilter = ref(null) // 'valid'|'expired'|'all'|null
const keyword = ref('')
let searchTimer = null

const addDialogVisible = ref(false)
const addForm = ref({ login_id: '', expire_date: '', note: '' })

const editDialogVisible = ref(false)
const editForm = ref({ id: 0, login_id: '', expire_date: '', note: '' })

const dateAfterDays = (days) => {
  const d = new Date()
  d.setDate(d.getDate() + days)
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const da = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${da}`
}

const fetchList = async () => {
  try {
    const params = {}
    if (statusFilter.value) params.status = statusFilter.value
    if (keyword.value) params.keyword = keyword.value.trim()
    if (expiryFilter.value) params.expiry = expiryFilter.value
    const res = await listCoopAccounts(params)
    accounts.value = res.accounts || []
  } catch (e) {
    ElMessage.error('获取勾协库失败')
  }
}

const onSearchInput = () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => fetchList(), 300)
}

const onSelectionChange = (rows) => {
  selectedIds.value = rows.map(r => r.id)
}

const openAddDialog = () => {
  addForm.value = { login_id: '', expire_date: dateAfterDays(31), note: '' }
  addDialogVisible.value = true
}

const handleAdd = async () => {
  if (!addForm.value.login_id) {
    ElMessage.warning('请输入登录ID')
    return
  }
  try {
    await createCoopAccount(addForm.value)
    ElMessage.success('创建成功')
    addDialogVisible.value = false
    fetchList()
  } catch (e) {
    ElMessage.error('创建失败')
  }
}

const openEditDialog = (row) => {
  editForm.value = { id: row.id, login_id: row.login_id, expire_date: row.expire_date || '', note: row.note || '' }
  editDialogVisible.value = true
}

const handleEditSave = async () => {
  try {
    await updateCoopAccount(editForm.value.id, { expire_date: editForm.value.expire_date, note: editForm.value.note })
    ElMessage.success('已保存')
    editDialogVisible.value = false
    fetchList()
  } catch (e) {
    ElMessage.error('保存失败')
  }
}

const handleDelete = async (row) => {
  try {
    await deleteCoopAccount(row.id)
    ElMessage.success('已删除')
    fetchList()
  } catch (e) {
    ElMessage.error('删除失败')
  }
}

const handleBatchDelete = async () => {
  try {
    await Promise.all(selectedIds.value.map(id => deleteCoopAccount(id)))
    ElMessage.success(`已删除 ${selectedIds.value.length} 个账号`)
    selectedIds.value = []
    fetchList()
  } catch (e) {
    ElMessage.error('批量删除失败')
  }
}

const toggleStatus = async (row, val) => {
  try {
    await updateCoopAccount(row.id, { status: val ? 1 : 2 })
    row.status = val ? 1 : 2
    ElMessage.success('已更新状态')
  } catch (e) {
    ElMessage.error('更新失败')
  }
}

fetchList()
</script>

<style scoped lang="scss">
.coop {
  .action-bar {
    margin-bottom: 16px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .left { display: flex; align-items: center; gap: 8px; }
  .right { display: flex; align-items: center; }
}
</style>