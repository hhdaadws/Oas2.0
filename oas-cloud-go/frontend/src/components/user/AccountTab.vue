<script setup>
import { onMounted, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { parseApiError, userApi } from "../../lib/http";
import { userTypeLabel, statusLabel, formatTime, ASSET_FIELDS } from "../../lib/helpers";
import { useTaskTemplates } from "../../composables/useTaskTemplates";

const props = defineProps({
  token: { type: String, default: "" },
  accountNo: { type: String, default: "" },
});

const emit = defineEmits(["logout"]);

const loading = reactive({ profile: false, redeem: false, logout: false, assets: false });
const redeemForm = reactive({ code: "" });
const logoutAll = ref(false);
const { ensureTaskTemplates } = useTaskTemplates();
const assetFields = ASSET_FIELDS;

const profile = reactive({
  account_no: "", user_type: "daily", status: "", expires_at: "",
  token_exp: "", last_used_at: "", manager_id: "",
});

const meAssets = reactive({
  level: 1, stamina: 0, gouyu: 0, lanpiao: 0, gold: 0,
  gongxun: 0, xunzhang: 0, tupo_ticket: 0,
  fanhe_level: 1, jiuhu_level: 1, liao_level: 0,
});

function syncAssets(assets) {
  const incoming = assets || {};
  Object.keys(meAssets).forEach((key) => {
    meAssets[key] = Number(incoming[key] ?? meAssets[key] ?? 0);
  });
}

watch(
  () => props.token,
  async (value) => {
    if (!value) { profile.user_type = "daily"; return; }
    await loadMeProfile();
  },
  { immediate: true },
);

onMounted(async () => {
  if (props.token) await loadMeProfile();
});

async function loadMeProfile() {
  loading.profile = true;
  try {
    const response = await userApi.getMeProfile(props.token);
    profile.account_no = response.account_no || "";
    profile.user_type = response.user_type || "daily";
    profile.status = response.status || "";
    profile.expires_at = response.expires_at || "";
    profile.token_exp = response.token_exp || "";
    profile.last_used_at = response.last_used_at || "";
    profile.manager_id = response.manager_id || "";
    syncAssets(response.assets || {});
  } catch (error) {
    ElMessage.error(parseApiError(error));
  } finally {
    loading.profile = false;
  }
}

async function loadMeAssets() {
  loading.assets = true;
  try {
    const response = await userApi.getMeAssets(props.token);
    profile.user_type = response.user_type || profile.user_type || "daily";
    profile.expires_at = response.expires_at || profile.expires_at;
    profile.status = response.status || profile.status;
    syncAssets(response.assets || {});
  } catch (error) {
    ElMessage.error(parseApiError(error));
  } finally {
    loading.assets = false;
  }
}

async function redeemCode() {
  const code = redeemForm.code.trim();
  if (!code) { ElMessage.warning("请输入激活码"); return; }
  loading.redeem = true;
  try {
    await userApi.redeemCode(props.token, { code });
    await loadMeProfile();
    await ensureTaskTemplates(profile.user_type);
    ElMessage.success("续费兑换成功");
    redeemForm.code = "";
  } catch (error) {
    ElMessage.error(parseApiError(error));
  } finally {
    loading.redeem = false;
  }
}

async function logoutWithServer() {
  const message = logoutAll.value
    ? "确定要退出全部设备的登录状态吗？所有设备上的会话都将失效。"
    : "确定要安全退出当前设备吗？";
  try {
    await ElMessageBox.confirm(message, "确认退出", {
      confirmButtonText: "确定退出", cancelButtonText: "取消", type: "warning",
    });
  } catch { return; }
  loading.logout = true;
  try {
    await userApi.logout(props.token, { all: logoutAll.value });
    ElMessage.success(logoutAll.value ? "已退出全部设备" : "已退出当前设备");
    emit("logout");
  } catch (error) {
    ElMessage.error(parseApiError(error));
  } finally {
    loading.logout = false;
  }
}
</script>

<template>
  <section class="panel-grid">
    <article class="panel-card panel-card--highlight">
      <div class="panel-headline">
        <h3>用户会话信息</h3>
        <el-tag type="success">已登录</el-tag>
      </div>
      <p class="tip-text">账号：{{ accountNo || "未记录" }}</p>
      <el-button type="danger" plain @click="$emit('logout')">退出当前用户会话</el-button>
    </article>

    <article class="panel-card panel-card--compact">
      <div class="panel-headline">
        <h3>激活码续费</h3>
        <el-tag type="warning">一次性激活码</el-tag>
      </div>
      <el-form :model="redeemForm" inline>
        <el-form-item label="激活码">
          <el-input v-model="redeemForm.code" placeholder="激活码示例：uac_xxx" clearable />
        </el-form-item>
        <el-form-item>
          <el-button type="success" :loading="loading.redeem" @click="redeemCode">兑换续费</el-button>
        </el-form-item>
      </el-form>
      <el-alert type="info" :closable="false" title="续费规则：未过期顺延，已过期从当前时刻重算" />
    </article>
  </section>

  <section class="panel-card">
    <div class="panel-headline">
      <h3>我的账号资料</h3>
      <div class="row-actions">
        <el-switch v-model="logoutAll" size="small" />
        <span class="muted" style="font-size: 12px;">{{ logoutAll ? '退出全部设备' : '仅当前设备' }}</span>
        <el-button plain :loading="loading.profile" @click="loadMeProfile">刷新资料</el-button>
        <el-button type="danger" :loading="loading.logout" @click="logoutWithServer">安全退出</el-button>
      </div>
    </div>
    <div class="stats-grid">
      <div class="stat-item">
        <span class="stat-label">账号</span>
        <strong class="stat-value">{{ profile.account_no || accountNo || "-" }}</strong>
      </div>
      <div class="stat-item">
        <span class="stat-label">类型</span>
        <strong class="stat-value">{{ userTypeLabel(profile.user_type) }}</strong>
      </div>
      <div class="stat-item">
        <span class="stat-label">状态</span>
        <strong class="stat-value">{{ statusLabel(profile.status) }}</strong>
      </div>
      <div class="stat-item">
        <span class="stat-label">到期时间</span>
        <strong class="stat-value stat-time">{{ formatTime(profile.expires_at) }}</strong>
      </div>
      <div class="stat-item">
        <span class="stat-label">令牌到期</span>
        <strong class="stat-value stat-time">{{ formatTime(profile.token_exp) }}</strong>
      </div>
      <div class="stat-item">
        <span class="stat-label">最近活跃</span>
        <strong class="stat-value stat-time">{{ formatTime(profile.last_used_at) }}</strong>
      </div>
      <div class="stat-item">
        <span class="stat-label">上级管理员ID</span>
        <strong class="stat-value">{{ profile.manager_id || "-" }}</strong>
      </div>
    </div>
  </section>

  <section class="panel-card">
    <div class="panel-headline">
      <h3>我的资产</h3>
      <el-button plain :loading="loading.assets" @click="loadMeAssets">刷新资产</el-button>
    </div>
    <div class="stats-grid">
      <div v-for="asset in assetFields" :key="asset.key" class="stat-item">
        <span class="stat-label">{{ asset.label }}</span>
        <strong class="stat-value">{{ meAssets[asset.key] ?? 0 }}</strong>
      </div>
    </div>
  </section>
</template>
