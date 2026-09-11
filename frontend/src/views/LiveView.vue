<template>
  <div class="stack">
    <section class="card">
      <div class="card-head">
        <h3>实时摄像头检测</h3>
        <div class="row">
          <span class="badge" :class="wsBadge.cls">{{ wsBadge.text }}</span>
          <span class="badge badge-none">{{ sourceLabel }}</span>
        </div>
      </div>

      <div class="card-body live-body">
        <div class="stage" :class="{ 'is-live': status === 'running' }">
          <video ref="videoEl" class="video" playsinline muted></video>
          <img v-if="annotated && annotatedSrc" class="video overlay-img" :src="annotatedSrc" alt="服务端标注结果" />
          <canvas v-show="!annotated" ref="canvasEl" class="overlay"></canvas>

          <div v-if="status !== 'running'" class="stage-mask">
            <div class="mask-inner">
              <span class="mask-title">{{ maskTitle }}</span>
              <p class="mask-desc">{{ maskDesc }}</p>
              <button class="btn btn-primary" :disabled="busy" @click="start">
                {{ busy ? '正在启动…' : '开启摄像头' }}
              </button>
            </div>
          </div>

          <div v-if="status === 'running'" class="hud">
            <span><b class="mono">{{ fpsText }}</b> FPS</span>
            <span>推理 <b class="mono">{{ msText }}</b> ms</span>
            <span>分辨率 <b class="mono">{{ frameW }}×{{ frameH }}</b></span>
          </div>

          <div v-if="alarm" class="alarm-tag" :class="`alarm-tag-${alarm.level}`">
            {{ alarm.label || '告警' }} · 连击 {{ alarm.strikes ?? 0 }}
          </div>
        </div>

        <aside class="side">
          <div class="field">
            <label class="label" for="cam-select">摄像头</label>
            <select id="cam-select" class="select" v-model="deviceId" :disabled="status === 'running'">
              <option value="">默认设备</option>
              <option v-for="cam in cameras" :key="cam.deviceId" :value="cam.deviceId">
                {{ cam.label }}
              </option>
            </select>
          </div>

          <div class="field">
            <label class="label">置信度阈值 <b class="mono">{{ conf.toFixed(2) }}</b></label>
            <input class="input" type="range" min="0.05" max="0.95" step="0.05" v-model.number="conf" />
          </div>

          <div class="field">
            <label class="label">NMS IoU <b class="mono">{{ iou.toFixed(2) }}</b></label>
            <input class="input" type="range" min="0.05" max="0.95" step="0.05" v-model.number="iou" />
          </div>

          <div class="field">
            <label class="label">画面质量 <b class="mono">{{ quality }}</b></label>
            <input class="input" type="range" min="0.4" max="0.9" step="0.05" v-model.number="quality" />
          </div>

          <label class="switch line">
            <input type="checkbox" v-model="annotated" />
            <span>显示服务端标注图</span>
          </label>

          <div class="row">
            <button v-if="status !== 'running'" class="btn btn-primary btn-block" :disabled="busy" @click="start">
              开始检测
            </button>
            <button v-else class="btn btn-danger btn-block" @click="stop">停止检测</button>
          </div>

          <p class="hint">
            画面以 JPEG 帧经 WebSocket 发送到后端逐帧推理，前端按归一化坐标 <code class="mono">xyxyn</code> 叠加检测框。
          </p>
        </aside>
      </div>

      <p v-if="errorMsg" class="card-foot err">{{ errorMsg }}</p>
    </section>

    <div class="grid grid-2">
      <section class="card">
        <div class="card-head">
          <h3>本帧检测结果</h3>
          <span class="hint">共 {{ detections.length }} 个目标</span>
        </div>
        <div class="card-body">
          <EmptyState v-if="!detections.length" title="未检测到目标" desc="画面中暂未出现火焰或烟雾。" />
          <ul v-else class="det-list">
            <li v-for="(det, index) in detections" :key="index">
              <span class="dot" :style="{ color: colorOf(det) }"></span>
              <span class="det-name">{{ det.label || det.cls }}</span>
              <span class="mono muted">{{ confPercent(det.conf) }}</span>
              <span class="mono det-xy">{{ xyText(det.xyxyn) }}</span>
            </li>
          </ul>
        </div>
      </section>

      <section class="card">
        <div class="card-head">
          <h3>实时统计</h3>
          <span class="hint">本会话累计</span>
        </div>
        <div class="card-body">
          <div class="grid grid-kpi">
            <KpiCard label="接收帧数" :value="frames" tone="accent" />
            <KpiCard label="火焰命中帧" :value="fireFrames" tone="fire" />
            <KpiCard label="烟雾命中帧" :value="smokeFrames" tone="smoke" />
            <KpiCard label="告警次数" :value="alarmCount" tone="danger" />
          </div>
          <div class="kv">
            <div><dt>最高置信度</dt><dd class="mono">{{ maxConfText }}</dd></div>
            <div><dt>当前设备</dt><dd class="mono">{{ deviceLabel }}</dd></div>
            <div><dt>模型</dt><dd class="mono">{{ modelName }}</dd></div>
            <div><dt>会话编号</dt><dd class="mono">{{ sessionId || '—' }}</dd></div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import EmptyState from '../components/EmptyState.vue'
