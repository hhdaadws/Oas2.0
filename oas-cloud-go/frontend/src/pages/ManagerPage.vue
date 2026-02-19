<template>
  <div class="page-shell">
    <header class="console-header glass-card stagger-1">
      <div class="brand">
        <p class="eyebrow">管理员工作台</p>
        <h1>管理员页面</h1>
        <p class="subtitle">管理下属用户、发放激活码、配置任务并查看执行日志。</p>
      </div>
      <div class="status-pills">
        <el-button plain @click="$emit('navigate', '/login')">返回登录页</el-button>
        <el-button type="danger" @click="logout">退出管理员</el-button>
      </div>
    </header>

    <section class="workspace glass-card stagger-2">
      <ManagerPanel :token="session.managerToken" @logout="logout" />
    </section>
  </div>
</template>

<script setup>
import ManagerPanel from "../components/manager/ManagerPanel.vue";
import { clearManagerToken } from "../lib/session";

defineProps({
  session: {
    type: Object,
    required: true,
  },
});

const emit = defineEmits(["navigate", "session-updated"]);

function logout() {
  clearManagerToken();
  emit("session-updated");
  emit("navigate", "/login");
}
</script>
