<template>
  <div class="page-shell page-shell--login">
    <header class="console-header glass-card stagger-1">
      <div class="brand">
        <p class="eyebrow">超级管理员认证</p>
        <h1>超级管理员登录</h1>
        <p class="subtitle">
          该页面用于超管初始化与登录；登录成功后将自动跳转到超级管理员管理后台。
        </p>
      </div>
    </header>

    <section class="login-center-wrap">
      <section class="auth-card glass-card stagger-2 login-center-card">
        <div class="panel-headline">
          <h3>初始化与登录</h3>
          <el-tag :type="bootstrapInitialized ? 'success' : 'warning'">
            {{ bootstrapInitialized ? "已初始化" : "未初始化" }}
          </el-tag>
        </div>
        <el-form :model="superForm" label-width="100px" class="compact-form">
          <el-form-item label="账号">
            <el-input v-model="superForm.username" class="auth-input" placeholder="账号示例：super_admin" />
          </el-form-item>
          <el-form-item label="密码">
            <el-input v-model="superForm.password" class="auth-input" type="password" show-password />
          </el-form-item>
          <el-form-item>
            <el-button
              v-if="!bootstrapInitialized"
              plain
              :loading="loading.status"
              @click="loadBootstrapStatus"
            >
              检查初始化
            </el-button>
            <el-button
              v-if="!bootstrapInitialized"
              type="warning"
              :loading="loading.init"
              @click="bootstrapInit"
            >
              首次初始化
            </el-button>
            <el-button type="primary" :loading="loading.login" @click="superLogin">登录超管</el-button>
          </el-form-item>
        </el-form>
      </section>

      <section class="session-card glass-card stagger-3 login-session-card">
        <div class="panel-headline">
          <h3>快捷入口</h3>
        </div>
        <div class="session-actions">
          <el-button plain @click="$emit('navigate', '/login')">返回普通登录中心</el-button>
          <el-button type="primary" :disabled="!session.superToken" @click="$emit('navigate', '/super-admin')">
            进入超级管理员后台
          </el-button>
        </div>
      </section>
    </section>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { parseApiError, superApi } from "../lib/http";
import { setSuperToken } from "../lib/session";

const props = defineProps({
  session: {
    type: Object,
    required: true,
  },
});

const emit = defineEmits(["navigate", "session-updated"]);

const bootstrapInitialized = ref(false);
const superForm = reactive({
  username: "",
  password: "",
});

const loading = reactive({
  status: false,
  init: false,
  login: false,
});

onMounted(async () => {
  await loadBootstrapStatus();
});

async function loadBootstrapStatus() {
  loading.status = true;
  try {
    const response = await superApi.bootstrapStatus();
    bootstrapInitialized.value = !!response.initialized;
  } catch (error) {
    ElMessage.error(parseApiError(error));
  } finally {
    loading.status = false;
  }
}

async function bootstrapInit() {
  const username = superForm.username.trim();
  const password = superForm.password;
  if (!username || !password) {
    ElMessage.warning("请输入超管账号和密码");
    return;
  }
  loading.init = true;
  try {
    await superApi.bootstrapInit({ username, password });
    ElMessage.success("超管初始化成功");
    await loadBootstrapStatus();
  } catch (error) {
    ElMessage.error(parseApiError(error));
  } finally {
    loading.init = false;
  }
}

async function superLogin() {
  const username = superForm.username.trim();
  const password = superForm.password;
  if (!username || !password) {
    ElMessage.warning("请输入超管账号和密码");
    return;
  }
  loading.login = true;
  try {
    const response = await superApi.login({ username, password });
    setSuperToken(response.token || "");
    emit("session-updated");
    ElMessage.success("超管登录成功");
    emit("navigate", "/super-admin");
  } catch (error) {
    ElMessage.error(parseApiError(error));
  } finally {
    loading.login = false;
  }
}
</script>