import KpiCard from '../components/KpiCard.vue'
import { wsUrl } from '../api/client'
import { useAlarmFeed } from '../composables/useAlarmFeed'
import { useAlarmSound } from '../composables/useAlarmSound'
import { useBackend } from '../composables/useBackend'
import { confPercent } from '../utils/format'

const CAPTURE_MAX_WIDTH = 960
const RESULT_TIMEOUT_MS = 3000
const SEND_INTERVAL_MS = 40

const { classes, deviceLabel, modelName } = useBackend()
const { push } = useAlarmFeed()
const { unlock } = useAlarmSound()

const videoEl = ref(null)
const canvasEl = ref(null)

const status = ref('idle') // idle | starting | running
const busy = ref(false)
const errorMsg = ref('')
const sessionId = ref('')
const annotated = ref(false)
const annotatedSrc = ref('')

const deviceId = ref('')
const cameras = ref([])
const conf = ref(0.4)
const iou = ref(0.45)
const quality = ref(0.7)

const fps = ref(0)
const inferenceMs = ref(0)
const frameW = ref(0)
const frameH = ref(0)
const detections = ref([])
const alarm = ref(null)

const counters = reactive({ frames: 0, fire: 0, smoke: 0, alarms: 0, maxConf: 0 })

let ws = null
let stream = null
let sendTimer = null
let watchdog = null
let inFlight = false
let destroyed = false

const fpsText = computed(() => (fps.value ? fps.value.toFixed(1) : '—'))
const msText = computed(() => (inferenceMs.value ? inferenceMs.value.toFixed(1) : '—'))
const maxConfText = computed(() => (counters.maxConf ? confPercent(counters.maxConf) : '—'))
const frames = computed(() => counters.frames)
const fireFrames = computed(() => counters.fire)
const smokeFrames = computed(() => counters.smoke)
const alarmCount = computed(() => counters.alarms)

const sourceLabel = computed(() => {
  const cam = cameras.value.find((item) => item.deviceId === deviceId.value)
  return cam ? cam.label : '默认摄像头'
})

const wsBadge = computed(() => {
  if (status.value === 'running') return { cls: 'badge-ok', text: '连接中 · 推理中' }
  if (status.value === 'starting') return { cls: 'badge-warning', text: '正在连接' }
  return { cls: 'badge-none', text: '未开始' }
})

const maskTitle = computed(() => {
  if (status.value === 'starting') return '正在启动…'
  return '摄像头未开启'
})

const maskDesc = computed(() => {
  if (errorMsg.value) return errorMsg.value
  return '浏览器会请求摄像头权限，画面仅在本机与后端之间传输。'
})

function colorOf(det) {
  const list = classes.value || []
  const hit = list.find((item) => item.name === det.cls || item.id === det.cls_id)
  return hit?.color || '#0ea5e9'
}

function xyText(xyxyn) {
  if (!Array.isArray(xyxyn) || xyxyn.length < 4) return '—'
  return xyxyn.map((n) => Number(n).toFixed(3)).join(', ')
}

async function listCameras() {
  if (!navigator.mediaDevices?.enumerateDevices) return
  try {
    const devices = await navigator.mediaDevices.enumerateDevices()
    cameras.value = devices
      .filter((item) => item.kind === 'videoinput')
      .map((item, index) => ({
        deviceId: item.deviceId,
        label: item.label || `摄像头 ${index + 1}`,
      }))
  } catch {
    /* 忽略：部分浏览器需先授权 */
  }
}

function resetCounters() {
  counters.frames = 0
  counters.fire = 0
  counters.smoke = 0
  counters.alarms = 0
  counters.maxConf = 0
  detections.value = []
  alarm.value = null
  fps.value = 0
  inferenceMs.value = 0
  annotatedSrc.value = ''
}

