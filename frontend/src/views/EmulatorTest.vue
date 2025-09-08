<template>
  <div class="emu-test">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>模拟器测试</span>
          <div class="actions">
            <el-button @click="goBack" link>
              <el-icon><ArrowLeft /></el-icon>
              返回配置
            </el-button>
          </div>
        </div>
      </template>

      <el-form :inline="true" class="toolbar">
        <el-form-item label="选择模拟器">
          <el-select v-model="selectedId" placeholder="请选择" style="width: 220px" @change="onEmuChange">
            <el-option v-for="e in emulators" :key="e.id" :label="`${e.name} (${e.adb_addr})`" :value="e.id" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :disabled="!selectedId" @click="refreshScreenshot">
            <el-icon><Camera /></el-icon>
            获取截图
          </el-button>
        </el-form-item>
        <el-form-item label="截图方式">
          <el-radio-group v-model="shotMethod">
            <el-radio label="adb">ADB</el-radio>
            <el-radio label="ipc">IPC</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="启动方式">
          <el-radio-group v-model="launchMode">
            <el-radio label="adb_monkey">ADB Monkey</el-radio>
            <el-radio label="adb_intent">ADB Intent</el-radio>
            <el-radio label="am_start">AM Start</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="launchMode==='adb_intent' || launchMode==='am_start'" label="Activity">
          <el-input v-model="activity" placeholder=".MainActivity" style="width: 200px" />
        </el-form-item>
        <el-form-item>
          <el-button type="success" :disabled="!selectedId" @click="startGame">
            <el-icon><VideoPlay /></el-icon>
            启动游戏
          </el-button>
        </el-form-item>
        <el-form-item label="X">
          <el-input-number v-model="clickX" :min="0" :max="10000" :step="10" />
        </el-form-item>
        <el-form-item label="Y">
          <el-input-number v-model="clickY" :min="0" :max="10000" :step="10" />
        </el-form-item>
        <el-form-item>
          <el-button :disabled="!selectedId" @click="sendClick">
            <el-icon><Pointer /></el-icon>
            发送点击
          </el-button>
        </el-form-item>
      </el-form>

      <el-alert type="info" show-icon :closable="false" style="margin-bottom: 12px;">
        <template #title>
          点击图片可直接在对应位置发送点击（自动按缩放换算坐标）。
        </template>
      </el-alert>

      <div class="work-area">
        <div class="canvas-wrap" v-loading="loading">
          <div v-if="screenshotUrl" class="image-stage" ref="stageRef">
            <img
              :src="screenshotUrl"
              ref="imgRef"
              @load="onImageLoad"
              @pointerdown="startSelection"
              @pointermove="updateSelection"
              @pointerup="endSelection"
              class="emu-image"
              alt="screenshot"
            />
            <div
              v-if="isSelecting || hasSelection"
              class="selection"
              :style="selectionStyle"
            ></div>
          </div>
          <el-empty v-else description="暂无截图，请先选择模拟器并点击获取截图" />
        </div>
        <div class="side-panel">
          <div class="roi-form">
            <div class="roi-title">区域截取</div>
            <el-form :inline="true">
              <el-form-item label="x"><el-input-number v-model="roi.x" :min="0" /></el-form-item>
              <el-form-item label="y"><el-input-number v-model="roi.y" :min="0" /></el-form-item>
              <el-form-item label="w"><el-input-number v-model="roi.w" :min="0" /></el-form-item>
              <el-form-item label="h"><el-input-number v-model="roi.h" :min="0" /></el-form-item>
              <el-form-item>
                <el-button :disabled="!screenshotUrl" @click="makeRoiPreview">
                  <el-icon><Crop /></el-icon>
                  生成预览
                </el-button>
              </el-form-item>
            </el-form>
            <div class="roi-preview" v-if="roiPreviewUrl">
              <img :src="roiPreviewUrl" alt="roi" />
            </div>
          </div>
        </div>
      </div>
    </el-card>
  </div>
  
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { API_ENDPOINTS, buildApiUrl, apiRequest } from '@/config'

