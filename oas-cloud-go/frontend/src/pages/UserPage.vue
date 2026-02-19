<template>
  <div class="page-shell">
    <header class="console-header glass-card stagger-1">
      <div class="brand">
        <p class="eyebrow">用户工作台</p>
        <h1>普通用户页面</h1>
        <p class="subtitle">管理个人任务开关与执行时间，查看自己的任务执行日志。</p>
      </div>
      <div class="status-pills">
        <el-button plain @click="$emit('navigate', '/login')">返回登录页</el-button>
        <el-button type="danger" @click="logout">退出用户</el-button>
      </div>
    </header>

    <section class="workspace glass-card stagger-2">
      <UserPanel
        :token="session.userToken"
        :account-no="session.userAccountNo"
        @logout="logout"
      />
    </section>
  </div>
</template>

<script setup>
import UserPanel from "../components/user/UserPanel.vue";
import { clearUserSession } from "../lib/session";

defineProps({
  session: {
    type: Object,
    required: true,
  },
});

const emit = defineEmits(["navigate", "session-updated"]);

function logout() {
  clearUserSession({ keepAccountNo: true });
  emit("session-updated");
  emit("navigate", "/login");
}
</script>
