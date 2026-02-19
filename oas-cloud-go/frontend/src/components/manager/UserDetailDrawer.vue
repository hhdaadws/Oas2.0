<template>
  <el-drawer v-model="visible" :title="`账号详情 — ${userAccountNo}`" size="700px" direction="rtl" :destroy-on-close="false">
    <el-tabs v-model="activeTab" @tab-click="onTabChange">

      <!-- 基本信息 tab -->
      <el-tab-pane label="基本信息" name="profile">
        <el-form :model="profileForm" label-width="100px" style="margin-top:12px">
          <el-form-item label="游戏ID">
            <el-input v-model="profileForm.login_id" placeholder="游戏内登录ID" />
          </el-form-item>
          <el-form-item label="账号状态">
            <el-select v-model="profileForm.account_status">
              <el-option label="正常" value="active" />
              <el-option label="异常" value="invalid" />
              <el-option label="藏宝阁" value="cangbaoge" />
            </el-select>
          </el-form-item>
          <el-form-item label="进度">
            <el-select v-model="profileForm.progress">
              <el-option label="起号中" value="init" />
              <el-option label="正常" value="ok" />
            </el-select>
          </el-form-item>
          <el-form-item label="备注">
            <el-input v-model="profileForm.remark" type="textarea" :rows="2" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="loading.profile" @click="saveProfile">保存</el-button>
          </el-form-item>
        </el-form>
      </el-tab-pane>

      <!-- 休息配置 tab -->
      <el-tab-pane label="休息配置" name="rest">
        <el-form :model="restForm" label-width="110px" style="margin-top:12px">
          <el-form-item label="启用休息">
            <el-switch v-model="restForm.enabled" />
          </el-form-item>
          <el-form-item label="模式">
            <el-select v-model="restForm.mode">
              <el-option label="随机" value="random" />
              <el-option label="自定义" value="custom" />
            </el-select>
          </el-form-item>
          <template v-if="restForm.mode === 'custom'">
            <el-form-item label="休息开始时间">
              <el-time-select v-model="restForm.rest_start" start="00:00" end="23:30" step="00:30" />
            </el-form-item>
            <el-form-item label="休息时长(分)">
              <el-input-number v-model="restForm.rest_duration" :min="0" :max="1440" />
            </el-form-item>
          </template>
          <el-form-item>
            <el-button plain :loading="loading.rest" @click="loadRestConfig">刷新</el-button>
            <el-button type="primary" :loading="loading.saveRest" @click="saveRestConfig">保存</el-button>
          </el-form-item>
        </el-form>
      </el-tab-pane>

      <!-- 阵容配置 tab -->
      <el-tab-pane label="阵容配置" name="lineup">
        <div style="margin-top:12px">
          <el-input v-model="lineupRaw" type="textarea" :rows="12" placeholder='{"team1": {...}}' />
          <div class="row-actions" style="margin-top:8px">
            <el-button plain :loading="loading.lineup" @click="loadLineupConfig">刷新</el-button>
            <el-button type="primary" :loading="loading.saveLineup" @click="saveLineupConfig">保存</el-button>
          </div>
        </div>
      </el-tab-pane>

      <!-- 式神配置 tab -->
      <el-tab-pane label="式神配置" name="shikigami">
        <div style="margin-top:12px">
          <el-input v-model="shikamiRaw" type="textarea" :rows="12" placeholder='{"shikigami_list": [...]}' />
          <div class="row-actions" style="margin-top:8px">
            <el-button plain :loading="loading.shikigami" @click="loadShikamiConfig">刷新</el-button>
            <el-button type="primary" :loading="loading.saveShikigami" @click="saveShikamiConfig">保存</el-button>
          </div>
        </div>
      </el-tab-pane>

      <!-- 探索进度 tab -->
      <el-tab-pane label="探索进度" name="explore">
        <div style="margin-top:12px">
          <pre style="background:var(--glass-2);padding:12px;border-radius:6px;font-size:12px;max-height:400px;overflow:auto">{{ exploreProgressText }}</pre>
          <el-button plain :loading="loading.explore" style="margin-top:8px" @click="loadExploreProgress">刷新</el-button>
        </div>
      </el-tab-pane>

      <!-- 执行日志 tab -->
      <el-tab-pane label="执行日志" name="user-logs">
        <div style="margin-top:12px">
          <el-table :data="userLogs" border stripe size="small" empty-text="暂无日志">
            <el-table-column prop="log_type" label="类型" width="120" />
            <el-table-column prop="level" label="级别" width="80">
              <template #default="scope">
                <el-tag :type="logLevelType(scope.row.level)" size="small">{{ scope.row.level }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="message" label="消息" min-width="200" />
            <el-table-column label="时间" width="160">
              <template #default="scope">{{ formatTime(scope.row.ts) }}</template>
            </el-table-column>
          </el-table>
          <el-pagination
            v-model:current-page="logPagination.page"
            v-model:page-size="logPagination.pageSize"
            :total="logPagination.total"
            layout="total, prev, pager, next"
            style="margin-top:8px"
            @current-change="loadUserLogs"
          />
        </div>
      </el-tab-pane>
    </el-tabs>
  </el-drawer>
</template>

<script setup>
import { ref, reactive, watch } from "vue";
import { ElMessage } from "element-plus";
import { managerApi, parseApiError } from "../../lib/http";
import { formatTime } from "../../lib/helpers";

const props = defineProps({
  token: { type: String, default: "" },
  userId: { type: Number, default: 0 },
  userAccountNo: { type: String, default: "" },
});

const emit = defineEmits(["profile-updated"]);

const visible = defineModel({ type: Boolean, default: false });
const activeTab = ref("profile");

const loading = reactive({
  profile: false,
  rest: false,
  saveRest: false,
  lineup: false,
  saveLineup: false,
  shikigami: false,
  saveShikigami: false,
  explore: false,
});

const profileForm = reactive({
  login_id: "",
  account_status: "active",
  progress: "ok",
  remark: "",
});

const restForm = reactive({
  enabled: false,
  mode: "random",
  rest_start: "00:00",
  rest_duration: 60,
});

const lineupRaw = ref("{}");
const shikamiRaw = ref("{}");
const exploreProgressText = ref("暂无数据");
const userLogs = ref([]);
const logPagination = reactive({ page: 1, pageSize: 20, total: 0 });

function logLevelType(level) {
  if (level === "error") return "danger";
  if (level === "warning") return "warning";
  return "info";
}

async function saveProfile() {
  if (!props.userId) return;
  loading.profile = true;
  try {
    const payload = {};
    if (profileForm.login_id !== undefined) payload.login_id = profileForm.login_id;
    if (profileForm.account_status) payload.account_status = profileForm.account_status;
    if (profileForm.progress) payload.progress = profileForm.progress;
    if (profileForm.remark !== undefined) payload.remark = profileForm.remark;
    await managerApi.patchUserGameProfile(props.token, props.userId, payload);
    ElMessage.success("基本信息已保存");
    emit("profile-updated");
  } catch (e) {
    ElMessage.error(parseApiError(e));
  } finally {
    loading.profile = false;
  }
}

async function loadRestConfig() {
  if (!props.userId) return;
  loading.rest = true;
  try {
    const res = await managerApi.getUserRestConfig(props.token, props.userId);
    restForm.enabled = res.enabled ?? false;
    restForm.mode = res.mode || "random";
    restForm.rest_start = res.rest_start || "00:00";
    restForm.rest_duration = res.rest_duration ?? 60;
  } catch (e) {
    ElMessage.error(parseApiError(e));
  } finally {
    loading.rest = false;
  }
}

async function saveRestConfig() {
  if (!props.userId) return;
  loading.saveRest = true;
  try {
    await managerApi.putUserRestConfig(props.token, props.userId, { ...restForm });
    ElMessage.success("休息配置已保存");
  } catch (e) {
    ElMessage.error(parseApiError(e));
  } finally {
    loading.saveRest = false;
  }
}

async function loadLineupConfig() {
  if (!props.userId) return;
  loading.lineup = true;
  try {
    const res = await managerApi.getUserLineupConfig(props.token, props.userId);
    lineupRaw.value = JSON.stringify(res.config || {}, null, 2);
  } catch (e) {
    ElMessage.error(parseApiError(e));
  } finally {
    loading.lineup = false;
  }
}

async function saveLineupConfig() {
  if (!props.userId) return;
  loading.saveLineup = true;
  try {
    let config = {};
    try { config = JSON.parse(lineupRaw.value); } catch { ElMessage.error("JSON格式错误"); loading.saveLineup = false; return; }
    await managerApi.putUserLineupConfig(props.token, props.userId, { config });
    ElMessage.success("阵容配置已保存");
  } catch (e) {
    ElMessage.error(parseApiError(e));
  } finally {
    loading.saveLineup = false;
  }
}

async function loadShikamiConfig() {
  if (!props.userId) return;
  loading.shikigami = true;
  try {
    const res = await managerApi.getUserShikamiConfig(props.token, props.userId);
    shikamiRaw.value = JSON.stringify(res.config || {}, null, 2);
  } catch (e) {
    ElMessage.error(parseApiError(e));
  } finally {
    loading.shikigami = false;
  }
}

async function saveShikamiConfig() {
  if (!props.userId) return;
  loading.saveShikigami = true;
  try {
    let config = {};
    try { config = JSON.parse(shikamiRaw.value); } catch { ElMessage.error("JSON格式错误"); loading.saveShikigami = false; return; }
    await managerApi.putUserShikamiConfig(props.token, props.userId, { config });
    ElMessage.success("式神配置已保存");
  } catch (e) {
    ElMessage.error(parseApiError(e));
  } finally {
    loading.saveShikigami = false;
  }
}

async function loadExploreProgress() {
  if (!props.userId) return;
  loading.explore = true;
  try {
    const res = await managerApi.getUserExploreProgress(props.token, props.userId);
    exploreProgressText.value = JSON.stringify(res.progress || {}, null, 2);
  } catch (e) {
    ElMessage.error(parseApiError(e));
  } finally {
    loading.explore = false;
  }
}

async function loadUserLogs() {
  if (!props.userId) return;
  try {
    const res = await managerApi.getUserUserLogs(props.token, props.userId, {
      page: logPagination.page,
      page_size: logPagination.pageSize,
    });
    userLogs.value = res.items || [];
    logPagination.total = res.total || 0;
  } catch (e) {
    ElMessage.error(parseApiError(e));
  }
}

function onTabChange(tab) {
  const name = tab.props.name;
  if (name === "rest") loadRestConfig();
  else if (name === "lineup") loadLineupConfig();
  else if (name === "shikigami") loadShikamiConfig();
  else if (name === "explore") loadExploreProgress();
  else if (name === "user-logs") loadUserLogs();
}

function prefillFromRow(row) {
  if (!row) return;
  profileForm.login_id = row.login_id || "";
  profileForm.account_status = row.account_status || "active";
  profileForm.progress = row.progress || "ok";
  profileForm.remark = row.remark || "";
}

watch(visible, (val) => {
  if (val) {
    activeTab.value = "profile";
  }
});

defineExpose({ prefillFromRow });
</script>
