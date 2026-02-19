<script setup>
import { ref } from "vue";
import RenewalKeysTab from "./RenewalKeysTab.vue";
import ManagersTab from "./ManagersTab.vue";

const props = defineProps({
  token: { type: String, default: "" },
});
defineEmits(["logout"]);

const activeTab = ref("keys");
</script>

<template>
  <div class="role-dashboard">
    <el-empty
      v-if="!token"
      class="empty-center"
      description="请先登录超级管理员，再进入治理页面"
      :image-size="100"
    >
      <el-button type="primary" @click="$emit('logout')">返回登录区</el-button>
    </el-empty>

    <template v-else>
      <el-tabs v-model="activeTab" class="module-tabs">
        <el-tab-pane label="秘钥中心" name="keys">
          <RenewalKeysTab :token="token" />
        </el-tab-pane>
        <el-tab-pane label="管理员管理" name="managers">
          <ManagersTab :token="token" />
        </el-tab-pane>
      </el-tabs>
    </template>
  </div>
</template>
