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
              @mousemove="onMouseMove"
              @mouseleave="onMouseLeave"
              class="emu-image"
              alt="screenshot"
            />
            <div v-if="cursorPos" class="coord-label">
              ({{ cursorPos.x }}, {{ cursorPos.y }})
            </div>
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
              <el-form-item label="x1"><el-input-number v-model="roi.x1" :min="0" /></el-form-item>
              <el-form-item label="y1"><el-input-number v-model="roi.y1" :min="0" /></el-form-item>
              <el-form-item label="x2"><el-input-number v-model="roi.x2" :min="0" /></el-form-item>
              <el-form-item label="y2"><el-input-number v-model="roi.y2" :min="0" /></el-form-item>
              <el-form-item>
                <el-button :disabled="!screenshotUrl" @click="makeRoiPreview">
                  <el-icon><Crop /></el-icon>
                  生成预览
                </el-button>
                <el-button type="warning" :disabled="!selectedId" :loading="ocrLoading" @click="runOcr">
                  OCR 识别
                </el-button>
              </el-form-item>
              <el-form-item>
                <el-button :disabled="savePreviewLoading" @click="pickSaveDirectory">
                  选择保存文件夹
                </el-button>
                <el-button
                  type="primary"
                  :disabled="!screenshotUrl || savePreviewLoading"
                  :loading="savePreviewLoading"
                  @click="saveRoiPreviewToFolder"
                >
                  保存预览到该文件夹
                </el-button>
              </el-form-item>
            </el-form>
            <div class="save-dir-tip">保存目录：{{ saveDirName || '未选择' }}</div>
            <div class="roi-preview" v-if="roiPreviewUrl">
              <img :src="roiPreviewUrl" alt="roi" />
            </div>
            <div class="ocr-result" v-if="ocrResult">
              <div class="roi-title" style="margin-top: 10px;">OCR 结果</div>
              <div class="ocr-fulltext">{{ ocrResult.full_text || '(未识别到文字)' }}</div>
              <el-table v-if="ocrResult.boxes && ocrResult.boxes.length" :data="ocrResult.boxes" size="small" stripe style="margin-top: 6px;">
                <el-table-column prop="text" label="文字" />
                <el-table-column label="置信度" width="80">
                  <template #default="{ row }">{{ (row.confidence * 100).toFixed(1) }}%</template>
                </el-table-column>
                <el-table-column label="中心坐标" width="110">
                  <template #default="{ row }">{{ row.center[0] }}, {{ row.center[1] }}</template>
                </el-table-column>
              </el-table>
            </div>
          </div>
        </div>
      </div>
    </el-card>
  </div>
  
</template>

<script setup>
import { ref, onMounted, computed, onBeforeUnmount } from 'vue'
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
const roi = ref({ x1: 0, y1: 0, x2: 0, y2: 0 })
const roiPreviewUrl = ref('')
const roiPreviewBlob = ref(null)
const roiPreviewMeta = ref(null)
const saveDirHandle = ref(null)
const saveDirName = ref('')
const savePreviewLoading = ref(false)
const ocrResult = ref(null)
const ocrLoading = ref(false)
const cursorPos = ref(null)

const goBack = () => router.push('/emulators')

const clamp = (v, min, max) => Math.min(max, Math.max(min, v))

const revokeObjectUrl = (url) => {
  if (url) URL.revokeObjectURL(url)
}

const clearRoiPreview = () => {
  revokeObjectUrl(roiPreviewUrl.value)
  roiPreviewUrl.value = ''
  roiPreviewBlob.value = null
  roiPreviewMeta.value = null
}

const clearScreenshot = () => {
  revokeObjectUrl(screenshotUrl.value)
  screenshotUrl.value = ''
  imgNatural.value = { w: 0, h: 0 }
}

const normalizeRoiPoints = (raw = roi.value) => {
  const naturalW = Number(imgNatural.value.w) || 0
  const naturalH = Number(imgNatural.value.h) || 0
  if (naturalW <= 0 || naturalH <= 0) return null

  let x1 = Math.round(Number(raw?.x1 ?? 0))
  let y1 = Math.round(Number(raw?.y1 ?? 0))
  let x2 = Math.round(Number(raw?.x2 ?? 0))
  let y2 = Math.round(Number(raw?.y2 ?? 0))
  if (!Number.isFinite(x1)) x1 = 0
  if (!Number.isFinite(y1)) y1 = 0
  if (!Number.isFinite(x2)) x2 = 0
  if (!Number.isFinite(y2)) y2 = 0

  x1 = clamp(x1, 0, naturalW)
  y1 = clamp(y1, 0, naturalH)
  x2 = clamp(x2, 0, naturalW)
  y2 = clamp(y2, 0, naturalH)

  const left = Math.min(x1, x2)
  const top = Math.min(y1, y2)
  const right = Math.max(x1, x2)
  const bottom = Math.max(y1, y2)

  if (right <= left || bottom <= top) return null
  return { x1: left, y1: top, x2: right, y2: bottom }
}

