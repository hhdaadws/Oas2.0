<template>
  <div class="page-shell page-shell--login">
    <header class="console-header glass-card stagger-1">
      <div class="brand">
        <p class="eyebrow">云端指令中心</p>
        <h1>OAS 云端登录中心</h1>
      </div>
    </header>

    <section class="login-center-wrap">
      <section class="auth-card glass-card stagger-2 login-center-card">
      <el-tabs v-model="activeAuthTab" class="module-tabs">
        <el-tab-pane label="管理员登录" name="manager">
          <div class="panel-headline">
            <h3>管理员登录</h3>
            <el-tag type="success" v-if="session.managerToken">已登录</el-tag>
          </div>

          <el-form :model="managerForm" label-width="100px" class="compact-form">
            <el-form-item label="账号">
              <el-input v-model="managerForm.username" class="auth-input" placeholder="账号示例：mgr_001" clearable />
            </el-form-item>
            <el-form-item label="密码">
              <el-input v-model="managerForm.password" class="auth-input" type="password" show-password />
            </el-form-item>
            <el-form-item>
              <el-button type="warning" :loading="loading.managerRegister" @click="registerManager">公共注册</el-button>
              <el-button type="primary" :loading="loading.managerLogin" @click="loginManager">登录并进入</el-button>
            </el-form-item>
          </el-form>
          <el-alert
            type="info"
            :closable="false"
            title="管理员注册后默认过期，请登录后在管理员页面兑换续费秘钥。"
          />
        </el-tab-pane>

        <el-tab-pane label="普通用户登录" name="user">
          <div class="panel-headline">
            <h3>普通用户登录</h3>
            <el-tag type="success" v-if="session.userToken">已登录</el-tag>
          </div>

          <el-form :model="userForm" label-width="100px" class="compact-form">
            <el-form-item label="激活码注册">
              <el-input v-model="userForm.registerCode" class="auth-input" placeholder="激活码示例：uac_xxx" clearable />
            </el-form-item>
            <el-form-item>
              <el-button type="warning" :loading="loading.userRegister" @click="registerUserByCode">
                注册并进入
              </el-button>
            </el-form-item>

            <el-divider />

            <el-form-item label="账号登录">
              <el-input v-model="userForm.accountNo" class="auth-input" placeholder="账号示例：U2026..." clearable />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="loading.userLogin" @click="loginUser">登录并进入</el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>
      </el-tabs>
      </section>

      <section class="session-card glass-card stagger-4 login-session-card">
        <div class="panel-headline">
          <h3>当前会话</h3>
        </div>
        <div class="session-actions">
          <el-button
            type="primary"
            plain
            :disabled="!session.managerToken"
            @click="$emit('navigate', '/manager')"
          >
            进入管理员页面
          </el-button>
          <el-button
            type="success"
            plain
            :disabled="!session.userToken"
            @click="$emit('navigate', '/user')"
          >
            进入普通用户页面
          </el-button>
        </div>
      </section>
    </section>
  </div>
</template>

<script setup>
import { reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { managerApi, parseApiError, userApi } from "../lib/http";
import { setManagerToken, setUserSession } from "../lib/session";

const props = defineProps({
  session: {
    type: Object,
    required: true,
  },
});

const emit = defineEmits(["navigate", "session-updated"]);
const activeAuthTab = ref("manager");

const managerForm = reactive({
  username: "",
  password: "",
});

const userForm = reactive({
  registerCode: "",
  accountNo: props.session.userAccountNo || "",
});

const loading = reactive({
  managerRegister: false,
  managerLogin: false,
  userRegister: false,
  userLogin: false,
});

async function registerManager() {
  const username = managerForm.username.trim();
  const password = managerForm.password;
  if (!username || !password) {
    ElMessage.warning("请输入管理员账号和密码");
    return;
  }
  loading.managerRegister = true;
  try {
    await managerApi.register({ username, password });
    ElMessage.success("管理员注册成功，请先续费后登录");
  } catch (error) {
    ElMessage.error(parseApiError(error));
  } finally {
    loading.managerRegister = false;
  }
}

async function loginManager() {
  const username = managerForm.username.trim();
  const password = managerForm.password;
  if (!username || !password) {
    ElMessage.warning("请输入管理员账号和密码");
    return;
  }
  loading.managerLogin = true;
  try {
    const response = await managerApi.login({ username, password });
    setManagerToken(response.token || "");
    emit("session-updated");
    ElMessage.success("管理员登录成功");
    emit("navigate", "/manager");
  } catch (error) {
    ElMessage.error(parseApiError(error));
  } finally {
    loading.managerLogin = false;
  }
}

async function registerUserByCode() {
  const code = userForm.registerCode.trim();
  if (!code) {
    ElMessage.warning("请输入用户激活码");
    return;
  }
  loading.userRegister = true;
  try {
    const response = await userApi.registerByCode({ code });
    setUserSession(response.token || "", response.account_no || "");
    userForm.accountNo = response.account_no || "";
    emit("session-updated");
    ElMessage.success("普通用户注册并登录成功");
    emit("navigate", "/user");
  } catch (error) {
    ElMessage.error(parseApiError(error));
  } finally {
    loading.userRegister = false;
  }
}

async function loginUser() {
  const accountNo = userForm.accountNo.trim();
  if (!accountNo) {
    ElMessage.warning("请输入普通用户账号");
    return;
  }
  loading.userLogin = true;
  try {
    const response = await userApi.login({ account_no: accountNo });
    setUserSession(response.token || "", response.account_no || accountNo);
    emit("session-updated");
    ElMessage.success("普通用户登录成功");
    emit("navigate", "/user");
  } catch (error) {
    ElMessage.error(parseApiError(error));
  } finally {
    loading.userLogin = false;
  }
}
</script>
