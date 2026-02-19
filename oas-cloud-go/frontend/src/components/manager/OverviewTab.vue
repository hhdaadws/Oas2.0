<template>
  <div class="role-dashboard">
    <section class="panel-card">
      <div class="panel-headline">
        <h3>运营总览</h3>
        <el-button text type="primary" :loading="loading.overview" @click="loadOverview">刷新总览</el-button>
      </div>
      <div class="stats-grid">
        <div class="stat-item">
          <span class="stat-label">下属总数</span>
          <strong class="stat-value">{{ overview.user_stats.total }}</strong>
        </div>
        <div class="stat-item">
          <span class="stat-label">活跃下属</span>
          <strong class="stat-value">{{ overview.user_stats.active }}</strong>
        </div>
        <div class="stat-item">
          <span class="stat-label">待执行任务</span>
          <strong class="stat-value">{{ overview.job_stats.pending }}</strong>
        </div>
        <div class="stat-item">
          <span class="stat-label">运行中任务</span>
          <strong class="stat-value">{{ overview.job_stats.running }}</strong>
        </div>
        <div class="stat-item">
          <span class="stat-label">24h 失败数</span>
          <strong class="stat-value">{{ overview.recent_failures_24h }}</strong>
        </div>
        <div class="stat-item">
          <span class="stat-label">最近刷新</span>
          <strong class="stat-value stat-time">{{ formatTime(overview.generated_at) }}</strong>
        </div>
      </div>
    </section>

    <section class="panel-grid">
      <article class="panel-card panel-card--highlight">
        <div class="panel-headline">
          <h3>管理员账号状态</h3>
          <el-tag :type="statusTagType(managerProfile.status)">{{ statusLabel(managerProfile.status) }}</el-tag>
        </div>
        <div class="stats-grid">
          <div class="stat-item">
            <span class="stat-label">账号</span>
            <strong class="stat-value">{{ managerProfile.username || "-" }}</strong>
          </div>
          <div class="stat-item">
            <span class="stat-label">到期时间</span>
            <strong class="stat-value stat-time">{{ formatTime(managerProfile.expires_at) }}</strong>
          </div>
          <div class="stat-item">
            <span class="stat-label">是否过期</span>
            <strong class="stat-value">{{ managerProfile.expired ? "是" : "否" }}</strong>
          </div>
        </div>
        <div class="row-actions">
          <el-button plain :loading="loading.profile" @click="loadManagerProfile">刷新账号状态</el-button>
        </div>
      </article>

      <article class="panel-card panel-card--compact">
        <div class="panel-headline">
          <h3>管理员续费</h3>
          <el-tag type="warning">续费秘钥</el-tag>
        </div>
        <el-form :model="redeemForm" inline>
          <el-form-item label="秘钥">
            <el-input v-model="redeemForm.code" placeholder="mrk_xxx" clearable />
          </el-form-item>
          <el-form-item>
            <el-button type="success" :loading="loading.redeem" @click="redeemRenewalKey">兑换续费</el-button>
          </el-form-item>
        </el-form>
        <p class="tip-text">激活码发放请到"激活码管理"，快速建号请到"下属配置"。</p>
      </article>
    </section>
  </div>
</template>

<script setup>
import { onMounted, reactive, watch } from "vue";
import { ElMessage } from "element-plus";
import { managerApi, parseApiError } from "../../lib/http";
import { statusTagType, statusLabel, formatTime } from "../../lib/helpers";

const props = defineProps({
  token: {
    type: String,
    default: "",
  },
});

const emit = defineEmits(["profile-updated"]);

const loading = reactive({
  overview: false,
  profile: false,
  redeem: false,
});

const redeemForm = reactive({ code: "" });

const managerProfile = reactive({
  id: 0,
  username: "",
  status: "",
  expires_at: "",
  expired: false,
});

const overview = reactive({
  user_stats: {
    total: 0,
    active: 0,
    expired: 0,
    disabled: 0,
  },
  job_stats: {
    pending: 0,
    leased: 0,
    running: 0,
    success: 0,
    failed: 0,
  },
  recent_failures_24h: 0,
  generated_at: "",
});

async function loadOverview() {
  loading.overview = true;
  try {
    const response = await managerApi.overview(props.token);
    overview.user_stats = {
      ...overview.user_stats,
      ...(response.user_stats || {}),
    };
    overview.job_stats = {
      ...overview.job_stats,
      ...(response.job_stats || {}),
    };
    overview.recent_failures_24h = response.recent_failures_24h || 0;
    overview.generated_at = response.generated_at || "";
  } catch (error) {
    ElMessage.error(parseApiError(error));
  } finally {
    loading.overview = false;
  }
}

async function loadManagerProfile() {
  loading.profile = true;
  try {
    const response = await managerApi.me(props.token);
    managerProfile.id = response.id || 0;
    managerProfile.username = response.username || "";
    managerProfile.status = response.status || "";
    managerProfile.expires_at = response.expires_at || "";
    managerProfile.expired = response.expired === true;
  } catch (error) {
    ElMessage.error(parseApiError(error));
  } finally {
    loading.profile = false;
  }
}

async function redeemRenewalKey() {
  const code = redeemForm.code.trim();
  if (!code) {
    ElMessage.warning("请输入续费秘钥");
    return;
  }
  loading.redeem = true;
  try {
    await managerApi.redeemRenewalKey(props.token, { code });
    ElMessage.success("管理员续费成功");
    redeemForm.code = "";
    await loadManagerProfile();
    emit("profile-updated");
  } catch (error) {
    ElMessage.error(parseApiError(error));
  } finally {
    loading.redeem = false;
  }
}

watch(
  () => props.token,
  async (value) => {
    if (!value) {
      managerProfile.id = 0;
      managerProfile.username = "";
      managerProfile.status = "";
      managerProfile.expires_at = "";
      managerProfile.expired = false;
      return;
    }
    await Promise.all([loadManagerProfile(), loadOverview()]);
  },
  { immediate: true },
);

onMounted(async () => {
  if (props.token) {
    await Promise.all([loadManagerProfile(), loadOverview()]);
  }
});
</script>