const router = useRouter()

const emulators = ref([])
const selectedId = ref(null)
const screenshotUrl = ref('')
const loading = ref(false)
const imgRef = ref(null)
const imgNatural = ref({ w: 0, h: 0 })
const clickX = ref(0)
const clickY = ref(0)
const shotMethod = ref('adb')
const launchMode = ref('adb_monkey')
const activity = ref('.MainActivity')
const stageRef = ref(null)
const isSelecting = ref(false)
const hasSelection = ref(false)
const selStart = ref({ x: 0, y: 0 })
const selEnd = ref({ x: 0, y: 0 })
const roi = ref({ x: 0, y: 0, w: 0, h: 0 })
const roiPreviewUrl = ref('')

const goBack = () => router.push('/emulators')

const fetchEmulators = async () => {
  try {
    const resp = await apiRequest(API_ENDPOINTS.emulators)
    const data = await resp.json()
    emulators.value = data
    if (!selectedId.value && data.length) {
      selectedId.value = data[0].id
    }
  } catch (e) {
    ElMessage.error('获取模拟器列表失败')
  }
}

const fetchSystem = async () => {
  try {
    const resp = await apiRequest(API_ENDPOINTS.system.settings)
    const data = await resp.json()
    if (data?.launch_mode) launchMode.value = data.launch_mode
    if (data?.activity_name) activity.value = data.activity_name
  } catch {}
}

const onEmuChange = () => {
  screenshotUrl.value = ''
}

const refreshScreenshot = async () => {
  if (!selectedId.value) return
  loading.value = true
  try {
    const url = buildApiUrl(API_ENDPOINTS.emulatorScreenshot(selectedId.value)) + `?method=${shotMethod.value}`
    const resp = await fetch(url)
    if (!resp.ok) {
      // 尝试读取错误详情
      const ct = resp.headers.get('content-type') || ''
      if (ct.includes('application/json')) {
        const err = await resp.json().catch(() => null)
        throw new Error(err?.detail || '拉取截图失败')
      } else {
        const text = await resp.text().catch(() => '')
        throw new Error(text || '拉取截图失败')
      }
    }
    const blob = await resp.blob()
    if (screenshotUrl.value) URL.revokeObjectURL(screenshotUrl.value)
    screenshotUrl.value = URL.createObjectURL(blob)
    // 清除已有选区
    hasSelection.value = false
    roiPreviewUrl.value = ''
  } catch (e) {
    ElMessage.error(e.message || '拉取截图失败')
  } finally {
    loading.value = false
  }
}

const onImageLoad = () => {
  const img = imgRef.value
  if (!img) return
  imgNatural.value = { w: img.naturalWidth, h: img.naturalHeight }
}

const onImageClick = async (evt) => {
  // 保留函数名，若后续需要单击触发点击
}

const sendClick = async () => {
  if (!selectedId.value) return
  try {
    const resp = await apiRequest(API_ENDPOINTS.emulatorClick(selectedId.value), {
      method: 'POST',
      body: JSON.stringify({ x: clickX.value, y: clickY.value })
    })
    if (!resp.ok) throw new Error('click failed')
    ElMessage.success(`已点击 (${clickX.value}, ${clickY.value})`)
  } catch (e) {
    ElMessage.error('发送点击失败')
  }
}

const startGame = async () => {
  if (!selectedId.value) return
  try {
    const resp = await apiRequest(API_ENDPOINTS.emulatorLaunch(selectedId.value), {
      method: 'POST',
      body: JSON.stringify({ mode: launchMode.value, activity: activity.value })
    })
    const data = await resp.json().catch(() => ({}))
    if (!resp.ok) throw new Error(data?.detail || '启动失败')
    ElMessage.success(`启动成功（${launchMode.value}）`) 
  } catch (e) {
    ElMessage.error(e.message || '启动失败')
  }
}

