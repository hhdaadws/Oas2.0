<template>
  <div class="login-container">
    <el-card class="login-card" shadow="hover">
      <template #header>
        <div class="login-header">
          <h2>阴阳师调度系统</h2>
          <p>{{ loginHeaderTip }}</p>
        </div>
      </template>

      <el-form
        ref="loginFormRef"
        :model="loginForm"
        :rules="activeRules"
        @submit.prevent="handleLogin"
      >
        <el-form-item prop="mode">
          <el-radio-group v-model="loginForm.mode" size="large">
            <el-radio-button label="local">本地模式</el-radio-button>
            <el-radio-button label="cloud">云端模式</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <el-form-item v-if="loginForm.mode === 'local' && canAutoLoginLocal">
          <el-alert
            title="检测到24小时内本地登录状态，点击下方按钮可自动登录"
            type="success"
            :closable="false"
            show-icon
          />
        </el-form-item>

        <el-form-item v-else-if="loginForm.mode === 'local'" prop="code">
          <el-input
            v-model="loginForm.code"
            placeholder="请输入6位验证码"
            maxlength="6"
            size="large"
            :prefix-icon="Lock"
            @keyup.enter="handleLogin"
            autofocus
          />
        </el-form-item>

        <el-form-item v-if="loginForm.mode === 'cloud'" prop="username">
          <el-input
            v-model="loginForm.username"
            placeholder="请输入管理员账号"
            size="large"
            autocomplete="username"
            @keyup.enter="handleLogin"
          />
        </el-form-item>

        <el-form-item v-if="loginForm.mode === 'cloud'" prop="password">
          <el-input
            v-model="loginForm.password"
            type="password"
            placeholder="请输入管理员密码"
            size="large"
            autocomplete="current-password"
            show-password
            @keyup.enter="handleLogin"
          />
        </el-form-item>

        <el-form-item v-if="loginForm.mode === 'cloud'">
          <el-checkbox v-model="rememberCredentials">记住账号密码</el-checkbox>
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            size="large"
            :loading="loading"
            style="width: 100%"
            @click="handleLogin"
          >
            {{ loginButtonText }}
          </el-button>
        </el-form-item>
      </el-form>

      <div class="login-tip">
        <el-text type="info" size="small">
          {{ loginForm.mode === 'cloud' ? '云端模式会从云端拉取任务执行' : '请联系管理员获取验证码' }}
        </el-text>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { computed, ref, reactive, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Lock } from '@element-plus/icons-vue'
import { login, checkAuthStatus } from '@/api/auth'
import { setToken, setMode, getToken, getCloudCredentials, setCloudCredentials, removeCloudCredentials } from '@/api/request'

const router = useRouter()
const loginFormRef = ref(null)
const loading = ref(false)
const canAutoLoginLocal = ref(false)
const rememberCredentials = ref(false)

const loginForm = reactive({
  mode: 'local',
  code: '',
  username: '',
  password: ''
})

const loginRules = {
  mode: [
    { required: true, message: '请选择模式', trigger: 'change' }
  ],
  code: [
    { required: true, message: '请输入验证码', trigger: 'blur' },
    { pattern: /^\d{6}$/, message: '验证码必须是6位数字', trigger: 'blur' }
  ],
  username: [
    { required: true, message: '请输入管理员账号', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入管理员密码', trigger: 'blur' }
  ]
}

const loginHeaderTip = computed(() => {
  if (loginForm.mode === 'cloud') {
    return '请输入管理员账号密码（云端模式）'
  }
  if (canAutoLoginLocal.value) {
    return '24小时内免验证码，支持一键自动登录（本地模式）'
  }
  return '请输入验证码（本地模式）'
})

const loginButtonText = computed(() => {
  if (loginForm.mode === 'local' && canAutoLoginLocal.value) {
    return '自动登录'
  }
  return '登 录'
})

const activeRules = computed(() => {
  if (loginForm.mode === 'cloud') {
    return {
      mode: loginRules.mode,
      username: loginRules.username,
      password: loginRules.password
    }
  }
  if (canAutoLoginLocal.value) {
    return {
      mode: loginRules.mode
    }
  }
  return {
    mode: loginRules.mode,
    code: loginRules.code
  }
})

const refreshAutoLoginState = async () => {
  canAutoLoginLocal.value = false
  if (!getToken()) return

  try {
    const status = await checkAuthStatus()
    canAutoLoginLocal.value = status?.authenticated === true && status?.mode === 'local'
  } catch {
    canAutoLoginLocal.value = false
  }
}

onMounted(() => {
  const saved = getCloudCredentials()
  if (saved) {
    loginForm.mode = 'cloud'
    loginForm.username = saved.username
    loginForm.password = saved.password
    rememberCredentials.value = true
  }
  refreshAutoLoginState()
})

watch(
  () => loginForm.mode,
  async mode => {
    loginForm.code = ''
    if (loginFormRef.value) {
      loginFormRef.value.clearValidate()
    }

    if (mode === 'local') {
      loginForm.username = ''
      loginForm.password = ''
      await refreshAutoLoginState()
    } else {
      canAutoLoginLocal.value = false
      const saved = getCloudCredentials()
      if (saved) {
        loginForm.username = saved.username
        loginForm.password = saved.password
        rememberCredentials.value = true
      } else {
        loginForm.username = ''
        loginForm.password = ''
        rememberCredentials.value = false
      }
    }
  }
)

const handleLogin = async () => {
  if (!loginFormRef.value) return

  if (loginForm.mode === 'local' && canAutoLoginLocal.value) {
    ElMessage.success('已使用24小时内登录状态自动登录')
    router.push('/dashboard')
    return
  }

  try {
    await loginFormRef.value.validate()
  } catch {
    return
  }

  loading.value = true
  try {
    const payload = {
      mode: loginForm.mode
    }
    if (loginForm.mode === 'cloud') {
      payload.username = loginForm.username.trim()
      payload.password = loginForm.password
    } else {
      payload.code = loginForm.code.trim()
    }

    const res = await login(payload)
    setToken(res.token)
    setMode(res.mode || loginForm.mode)
    if (loginForm.mode === 'cloud') {
      if (rememberCredentials.value) {
        setCloudCredentials(payload.username, payload.password)
      } else {
        removeCloudCredentials()
      }
    }
    canAutoLoginLocal.value = res.mode === 'local'
    ElMessage.success('登录成功')
    router.push('/dashboard')
  } catch (err) {
    loginForm.code = ''
    loginForm.password = ''
  } finally {
    loading.value = false
  }
}
</script>

<style scoped lang="scss">
.login-container {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.login-card {
  width: 400px;

  .login-header {
    text-align: center;

    h2 {
      margin: 0 0 8px 0;
      color: #303133;
    }

    p {
      margin: 0;
      color: #909399;
      font-size: 14px;
    }
  }
}

.login-tip {
  text-align: center;
  margin-top: 10px;
}
</style>
