<script setup>
import { ref } from "vue";
import AccountTab from "./AccountTab.vue";
import TasksTab from "./TasksTab.vue";
import UserLogsTab from "./UserLogsTab.vue";
import UserRestConfigTab from "./UserRestConfigTab.vue";

const props = defineProps({
  token: { type: String, default: "" },
  accountNo: { type: String, default: "" },
});
defineEmits(["logout"]);

const activeTab = ref("account");
</script>

<template>
  <div class="role-dashboard">
    <el-empty
      v-if="!token"
      class="empty-center"
      description="请先登录普通用户，再进入个人中心"
      :image-size="100"
    >
      <el-button type="primary" @click="$emit('logout')">返回登录区</el-button>
    </el-empty>

    <template v-else>
      <el-tabs v-model="activeTab" class="module-tabs">
        <el-tab-pane label="账号与续费" name="account">
          <AccountTab :token="token" :account-no="accountNo" @logout="$emit('logout')" />
        </el-tab-pane>
        <el-tab-pane label="任务配置" name="tasks">
          <TasksTab :token="token" />
        </el-tab-pane>
        <el-tab-pane label="执行日志" name="logs">
          <UserLogsTab :token="token" />
        </el-tab-pane>
        <el-tab-pane label="休息配置" name="rest">
          <UserRestConfigTab :token="token" />
        </el-tab-pane>
      </el-tabs>
    </template>
  </div>
</template>
