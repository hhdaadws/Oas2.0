<template>
  <div class="page-shell">
    <header class="console-header glass-card stagger-1">
      <div class="brand">
        <p class="eyebrow">超级管理员工作台</p>
        <h1>超级管理员管理后台</h1>
        <p class="subtitle">统一管理管理员生命周期、续费秘钥状态和治理策略。</p>
      </div>
      <div class="status-pills">
        <el-button plain @click="$emit('navigate', '/super-admin-login')">返回超管登录</el-button>
        <el-button type="danger" @click="logout">退出超管</el-button>
      </div>
    </header>

    <section class="workspace glass-card stagger-2">
      <SuperPanel :token="session.superToken" @logout="logout" />
    </section>
  </div>
</template>

<script setup>
import SuperPanel from "../components/super/SuperPanel.vue";
import { clearSuperToken } from "../lib/session";

defineProps({
  session: {
    type: Object,
    required: true,
  },
});

const emit = defineEmits(["navigate", "session-updated"]);

function logout() {
  clearSuperToken();
  emit("session-updated");
  emit("navigate", "/super-admin-login");
}
</script>