async function start() {
  if (status.value === 'running' || busy.value) return
  busy.value = true
  errorMsg.value = ''
  status.value = 'starting'
  resetCounters()
  unlock()

  try {
    const constraints = {
      audio: false,
      video: {
        width: { ideal: 1280 },
        height: { ideal: 720 },
        ...(deviceId.value ? { deviceId: { exact: deviceId.value } } : {}),
      },
    }
    stream = await navigator.mediaDevices.getUserMedia(constraints)
    const video = videoEl.value
    video.srcObject = stream
    await video.play().catch(() => {})
    await new Promise((resolve) => {
      if (video.videoWidth) return resolve()
      video.onloadedmetadata = () => resolve()
      window.setTimeout(resolve, 1500)
    })

    await listCameras()
    frameW.value = video.videoWidth || 0
    frameH.value = video.videoHeight || 0
    syncCanvas()

    await openSocket()
    status.value = 'running'
    startSending()
  } catch (err) {
    errorMsg.value = friendlyError(err)
    cleanup()
    status.value = 'idle'
  } finally {
    busy.value = false
  }
}

function friendlyError(err) {
  const name = err?.name || ''
  if (name === 'NotAllowedError') return '摄像头权限被拒绝，请在浏览器地址栏允许摄像头访问。'
  if (name === 'NotFoundError') return '未找到可用的摄像头设备。'
  if (name === 'NotReadableError') return '摄像头被其他程序占用，请关闭后重试。'
  if (err?.message) return err.message
  return '无法启动摄像头。'
}

function openSocket() {
  return new Promise((resolve, reject) => {
    let settled = false
    const socket = new WebSocket(wsUrl('/ws/detect'))
    socket.binaryType = 'arraybuffer'
    ws = socket

    const fail = (err) => {
      if (settled) return
      settled = true
      reject(err)
    }

    socket.onopen = () => {
      socket.send(
        JSON.stringify({ type: 'config', conf: conf.value, iou: iou.value, annotated: annotated.value }),
      )
      if (!settled) {
        settled = true
        resolve()
      }
    }
    socket.onmessage = (event) => handleMessage(event)
    socket.onerror = () => fail(new Error('WebSocket 连接失败，请确认后端服务已启动。'))
    socket.onclose = () => {
      if (status.value === 'running' && !destroyed) {
        errorMsg.value = '推理连接已断开，请重新开始。'
        cleanup()
        status.value = 'idle'
      }
      fail(new Error('WebSocket 连接已关闭。'))
    }
  })
}

function handleMessage(event) {
  let msg = null
  try {
    msg = JSON.parse(event.data)
  } catch {
    return
  }

  if (msg.type === 'ready') {
    sessionId.value = msg.session_id || ''
    return
  }
  if (msg.type === 'pong') return
  if (msg.type === 'error') {
    errorMsg.value = msg.message || '单帧推理失败'
    return
  }
  if (msg.type !== 'result') return

  inFlight = false
  clearWatchdog()

  counters.frames += 1
  counters.fire += msg.counts?.fire || 0
  counters.smoke += msg.counts?.smoke || 0
  counters.maxConf = Math.max(counters.maxConf, Number(msg.max_conf) || 0)
  fps.value = Number(msg.fps) || fps.value
  inferenceMs.value = Number(msg.inference_ms) || 0
  frameW.value = msg.width || frameW.value
  frameH.value = msg.height || frameH.value

  detections.value = Array.isArray(msg.detections) ? msg.detections : []
  if (annotated.value) {
    annotatedSrc.value = msg.image?.data_url || ''
  } else {
    drawOverlay(detections.value, msg.width, msg.height)
  }

  const active = msg.alarm?.active
  alarm.value = active ? msg.alarm : null
  if (active) {
    counters.alarms += 1
    push(msg.alarm, { source: 'camera' })
  }
}

function syncCanvas() {
  const canvas = canvasEl.value
  const video = videoEl.value
  if (!canvas || !video) return
  const w = video.videoWidth || 640
  const h = video.videoHeight || 480
  canvas.width = w
  canvas.height = h
}