// 选区交互
const startSelection = (evt) => {
  if (!imgRef.value) return
  isSelecting.value = true
  const rect = imgRef.value.getBoundingClientRect()
  selStart.value = { x: evt.clientX - rect.left, y: evt.clientY - rect.top }
  selEnd.value = { ...selStart.value }
}
const updateSelection = (evt) => {
  if (!isSelecting.value || !imgRef.value) return
  const rect = imgRef.value.getBoundingClientRect()
  selEnd.value = { x: evt.clientX - rect.left, y: evt.clientY - rect.top }
}
const endSelection = () => {
  if (!isSelecting.value || !imgRef.value) return
  isSelecting.value = false
  hasSelection.value = true
  // 写入 roi（原图坐标）
  const rect = imgRef.value.getBoundingClientRect()
  const x1 = Math.max(0, Math.min(selStart.value.x, selEnd.value.x))
  const y1 = Math.max(0, Math.min(selStart.value.y, selEnd.value.y))
  const x2 = Math.max(0, Math.max(selStart.value.x, selEnd.value.x))
  const y2 = Math.max(0, Math.max(selStart.value.y, selEnd.value.y))
  const scaleX = imgNatural.value.w / rect.width
  const scaleY = imgNatural.value.h / rect.height
  roi.value = {
    x: Math.round(x1 * scaleX),
    y: Math.round(y1 * scaleY),
    w: Math.round((x2 - x1) * scaleX),
    h: Math.round((y2 - y1) * scaleY)
  }
}

const selectionStyle = computed(() => {
  if (!imgRef.value) return {}
  const x1 = Math.min(selStart.value.x, selEnd.value.x)
  const y1 = Math.min(selStart.value.y, selEnd.value.y)
  const x2 = Math.max(selStart.value.x, selEnd.value.x)
  const y2 = Math.max(selStart.value.y, selEnd.value.y)
  const w = Math.max(0, x2 - x1)
  const h = Math.max(0, y2 - y1)
  return { left: x1 + 'px', top: y1 + 'px', width: w + 'px', height: h + 'px' }
})

const makeRoiPreview = async () => {
  if (!screenshotUrl.value || !imgRef.value) return
  const imgEl = imgRef.value
  const canvas = document.createElement('canvas')
  canvas.width = roi.value.w
  canvas.height = roi.value.h
  const ctx = canvas.getContext('2d')
  const tmpImg = new Image()
  await new Promise((resolve, reject) => {
    tmpImg.onload = resolve
    tmpImg.onerror = reject
    tmpImg.src = screenshotUrl.value
  })
  // 按原图裁剪
  ctx.drawImage(
    tmpImg,
    roi.value.x, roi.value.y, roi.value.w, roi.value.h,
    0, 0, roi.value.w, roi.value.h
  )
  roiPreviewUrl.value = canvas.toDataURL('image/png')
}

onMounted(async () => { await fetchEmulators(); await fetchSystem(); })
</script>

<style scoped>
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.toolbar {
  margin-bottom: 12px;
}
.work-area { display: flex; gap: 12px; }
.canvas-wrap { flex: 1; background: #000; min-height: 300px; display: flex; align-items: center; justify-content: center; }
.image-stage { position: relative; }
.emu-image {
  max-width: 100%;
  height: auto;
  image-rendering: pixelated;
  cursor: crosshair;
}
.selection { position: absolute; border: 2px dashed #409eff; background: rgba(64,158,255,0.15); pointer-events: none; }
.side-panel { width: 320px; }
.roi-form { background: #fff; padding: 10px; border-radius: 4px; }
.roi-title { margin-bottom: 6px; font-weight: 600; }
.roi-preview img { max-width: 100%; border: 1px solid #e5e5e5; border-radius: 4px; }
</style>
