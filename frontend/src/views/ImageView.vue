<template>
  <div class="stack">
    <section class="card">
      <div class="card-head">
        <h3>图片检测</h3>
        <span class="hint">支持 jpg / png / webp / bmp</span>
      </div>
      <div class="card-body img-body">
        <div class="stage" :class="{ 'is-dragging': dragging }" @dragenter.prevent="dragging = true"
             @dragover.prevent="dragging = true" @dragleave.prevent="dragging = false" @drop.prevent="onDrop">
          <img v-if="previewSrc" class="preview" :src="previewSrc" alt="待检测图片" @load="onImageLoad" />
          <canvas v-show="previewSrc && !usesServerImage" ref="canvasEl" class="overlay"></canvas>

          <div v-if="!previewSrc" class="stage-mask">
            <div class="mask-inner">
              <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                   stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <rect x="3" y="4" width="18" height="16" rx="2.5" />
                <circle cx="9" cy="10" r="1.6" />
                <path d="M4 18l5-4.5 4 3.2 3-2.4 4 3.7" />
              </svg>
              <span class="mask-title">拖拽图片到此处</span>
              <p class="mask-desc">或点击下方按钮选择本地图片文件</p>
              <label class="btn btn-primary">
                选择图片
                <input ref="fileEl" type="file" accept="image/*" hidden @change="onPick" />
              </label>
            </div>
          </div>

          <div v-if="loading" class="stage-mask is-busy">
            <div class="mask-inner">
              <span class="dot dot-pulse" style="color: var(--accent)"></span>
              <span class="mask-title">正在推理…</span>
            </div>
          </div>
        </div>

        <aside class="side">
          <div class="field">
            <label class="label">置信度阈值 <b class="mono">{{ conf.toFixed(2) }}</b></label>
            <input class="input" type="range" min="0.05" max="0.95" step="0.05" v-model.number="conf" />
          </div>
          <div class="field">
            <label class="label">NMS IoU <b class="mono">{{ iou.toFixed(2) }}</b></label>
            <input class="input" type="range" min="0.05" max="0.95" step="0.05" v-model.number="iou" />
          </div>
          <label class="switch line">
            <input type="checkbox" v-model="returnImage" />
            <span>返回服务端标注图</span>
          </label>

          <div class="row">
            <button class="btn btn-primary btn-block" :disabled="!file || loading" @click="submit">
              {{ loading ? '检测中…' : '开始检测' }}
            </button>
          </div>
          <div class="row">
            <button class="btn btn-sm" :disabled="!file || loading" @click="pickAnother">换一张</button>
            <button class="btn btn-sm" :disabled="!result" @click="downloadRaw">下载标注图</button>
            <button class="btn btn-sm" :disabled="!previewSrc" @click="reset">清空</button>
          </div>
          <p v-if="file" class="hint mono">{{ file.name }} · {{ formatBytes(file.size) }}</p>
          <p v-if="error" class="hint err">{{ error }}</p>
        </aside>
      </div>
    </section>

    <div v-if="result" class="grid grid-2">
      <section class="card">
        <div class="card-head">
          <h3>检测结果</h3>
          <span class="badge" :class="alarmMeta.badge">{{ alarmMeta.text }}</span>
        </div>
        <div class="card-body">
          <div class="grid grid-kpi">
            <KpiCard label="目标总数" :value="result.counts?.total ?? detections.length" tone="accent" />
            <KpiCard label="火焰" :value="result.counts?.fire ?? 0" tone="fire" />
            <KpiCard label="烟雾" :value="result.counts?.smoke ?? 0" tone="smoke" />
            <KpiCard label="最高置信度" :value="confPercent(result.max_conf)" tone="warn" />
          </div>
          <div class="kv">
            <div><dt>图片尺寸</dt><dd class="mono">{{ result.width }}×{{ result.height }}</dd></div>
            <div><dt>推理设备</dt><dd class="mono">{{ result.device }}</dd></div>
            <div><dt>预处理</dt><dd class="mono">{{ ms(result.preprocess_ms) }} ms</dd></div>
            <div><dt>推理耗时</dt><dd class="mono">{{ ms(result.inference_ms) }} ms</dd></div>
            <div><dt>后处理</dt><dd class="mono">{{ ms(result.postprocess_ms) }} ms</dd></div>
            <div><dt>检测编号</dt><dd class="mono">{{ result.id }}</dd></div>
          </div>
          <p v-if="result.alarm?.active" class="alarm-line">
            {{ result.alarm.message }}（{{ result.alarm.level }}）
          </p>
        </div>
      </section>

      <section class="card">
        <div class="card-head">
          <h3>目标清单</h3>
          <span class="hint">{{ detections.length }} 个</span>
        </div>
        <div class="card-body">
          <EmptyState v-if="!detections.length" title="未检测到目标" desc="该图片中未发现火焰或烟雾。" />
          <div v-else class="table-wrap">
            <table class="table">
              <thead>
                <tr>
                  <th>类别</th>
                  <th>置信度</th>
                  <th>像素框 xyxy</th>
                  <th>归一化框 xyxyn</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(det, index) in detections" :key="index">
                  <td>
                    <span class="dot" :style="{ color: colorOf(det) }"></span>
                    {{ det.label || det.cls }}
                  </td>
                  <td class="num mono">{{ confPercent(det.conf) }}</td>
                  <td class="mono num">{{ listText(det.xyxy) }}</td>
                  <td class="mono num">{{ listText(det.xyxyn, 3) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>

    <p v-else class="card card-body tip">
      选择或拖入一张图片后点击「开始检测」，即可查看检测框、置信度与告警结果。
    </p>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'
import EmptyState from '../components/EmptyState.vue'
import KpiCard from '../components/KpiCard.vue'
import { api, buildForm } from '../api/client'
import { useAlarmFeed } from '../composables/useAlarmFeed'
import { useBackend } from '../composables/useBackend'
import { confPercent, formatBytes, levelMeta } from '../utils/format'

const { classes } = useBackend()
const { push } = useAlarmFeed()

const fileEl = ref(null)
const canvasEl = ref(null)
const file = ref(null)
const localUrl = ref('')
const annotatedUrl = ref('')
const dragging = ref(false)
const loading = ref(false)
const error = ref('')
const result = ref(null)

const conf = ref(0.35)
const iou = ref(0.45)
const returnImage = ref(true)

const detections = computed(() => (Array.isArray(result.value?.detections) ? result.value.detections : []))
const usesServerImage = computed(() => Boolean(annotatedUrl.value && returnImage.value))
const previewSrc = computed(() => annotatedUrl.value || localUrl.value)
const alarmMeta = computed(() => levelMeta(result.value?.alarm?.level))

function ms(value) {
  const n = Number(value)
  return Number.isFinite(n) ? n.toFixed(1) : '—'
}

function listText(list, digits = 0) {
  if (!Array.isArray(list)) return '—'
  return list.map((n) => Number(n).toFixed(digits)).join(', ')
}

function colorOf(det) {
  const list = classes.value || []
  const hit = list.find((item) => item.name === det.cls || item.id === det.cls_id)
  return hit?.color || '#0ea5e9'
}

function acceptFile(candidate) {
  if (!candidate) return
  if (!candidate.type.startsWith('image/')) {
    error.value = '请选择图片文件（jpg / png / webp / bmp）。'
    return
  }
  error.value = ''
  result.value = null
  annotatedUrl.value = ''
  if (localUrl.value) URL.revokeObjectURL(localUrl.value)
  file.value = candidate
  localUrl.value = URL.createObjectURL(candidate)
}

function onPick(event) {
  const [picked] = event.target.files || []
  acceptFile(picked)
  event.target.value = ''
}

function onDrop(event) {
  dragging.value = false
  const [dropped] = event.dataTransfer?.files || []
  acceptFile(dropped)
}

function pickAnother() {
  fileEl.value?.click()
}

function reset() {
  if (localUrl.value) URL.revokeObjectURL(localUrl.value)
  localUrl.value = ''
  annotatedUrl.value = ''
  file.value = null
  result.value = null
  error.value = ''
  const canvas = canvasEl.value
  if (canvas) {
    const ctx = canvas.getContext('2d')
    if (ctx) ctx.clearRect(0, 0, canvas.width, canvas.height)
  }
}

function onImageLoad(event) {
  const canvas = canvasEl.value
  if (!canvas) return
  canvas.width = event.target.naturalWidth || canvas.clientWidth
  canvas.height = event.target.naturalHeight || canvas.clientHeight
  nextTick(() => drawBoxes())
}

function drawBoxes() {
  if (usesServerImage.value) return
  const canvas = canvasEl.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  if (!detections.value.length) return

  const cw = canvas.width
  const ch = canvas.height
  ctx.lineWidth = Math.max(2, Math.round(cw / 400))
  ctx.font = `${Math.max(13, Math.round(cw / 48))}px monospace`
  ctx.textBaseline = 'top'

  detections.value.forEach((det) => {
    let box = Array.isArray(det.xyxyn) ? det.xyxyn : null
    if (!box && Array.isArray(det.xyxy) && result.value) {
      box = [
        det.xyxy[0] / result.value.width,
        det.xyxy[1] / result.value.height,
        det.xyxy[2] / result.value.width,
        det.xyxy[3] / result.value.height,
      ]
    }
    if (!box) return
    const color = colorOf(det)
    const x = box[0] * cw
    const y = box[1] * ch
    const w = Math.max(1, (box[2] - box[0]) * cw)
    const h = Math.max(1, (box[3] - box[1]) * ch)
    ctx.strokeStyle = color
    ctx.strokeRect(x, y, w, h)

    const text = `${det.label || det.cls} ${confPercent(det.conf)}`
    const textW = ctx.measureText(text).width + 12
    const textH = Math.max(18, Math.round(cw / 38))
    const ty = y - textH < 0 ? y : y - textH
    ctx.fillStyle = color
    ctx.fillRect(x, ty, textW, textH)
    ctx.fillStyle = '#fff'
    ctx.fillText(text, x + 6, ty + Math.round(textH * 0.18))
  })
}

async function submit() {
  if (!file.value || loading.value) return
  loading.value = true
  error.value = ''
  try {
    const form = buildForm({
      file: file.value,
      conf: conf.value,
      iou: iou.value,
      return_image: returnImage.value ? 'true' : 'false',
    })
    const data = await api.detectImage(form)
    result.value = data
    annotatedUrl.value = data.image?.data_url || ''
    await nextTick()
    if (!usesServerImage.value) {
      const img = document.querySelector('.preview')
      if (img?.naturalWidth) {
        const canvas = canvasEl.value
        if (canvas) {
          canvas.width = img.naturalWidth
          canvas.height = img.naturalHeight
        }
      }
      drawBoxes()
    }
    if (data.alarm?.active) {
      push(data.alarm, { source: 'image' })
    }
  } catch (err) {
    error.value = err?.message || '检测失败，请确认后端服务正常。'
  } finally {
    loading.value = false
  }
}

async function downloadRaw() {
  if (!file.value) return
  try {
    const form = buildForm({
      file: file.value,
      conf: conf.value,
      iou: iou.value,
    })
    const blob = await api.detectImageRaw(form)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `detected_${Date.now()}.jpg`
    link.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    error.value = err?.message || '导出标注图失败。'
  }
}

onBeforeUnmount(() => {
  if (localUrl.value) URL.revokeObjectURL(localUrl.value)
})
</script>

<style scoped>
.img-body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 280px;
  gap: 18px;
}

.stage {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 360px;
  background: var(--surface-sunken);
  border: 1px dashed var(--line-strong);
  border-radius: var(--r-md);
  overflow: hidden;
}

.stage.is-dragging {
  border-color: var(--accent);
  background: var(--accent-soft);
}

.preview {
  display: block;
  max-width: 100%;
  max-height: 620px;
  object-fit: contain;
}

.overlay {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: contain;
  pointer-events: none;
}

.stage-mask {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 20px;
}

.stage-mask.is-busy {
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(2px);
}

.mask-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  text-align: center;
  max-width: 300px;
  color: var(--text-3);
}

.mask-title {
  font-size: 14.5px;
  font-weight: 600;
  color: var(--text);
}

.mask-desc {
  margin: 0 0 4px;
  font-size: 12.5px;
  line-height: 1.6;
}

.side {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.line {
  flex-direction: row;
  align-items: center;
  gap: 9px;
}

.line span {
  font-size: 13px;
  color: var(--text-2);
}

.kv {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px 20px;
  margin-top: 14px;
}

.kv > div {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  padding: 6px 0;
  border-bottom: 1px dashed var(--line);
}

.kv dt {
  font-size: 12.5px;
  color: var(--text-3);
}

.kv dd {
  margin: 0;
  font-size: 13px;
  text-align: right;
}

.alarm-line {
  margin: 14px 0 0;
  padding: 9px 12px;
  font-size: 13px;
  color: #b91c1c;
  background: var(--danger-soft);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: var(--r-sm);
}

.table-wrap {
  max-height: 300px;
  overflow: auto;
}

.err {
  color: #b91c1c;
}

.tip {
  margin: 0;
  font-size: 13px;
  color: var(--text-3);
  border: 1px dashed var(--line-strong);
}

@media (max-width: 1000px) {
  .img-body {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