function drawOverlay(list, width, height) {
  const canvas = canvasEl.value
  if (!canvas) return
  if (!canvas.width || !canvas.height) syncCanvas()
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  if (!Array.isArray(list) || !list.length) return

  const cw = canvas.width || width || 640
  const ch = canvas.height || height || 480
  ctx.lineWidth = Math.max(2, Math.round(cw / 320))
  ctx.font = `${Math.max(12, Math.round(cw / 42))}px var(--mono, monospace)`
  ctx.textBaseline = 'top'

  list.forEach((det) => {
    let box = Array.isArray(det.xyxyn) ? det.xyxyn : null
    if (!box && Array.isArray(det.xyxy) && width && height) {
      box = [det.xyxy[0] / width, det.xyxy[1] / height, det.xyxy[2] / width, det.xyxy[3] / height]
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
    const padX = 6
    const textW = ctx.measureText(text).width + padX * 2
    const textH = Math.max(16, Math.round(cw / 34))
    const ty = y - textH < 0 ? y : y - textH

    ctx.fillStyle = color
    ctx.fillRect(x, ty, textW, textH)
    ctx.fillStyle = '#ffffff'
    ctx.fillText(text, x + padX, ty + Math.round(textH * 0.2))
  })
}

function startSending() {
  stopSending()
  sendTimer = window.setInterval(sendFrame, SEND_INTERVAL_MS)
}

function stopSending() {
  if (sendTimer !== null) {
    window.clearInterval(sendTimer)
    sendTimer = null
  }
  clearWatchdog()
  inFlight = false
}

function clearWatchdog() {
  if (watchdog !== null) {
    window.clearTimeout(watchdog)
    watchdog = null
  }
}

function sendFrame() {
  const socket = ws
  const video = videoEl.value
  if (!socket || socket.readyState !== WebSocket.OPEN) return
  if (inFlight) return
  if (!video || !video.videoWidth) return

  const scale = Math.min(1, CAPTURE_MAX_WIDTH / video.videoWidth)
  const w = Math.max(1, Math.round(video.videoWidth * scale))
  const h = Math.max(1, Math.round(video.videoHeight * scale))

  const scratch = document.createElement('canvas')
  scratch.width = w
  scratch.height = h
  const ctx = scratch.getContext('2d')
  if (!ctx) return
  ctx.drawImage(video, 0, 0, w, h)

  inFlight = true
  watchdog = window.setTimeout(() => {
    inFlight = false
    watchdog = null
  }, RESULT_TIMEOUT_MS)

  scratch.toBlob(
    async (blob) => {
      if (!blob || !ws || ws.readyState !== WebSocket.OPEN) {
        inFlight = false
        return
      }
      try {
        const buf = await blob.arrayBuffer()
        if (ws && ws.readyState === WebSocket.OPEN) ws.send(buf)
        else inFlight = false
      } catch {
        inFlight = false
      }
    },
    'image/jpeg',
    quality.value,
  )
}

function stop() {
  cleanup()
  status.value = 'idle'
}

function cleanup() {
  stopSending()
  if (ws) {
    try {
      ws.onopen = null
      ws.onmessage = null
      ws.onerror = null
      ws.onclose = null
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) ws.close()
    } catch {
      /* ignore */
    }
    ws = null
  }
  if (stream) {
    stream.getTracks().forEach((track) => track.stop())
    stream = null
  }
  if (videoEl.value) videoEl.value.srcObject = null
  const canvas = canvasEl.value
  if (canvas) {
    const ctx = canvas.getContext('2d')
    if (ctx) ctx.clearRect(0, 0, canvas.width, canvas.height)
  }
  sessionId.value = ''
}

onMounted(() => {
  listCameras()
  if (navigator.mediaDevices) {
    navigator.mediaDevices.addEventListener('devicechange', listCameras)
  }
})

onBeforeUnmount(() => {
  destroyed = true
  cleanup()
  if (navigator.mediaDevices) {
    navigator.mediaDevices.removeEventListener('devicechange', listCameras)
  }
})
</script>

<style scoped>
.live-body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 280px;
  gap: 18px;
}

.stage {
  position: relative;
  aspect-ratio: 16 / 10;
  background: var(--surface-sunken);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  overflow: hidden;
}

.stage.is-live {
  border-color: var(--accent-line);
  box-shadow: 0 0 0 3px rgba(30, 111, 255, 0.08);
}

.video {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: #0b1220;
}

.overlay {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}

.overlay-img {
  object-fit: contain;
}

.stage-mask {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  background: linear-gradient(180deg, rgba(244, 247, 251, 0.96), rgba(255, 255, 255, 0.96));
}

.mask-inner {
  text-align: center;
  max-width: 320px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.mask-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
}

.mask-desc {
  margin: 0 0 4px;
  font-size: 12.5px;
  color: var(--text-3);
  line-height: 1.6;
}

.hud {
  position: absolute;
  left: 10px;
  top: 10px;
  display: flex;
  gap: 12px;
  padding: 6px 10px;
  font-size: 11.5px;
  color: #eaf1ff;
  background: rgba(11, 18, 32, 0.62);
  border-radius: var(--r-pill);
  backdrop-filter: blur(3px);
}

.hud b {
  font-weight: 600;
}

.alarm-tag {
  position: absolute;
  right: 10px;
  top: 10px;
  padding: 6px 12px;
  font-size: 12.5px;
  font-weight: 600;
  border-radius: var(--r-pill);
  color: #fff;
  background: var(--warn);
  box-shadow: 0 4px 12px rgba(15, 28, 46, 0.2);
}

.alarm-tag-critical {
  background: var(--danger);
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

.det-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 260px;
  overflow-y: auto;
}

.det-list li {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  font-size: 13px;
  background: var(--surface-soft);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
}

.det-name {
  font-weight: 500;
}

.det-xy {
  margin-left: auto;
  font-size: 11.5px;
  color: var(--text-3);
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

.err {
  margin: 0;
  color: #b91c1c;
}

@media (max-width: 1000px) {
  .live-body {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