const roiPointsToRect = (points) => {
  if (!points) return null
  return {
    x: points.x1,
    y: points.y1,
    w: points.x2 - points.x1,
    h: points.y2 - points.y1
  }
}

const canvasToPngBlob = (canvas) =>
  new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) resolve(blob)
      else reject(new Error('生成预览失败'))
    }, 'image/png')
  })

const isDirectoryPickerSupported = () =>
  typeof window !== 'undefined' && typeof window.showDirectoryPicker === 'function'

const formatDateForFileName = (d = new Date()) => {
  const pad2 = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}${pad2(d.getMonth() + 1)}${pad2(d.getDate())}_${pad2(d.getHours())}${pad2(d.getMinutes())}${pad2(d.getSeconds())}`
}

const buildRoiFileName = (normalizedPoints) =>
  `roi_${formatDateForFileName()}_x1${normalizedPoints.x1}_y1${normalizedPoints.y1}_x2${normalizedPoints.x2}_y2${normalizedPoints.y2}.png`

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
  clearScreenshot()
  clearRoiPreview()
  hasSelection.value = false
}

const refreshScreenshot = async () => {
  if (!selectedId.value) return
  loading.value = true
  try {
    const url = buildApiUrl(API_ENDPOINTS.emulatorScreenshot(selectedId.value)) + `?method=${shotMethod.value}`
    const token = localStorage.getItem('yys_auth_token')
    const resp = await fetch(url, {
      headers: token ? { 'Authorization': `Bearer ${token}` } : {}
    })
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
    clearScreenshot()
    screenshotUrl.value = URL.createObjectURL(blob)
    // 清除已有选区
    hasSelection.value = false
    clearRoiPreview()
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

// 鼠标坐标追踪（原图坐标）
const onMouseMove = (evt) => {
  if (!imgRef.value || !imgNatural.value.w) return
  const rect = imgRef.value.getBoundingClientRect()
  const scaleX = imgNatural.value.w / rect.width
  const scaleY = imgNatural.value.h / rect.height
  cursorPos.value = {
    x: Math.round((evt.clientX - rect.left) * scaleX),
    y: Math.round((evt.clientY - rect.top) * scaleY)
  }
}
const onMouseLeave = () => { cursorPos.value = null }

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
  const x1 = clamp(Math.min(selStart.value.x, selEnd.value.x), 0, rect.width)
  const y1 = clamp(Math.min(selStart.value.y, selEnd.value.y), 0, rect.height)
  const x2 = clamp(Math.max(selStart.value.x, selEnd.value.x), 0, rect.width)
  const y2 = clamp(Math.max(selStart.value.y, selEnd.value.y), 0, rect.height)
  const scaleX = imgNatural.value.w / rect.width
  const scaleY = imgNatural.value.h / rect.height
  roi.value = {
    x1: Math.round(x1 * scaleX),
    y1: Math.round(y1 * scaleY),
    x2: Math.round(x2 * scaleX),
    y2: Math.round(y2 * scaleY)
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
  if (!screenshotUrl.value || !imgRef.value || imgNatural.value.w <= 0 || imgNatural.value.h <= 0) {
    ElMessage.warning('请先获取截图')
    return false
  }

  const normalizedPoints = normalizeRoiPoints()
  if (!normalizedPoints) {
    clearRoiPreview()
    ElMessage.warning('请先框选有效区域（x2/x1 与 y2/y1 需形成有效矩形）')
    return false
  }

  const normalizedRoi = roiPointsToRect(normalizedPoints)
  if (!normalizedRoi) return false
  roi.value = { ...normalizedPoints }
  try {
    const canvas = document.createElement('canvas')
    canvas.width = normalizedRoi.w
    canvas.height = normalizedRoi.h
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('画布初始化失败')

    ctx.drawImage(
      imgRef.value,
      normalizedRoi.x, normalizedRoi.y, normalizedRoi.w, normalizedRoi.h,
      0, 0, normalizedRoi.w, normalizedRoi.h
    )

    const blob = await canvasToPngBlob(canvas)
    clearRoiPreview()
    roiPreviewBlob.value = blob
    roiPreviewMeta.value = { ...normalizedPoints }
    roiPreviewUrl.value = URL.createObjectURL(blob)
    return true
  } catch (e) {
    clearRoiPreview()
    ElMessage.error(e.message || '生成预览失败')
    return false
  }
}

const pickSaveDirectory = async () => {
  if (!isDirectoryPickerSupported()) {
    ElMessage.warning('当前运行环境不支持指定文件夹保存')
    return false
  }
  try {
    const dirHandle = await window.showDirectoryPicker({ mode: 'readwrite' })
    saveDirHandle.value = dirHandle
    saveDirName.value = dirHandle?.name || ''
    return true
  } catch (e) {
    if (e?.name !== 'AbortError') {
      ElMessage.error(e.message || '选择保存文件夹失败')
    }
    return false
  }
}

const saveRoiPreviewToFolder = async () => {
  if (savePreviewLoading.value) return
  savePreviewLoading.value = true
  try {
    if (!isDirectoryPickerSupported()) {
      ElMessage.warning('当前运行环境不支持指定文件夹保存')
      return
    }

    if (!roiPreviewBlob.value) {
      const ok = await makeRoiPreview()
      if (!ok) return
    }

    if (!saveDirHandle.value) {
      const selected = await pickSaveDirectory()
      if (!selected) return
    }

    const normalizedPoints = roiPreviewMeta.value || normalizeRoiPoints()
    if (!normalizedPoints || !roiPreviewBlob.value) {
      ElMessage.warning('当前没有可保存的预览图')
      return
    }

    const fileName = buildRoiFileName(normalizedPoints)
    const fileHandle = await saveDirHandle.value.getFileHandle(fileName, { create: true })
    const writable = await fileHandle.createWritable()
    await writable.write(roiPreviewBlob.value)
    await writable.close()
    ElMessage.success(`已保存预览：${fileName}`)
  } catch (e) {
    if (e?.name === 'AbortError') return
    if (e?.name === 'NotAllowedError') {
      ElMessage.error('没有文件夹写入权限，请重新选择目录')
      return
    }
    ElMessage.error(e.message || '保存预览失败')
  } finally {
    savePreviewLoading.value = false
  }
}

const runOcr = async () => {
  if (!selectedId.value) return
  ocrLoading.value = true
  ocrResult.value = null
  try {
    const normalizedPoints = normalizeRoiPoints()
    const normalizedRoi = roiPointsToRect(normalizedPoints)
    const payload = normalizedRoi
      ? { ...normalizedRoi, method: shotMethod.value }
      : { x: 0, y: 0, w: 0, h: 0, method: shotMethod.value }
    const resp = await apiRequest(API_ENDPOINTS.emulatorOcr(selectedId.value), {
      method: 'POST',
      body: JSON.stringify(payload)
    })
    const data = await resp.json()
    if (!resp.ok) throw new Error(data?.detail || 'OCR 识别失败')
    ocrResult.value = data
    ElMessage.success(`识别完成，共 ${data.boxes?.length || 0} 条结果`)
  } catch (e) {
    ElMessage.error(e.message || 'OCR 识别失败')
  } finally {
    ocrLoading.value = false
  }
}

onMounted(async () => { await fetchEmulators(); await fetchSystem(); })
onBeforeUnmount(() => {
  clearScreenshot()
  clearRoiPreview()
})
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
.coord-label { position: absolute; top: 4px; left: 4px; background: rgba(0,0,0,0.7); color: #fff; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-family: monospace; pointer-events: none; z-index: 10; }
.side-panel { width: 320px; }
.roi-form { background: #fff; padding: 10px; border-radius: 4px; }
.roi-title { margin-bottom: 6px; font-weight: 600; }
.save-dir-tip { margin: 4px 0 10px; color: #606266; font-size: 12px; word-break: break-all; }
.roi-preview img { max-width: 100%; border: 1px solid #e5e5e5; border-radius: 4px; }
.ocr-result { margin-top: 8px; }
.ocr-fulltext { background: #f5f7fa; padding: 8px; border-radius: 4px; font-size: 13px; word-break: break-all; user-select: text; }
</style>
