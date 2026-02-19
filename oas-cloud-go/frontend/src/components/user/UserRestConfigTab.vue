<template>
  <section class="panel-card">
    <h3>休息配置</h3>
    <el-form :model="form" label-width="110px" style="margin-top:12px;max-width:420px">
      <el-form-item label="启用休息">
        <el-switch v-model="form.enabled" />
      </el-form-item>
      <el-form-item label="模式">
        <el-select v-model="form.mode">
          <el-option label="随机" value="random" />
          <el-option label="自定义" value="custom" />
        </el-select>
      </el-form-item>
      <template v-if="form.mode === 'custom'">
        <el-form-item label="休息开始时间">
          <el-time-select v-model="form.rest_start" start="00:00" end="23:30" step="00:30" />
        </el-form-item>
        <el-form-item label="休息时长(分)">
          <el-input-number v-model="form.rest_duration" :min="0" :max="1440" />
        </el-form-item>
      </template>
      <el-form-item>
        <el-button plain :loading="loading" @click="load">刷新</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </el-form-item>
    </el-form>
  </section>
</template>

<script setup>
import { reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { userApi, parseApiError } from "../../lib/http";

const props = defineProps({ token: { type: String, default: "" } });
const loading = ref(false);
const saving = ref(false);
const form = reactive({ enabled: false, mode: "random", rest_start: "00:00", rest_duration: 60 });

async function load() {
  if (!props.token) return;
  loading.value = true;
  try {
    const res = await userApi.getMeRestConfig(props.token);
    form.enabled = res.enabled ?? false;
    form.mode = res.mode || "random";
    form.rest_start = res.rest_start || "00:00";
    form.rest_duration = res.rest_duration ?? 60;
  } catch (e) {
    ElMessage.error(parseApiError(e));
  } finally {
    loading.value = false;
  }
}

async function save() {
  saving.value = true;
  try {
    await userApi.putMeRestConfig(props.token, { ...form });
    ElMessage.success("休息配置已保存");
  } catch (e) {
    ElMessage.error(parseApiError(e));
  } finally {
    saving.value = false;
  }
}

watch(() => props.token, (val) => { if (val) load(); }, { immediate: true });
</script>
