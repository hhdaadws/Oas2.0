<template>
  <div class="role-dashboard">
    <el-empty
      v-if="!token"
      class="empty-center"
      description="请先登录管理员，再进入下属管理页面"
      :image-size="100"
    >
      <el-button type="primary" @click="$emit('logout')">返回登录区</el-button>
    </el-empty>

    <template v-else>
      <el-tabs v-model="activeTab" class="module-tabs">
        <el-tab-pane label="总览" name="overview">
          <OverviewTab :token="token" />
        </el-tab-pane>

        <el-tab-pane label="激活码管理" name="codes">
          <ActivationCodesTab :token="token" />
        </el-tab-pane>

        <el-tab-pane label="下属配置" name="users">
          <UsersTab
            :token="token"
            :selected-user-id="selectedUserId"
            :selected-user-type="selectedUserType"
            :selected-user-account-no="selectedUserAccountNo"
            :selected-user-status="selectedUserStatus"
            :selected-user-expires-at="selectedUserExpiresAt"
            :template-cache="templateCache"
            :ensure-task-templates="ensureTaskTemplates"
            @user-selected="onUserSelected"
          />
        </el-tab-pane>

        <el-tab-pane label="执行日志" name="logs">
          <UserLogsTab
            :token="token"
            :selected-user-id="selectedUserId"
            :selected-user-account-no="selectedUserAccountNo"
          />
        </el-tab-pane>

        <el-tab-pane label="仪表盘" name="dashboard">
          <DashboardTab :token="token" />
        </el-tab-pane>

        <el-tab-pane label="勾协管理" name="coop">
          <CoopTab :token="token" />
        </el-tab-pane>
      </el-tabs>
    </template>
  </div>
</template>

<script setup>
import { ref, watch } from "vue";
import { useTaskTemplates } from "../../composables/useTaskTemplates";
import OverviewTab from "./OverviewTab.vue";
import ActivationCodesTab from "./ActivationCodesTab.vue";
import UsersTab from "./UsersTab.vue";
import UserLogsTab from "./UserLogsTab.vue";
import DashboardTab from "./DashboardTab.vue";
import CoopTab from "./CoopTab.vue";

const props = defineProps({
  token: {
    type: String,
    default: "",
  },
});

defineEmits(["logout"]);

const activeTab = ref("overview");
const selectedUserId = ref(0);
const selectedUserType = ref("daily");
const selectedUserAccountNo = ref("");
const selectedUserStatus = ref("");
const selectedUserExpiresAt = ref("");

const { templateCache, ensureTaskTemplates } = useTaskTemplates();

function onUserSelected(row) {
  selectedUserId.value = row.id;
  selectedUserType.value = row.user_type || "daily";
  selectedUserAccountNo.value = row.account_no || "";
  selectedUserStatus.value = row.status || "";
  selectedUserExpiresAt.value = row.expires_at || "";
}

watch(
  () => props.token,
  (value) => {
    if (!value) {
      selectedUserId.value = 0;
      selectedUserType.value = "daily";
      selectedUserAccountNo.value = "";
      selectedUserStatus.value = "";
      selectedUserExpiresAt.value = "";
      activeTab.value = "overview";
    }
  },
);
</script>
