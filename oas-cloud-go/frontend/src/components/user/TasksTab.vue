<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { parseApiError, userApi } from "../../lib/http";
import { userTypeLabel, isHHmmPattern, ensureTaskConfig, parseTaskConfigFromRaw } from "../../lib/helpers";
import { useTaskTemplates } from "../../composables/useTaskTemplates";

const props = defineProps({
  token: { type: String, default: "" },
});

const loading = reactive({ tasks: false, saveTasks: false });
const taskConfigRaw = ref("{}");
const taskRows = ref([]);
const { templateCache, ensureTaskTemplates } = useTaskTemplates();

const userType = ref("daily");

const currentTemplate = computed(() => {
  return templateCache[userType.value] || { order: [], defaultConfig: {} };
});

function buildTaskRows(config) {
  const tpl = currentTemplate.value;
  taskRows.value = tpl.order.map((name) => {
    const cfg = reactive(ensureTaskConfig(config[name]));
    return {
      name,
      config: cfg,
      _nextTimeMode: isHHmmPattern(cfg.next_time) ? "daily" : "datetime",
    };
  });
}

function stringifyTaskConfig(config) {
  taskConfigRaw.value = JSON.stringify(config || {}, null, 2);
}

function applyTaskConfigFromRaw() {
  const config = parseTaskConfigFromRaw(taskConfigRaw.value);
  buildTaskRows(config);
  ElMessage.success("已从 JSON 同步到任务表格");
}

watch(
  () => props.token,
  async (value) => {
    if (!value) { taskConfigRaw.value = "{}"; taskRows.value = []; return; }
    await loadMeTasks();
  },
  { immediate: true },
);

onMounted(async () => {
  if (props.token) await loadMeTasks();
});

async function loadMeTasks() {
  loading.tasks = true;
  try {
    const response = await userApi.getMeTasks(props.token);
    const ut = response.user_type || "daily";
    userType.value = ut;
    const template = await ensureTaskTemplates(ut);
    const merged = {
      ...(template.defaultConfig || {}),
      ...(response.task_config || {}),
    };
    buildTaskRows(merged);
    stringifyTaskConfig(merged);
  } catch (error) {
    ElMessage.error(parseApiError(error));
  } finally {
    loading.tasks = false;
  }
}

async function saveMeTasks() {
  const normalizedConfig = {};
  taskRows.value.forEach((row) => {
    normalizedConfig[row.name] = {
      ...(row.config || {}),
      enabled: row.config.enabled === true,
    };
  });

  loading.saveTasks = true;
  try {
    const response = await userApi.putMeTasks(props.token, { task_config: normalizedConfig });
    userType.value = response.user_type || userType.value || "daily";
    const savedConfig = response.task_config || normalizedConfig;
    buildTaskRows(savedConfig);
    stringifyTaskConfig(savedConfig);
    ElMessage.success("任务配置保存成功");
  } catch (error) {
    ElMessage.error(parseApiError(error));
  } finally {
    loading.saveTasks = false;
  }
}
</script>

<template>
  <article class="panel-card">
    <div class="panel-headline">
      <h3>我的任务配置（{{ userTypeLabel(userType) }}）</h3>
      <div class="row-actions">
        <el-button plain :loading="loading.tasks" @click="loadMeTasks">加载</el-button>
        <el-button type="primary" :loading="loading.saveTasks" @click="saveMeTasks">保存</el-button>
      </div>
    </div>
    <div class="data-table-wrapper">
      <el-table :data="taskRows" border stripe empty-text="暂无可配置任务">
        <el-table-column prop="name" label="任务类型" min-width="170" />
        <el-table-column label="启用" width="100">
          <template #default="scope">
            <el-switch v-model="scope.row.config.enabled" />
          </template>
        </el-table-column>
        <el-table-column label="执行时间" min-width="280">
          <template #default="scope">
            <div class="next-time-row">
              <el-radio-group
                v-model="scope.row._nextTimeMode"
                size="small"
                @change="(mode) => { if (mode === 'daily' && !isHHmmPattern(scope.row.config.next_time)) scope.row.config.next_time = '08:00'; }"
              >
                <el-radio-button value="daily">每日</el-radio-button>
                <el-radio-button value="datetime">指定</el-radio-button>
              </el-radio-group>
              <el-time-select
                v-if="scope.row._nextTimeMode === 'daily'"
                v-model="scope.row.config.next_time"
                start="00:00" end="23:30" step="00:30"
                placeholder="时:分" size="small" style="width: 100px"
              />
              <el-date-picker
                v-else
                v-model="scope.row.config.next_time"
                type="datetime" value-format="YYYY-MM-DD HH:mm"
                placeholder="选择日期时间" size="small" style="width: 170px"
              />
            </div>
          </template>
        </el-table-column>
        <el-table-column label="失败延迟(分)" width="130">
          <template #default="scope">
            <el-input-number v-model="scope.row.config.fail_delay" :min="0" :max="100000" size="small" />
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-collapse class="collapse-section">
      <el-collapse-item title="高级配置编辑（完整字段）" name="json">
        <el-input
          v-model="taskConfigRaw"
          type="textarea"
          :rows="12"
          placeholder='{"签到":{"enabled":true,"next_time":"09:00"}}'
        />
        <el-button type="primary" plain style="margin-top: 8px" @click="applyTaskConfigFromRaw">应用配置</el-button>
      </el-collapse-item>
    </el-collapse>
    <p class="tip-text">系统会按用户类型过滤任务，并按"默认 + 现有 + 提交"合并更新。</p>
  </article>
</template>
