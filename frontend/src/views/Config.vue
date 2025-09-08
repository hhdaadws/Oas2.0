<template>
  <div class="config">
    <el-tabs v-model="activeTab">
      <!-- ADB配置 -->
      <el-tab-pane label="ADB配置" name="adb">
        <el-card>
          <el-form :model="config.adb" label-width="120px">
            <el-form-item label="ADB路径">
              <el-input v-model="config.adb.path" placeholder="如: adb" />
            </el-form-item>
            <el-form-item label="启动方式">
              <el-select v-model="config.adb.start_method">
                <el-option label="Monkey命令" value="monkey" />
                <el-option label="AM Start" value="am_start" />
                <el-option label="Intent启动" value="intent" />
              </el-select>
              <div class="config-description">
                <p><strong>Monkey</strong>: 模拟用户启动，兼容性最好</p>
                <p><strong>AM Start</strong>: 直接启动Activity，速度快</p>
                <p><strong>Intent</strong>: 通过Intent启动，标准方式</p>
              </div>
            </el-form-item>
            <el-form-item label="应用包名">
              <el-input v-model="config.adb.package" placeholder="com.netease.onmyoji" />
            </el-form-item>
            <el-form-item label="主Activity">
              <el-input v-model="config.adb.activity" placeholder="com.netease.onmyoji.Onmyoji" />
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>
      
      <!-- 截图配置 -->
      <el-tab-pane label="截图配置" name="capture">
        <el-card>
          <el-form :model="config.capture" label-width="120px">
            <el-form-item label="截图方式">
              <el-select v-model="config.capture.method">
                <el-option label="ADB截图" value="adb" />
                <el-option label="IPC截图" value="ipc" />
              </el-select>
              <div class="config-description">
                <p><strong>ADB截图</strong>: 兼容性好，速度较慢</p>
                <p><strong>IPC截图</strong>: 速度快，需要特殊支持</p>
              </div>
            </el-form-item>
            <el-form-item label="图像质量">
              <el-slider v-model="config.capture.quality" :min="50" :max="100" show-input />
              <div class="config-description">质量越高文件越大，识别越准确</div>
            </el-form-item>
            <el-form-item label="截图超时">
              <el-input-number v-model="config.capture.timeout" :min="5" :max="30" />
              <span style="margin-left: 10px">秒</span>
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>
      
      <!-- 识别配置 -->
      <el-tab-pane label="识别配置" name="recognition">
        <el-card>
          <el-form :model="config.recognition" label-width="120px">
            <el-form-item label="模板匹配阈值">
              <el-slider v-model="config.recognition.template_threshold" :min="0.5" :max="1.0" :step="0.05" show-input />
              <div class="config-description">阈值越高要求匹配越精确</div>
            </el-form-item>
            <el-form-item label="OCR语言">
              <el-select v-model="config.recognition.ocr_language">
                <el-option label="中文" value="ch" />
                <el-option label="英文" value="en" />
                <el-option label="中英文" value="ch_en" />
              </el-select>
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>
      
      <!-- 任务配置 -->
      <el-tab-pane label="任务配置" name="task">
        <el-card>
          <el-form :model="config.task" label-width="120px">
            <el-form-item label="任务超时">
              <el-input-number v-model="config.task.timeout" :min="60" :max="600" />
              <span style="margin-left: 10px">秒</span>
            </el-form-item>
            <el-form-item label="重试次数">
              <el-input-number v-model="config.task.retry_count" :min="1" :max="10" />
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>
      
      <!-- 调度配置 -->
      <el-tab-pane label="调度配置" name="schedule">
        <el-card>
          <el-form :model="config.schedule" label-width="120px">
            <el-form-item label="全局休息开始">
              <el-time-picker v-model="config.schedule.global_rest_start" format="HH:mm" value-format="HH:mm" />
            </el-form-item>
            <el-form-item label="全局休息结束">
              <el-time-picker v-model="config.schedule.global_rest_end" format="HH:mm" value-format="HH:mm" />
            </el-form-item>
            <el-form-item label="体力阈值">
              <el-input-number v-model="config.schedule.stamina_threshold" :min="100" :max="2000" />
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>
    </el-tabs>
    
    <!-- 保存按钮 -->
    <div style="margin-top: 20px; text-align: center">
      <el-button type="primary" @click="saveConfig" size="large">
        保存配置
      </el-button>
      <el-button @click="resetConfig" size="large">
        重置配置
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { apiRequest } from '@/config'

// 数据
const activeTab = ref('adb')
const config = reactive({
  adb: {
    path: 'adb',
    start_method: 'monkey',
    package: 'com.netease.onmyoji',
    activity: 'com.netease.onmyoji.Onmyoji'
  },
  capture: {
    method: 'adb',
    quality: 80,
    timeout: 10
  },
  recognition: {
    template_threshold: 0.8,
    ocr_language: 'ch'
  },
  task: {
    timeout: 300,
    retry_count: 3
  },
  schedule: {
    global_rest_start: '00:00',
    global_rest_end: '06:00',
    stamina_threshold: 1000
  }
})

// 获取配置
const fetchConfig = async () => {
  try {
    const response = await apiRequest('/api/config/')
    const data = await response.json()
    
    // 更新本地配置
    Object.assign(config, data)
  } catch (error) {
    console.error('获取配置失败:', error)
    ElMessage.error('获取配置失败')
  }
}

// 保存配置
const saveConfig = async () => {
  try {
    const response = await apiRequest('/api/config/', {
      method: 'PUT',
      body: JSON.stringify(config)
    })
    
    if (response.ok) {
      ElMessage.success('配置保存成功')
    } else {
      throw new Error('保存失败')
    }
  } catch (error) {
    console.error('保存配置失败:', error)
    ElMessage.error('保存配置失败')
  }
}

// 重置配置
const resetConfig = () => {
  Object.assign(config, {
    adb: {
      path: 'adb',
      start_method: 'monkey',
      package: 'com.netease.onmyoji',
      activity: 'com.netease.onmyoji.Onmyoji'
    },
    capture: {
      method: 'adb',
      quality: 80,
      timeout: 10
    },
    recognition: {
      template_threshold: 0.8,
      ocr_language: 'ch'
    },
    task: {
      timeout: 300,
      retry_count: 3
    },
    schedule: {
      global_rest_start: '00:00',
      global_rest_end: '06:00',
      stamina_threshold: 1000
    }
  })
  
  ElMessage.info('配置已重置')
}

onMounted(() => {
  fetchConfig()
})
</script>

<style scoped lang="scss">
.config {
  .config-description {
    margin-top: 8px;
    font-size: 12px;
    color: #909399;
    
    p {
      margin: 2px 0;
    }
  }
}
</style>