<template>
  <div class="stack">
    <section class="card">
      <div class="card-head">
        <h3>视频文件检测</h3>
        <span class="hint">支持 mp4 / avi / mov / mkv</span>
      </div>
      <div class="card-body vid-body">
        <div class="stage" :class="{ 'is-dragging': dragging }" @dragenter.prevent="dragging = true"
             @dragover.prevent="dragging = true" @dragleave.prevent="dragging = false" @drop.prevent="onDrop">
          <video v-if="outputUrl" class="player" :src="outputUrl" controls autoplay loop></video>

          <div v-if="!outputUrl" class="stage-mask">
            <div class="mask-inner">
              <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                   stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <rect x="3" y="5" width="13" height="14" rx="2.5" />
                <path d="M16 10.5 21 8v8l-5-2.5z" />
              </svg>
              <span class="mask-title">{{ job ? '正在检测视频…' : '拖拽视频到此处' }}</span>
              <p class="mask-desc">
                {{ job ? (job.filename || '视频') + ' 正在逐帧推理' : '或点击下方按钮选择本地视频文件' }}
              </p>
              <label v-if="!job" class="btn btn-primary">
                选择视频
                <input ref="fileEl" type="file" accept="video/*" hidden @change="onPick" />
              </label>
            </div>
          </div>
        </div>

        <aside class="side">
          <div class="field">
            <label class="label">置信度阈值 <b class="mono">{{ conf.toFixed(2) }}</b></label>
            <input class="input" type="range" min="0.05" max="0.95" step="0.05" v-model.number="conf"
                   :disabled="Boolean(job)" />
          </div>
          <div class="field">
            <label class="label">NMS IoU <b class="mono">{{ iou.toFixed(2) }}</b></label>
            <input class="input" type="range" min="0.05" max="0.95" step="0.05" v-model.number="iou"
                   :disabled="Boolean(job)" />
          </div>
          <div class="field">
            <label class="label" for="stride">抽帧步长 <b class="mono">每 {{ stride }} 帧</b></label>
            <select id="stride" class="select" v-model.number="stride" :disabled="Boolean(job)">
              <option :value="1">1（最精细）</option>
              <option :value="2">2（推荐）</option>
              <option :value="3">3</option>
              <option :value="5">5（最快）</option>
            </select>
          </div>

          <div class="row">
            <button v-if="!job" class="btn btn-primary btn-block" :disabled="!file || submitting" @click="submit">
              {{ submitting ? '上传中…' : '开始检测' }}
            </button>
            <button v-else class="btn btn-danger btn-block" @click="cancelJob">取消任务</button>
          </div>
          <div v-if="!job" class="row">
            <button class="btn btn-sm" :disabled="submitting" @click="pickAnother">选择视频</button>
            <button class="btn btn-sm" :disabled="!file" @click="reset">清空</button>
          </div>
          <p v-if="file && !job" class="hint mono">{{ file.name }} · {{ formatBytes(file.size) }}</p>
          <p v-if="error" class="hint err">{{ error }}</p>
        </aside>
      </div>
    </section>

    <section v-if="job" class="card">
      <div class="card-head">
        <h3>任务进度</h3>
        <span class="badge" :class="statusMeta.badge">{{ statusMeta.text }}</span>
      </div>
      <div class="card-body">
        <div class="progress" :class="{ 'is-fire': job.status === 'processing' }">
          <span :style="{ width: `${Math.round((job.progress || 0) * 100)}%` }"></span>
        </div>
        <div class="progress-meta">
          <span class="mono">{{ Math.round((job.progress || 0) * 100) }}%</span>
          <span class="muted mono">{{ job.processed || 0 }} / {{ job.total_frames || '?' }} 帧</span>
          <span class="span spacer"></span>
          <span class="muted mono">{{ job.fps ? job.fps.toFixed(1) + ' FPS' : '—' }}</span>
        </div>

        <div class="kv">
          <div><dt>任务编号</dt><dd class="mono">{{ job.job_id }}</dd></div>
          <div><dt>文件名</dt><dd class="mono">{{ job.filename }}</dd></div>
          <div><dt>开始时间</dt><dd class="mono">{{ formatTime(job.started_at) }}</dd></div>
          <div><dt>结束时间</dt><dd class="mono">{{ job.finished_at ? formatTime(job.finished_at) : '—' }}</dd></div>
        </div>

        <p v-if="job.status === 'failed'" class="alarm-line">{{ job.error || '任务执行失败' }}</p>

        <div v-if="job.summary" class="grid grid-kpi summary">
          <KpiCard label="检出的目标" :value="job.summary.total_detections ?? 0" tone="accent" />
          <KpiCard label="火焰帧" :value="job.summary.fire_frames ?? 0" tone="fire" />
          <KpiCard label="烟雾帧" :value="job.summary.smoke_frames ?? 0" tone="smoke" />
          <KpiCard label="生成报警" :value="job.summary.events_created ?? 0" tone="danger" />
        </div>
      </div>
      <div v-if="outputUrl" class="card-foot">
        <a class="btn btn-sm" :href="outputUrl" download>下载标注视频</a>
        <span class="hint">已生成标注视频，可直接在左侧播放。</span>
      </div>
    </section>

    <section class="card">
      <div class="card-head">
        <h3>历史任务</h3>
        <button class="btn btn-sm" :disabled="loadingJobs" @click="loadJobs">刷新</button>
      </div>
      <div class="card-body">
        <EmptyState v-if="!jobs.length" title="暂无检测任务" desc="提交一个视频文件后，任务会显示在这里。" />
        <div v-else class="table-wrap">
          <table class="table">
            <thead>
              <tr>
                <th>文件名</th>
                <th>状态</th>
                <th>进度</th>
                <th>帧数</th>
                <th>开始时间</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in jobs" :key="item.job_id" :class="{ 'is-current': job && item.job_id === job.job_id }">
                <td class="mono ellipsis">{{ item.filename }}</td>
                <td>
                  <span class="badge" :class="badgeOf(item.status)">{{ statusText(item.status) }}</span>
                </td>
                <td class="num mono">{{ Math.round((item.progress || 0) * 100) }}%</td>
                <td class="num mono">{{ item.processed || 0 }}/{{ item.total_frames || '?' }}</td>
                <td class="mono">{{ formatTime(item.started_at) }}</td>
                <td class="num">
                  <button class="btn btn-sm" @click="selectJob(item.job_id)">查看</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import EmptyState from '../components/EmptyState.vue'
import KpiCard from '../components/KpiCard.vue'
import { api, buildForm, staticUrl } from '../api/client'
import { formatBytes, formatTime } from '../utils/format'

const POLL_MS = 1000

const fileEl = ref(null)
const file = ref(null)
const dragging = ref(false)
const submitting = ref(false)
const error = ref('')
const job = ref(null)
const jobs = ref([])
const loadingJobs = ref(false)

const conf = ref(0.25)
const iou = ref(0.45)
const stride = ref(2)

let pollTimer = null

const outputUrl = computed(() => {
  const url = job.value?.output_url
  return url ? staticUrl(url) : ''
})

const statusMeta = computed(() => {
  const value = job.value?.status || 'queued'
  return { text: statusText(value), badge: badgeOf(value) }
})

function statusText(value) {
  return (
    {
      queued: '排队中',
      processing: '检测中',
      done: '已完成',
      failed: '失败',
      cancelled: '已取消',
    }[value] || value
  )
}

function badgeOf(value) {
  if (value === 'done') return 'badge-ok'
  if (value === 'failed') return 'badge-critical'
  if (value === 'processing') return 'badge-warning'
  return 'badge-none'
}

function acceptFile(candidate) {
  if (!candidate) return
  if (!candidate.type.startsWith('video/')) {
    error.value = '请选择视频文件（mp4 / avi / mov / mkv）。'
    return
  }
  error.value = ''
  file.value = candidate
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
  file.value = null
  error.value = ''
  job.value = null
  stopPoll()
}

async function submit() {
  if (!file.value || submitting.value) return
  submitting.value = true
  error.value = ''
  try {
    const form = buildForm({
      file: file.value,
      conf: conf.value,
      iou: iou.value,
      stride: stride.value,
      max_frames: 0,
    })
    const created = await api.detectVideo(form)
    job.value = {
      job_id: created.job_id,
      filename: file.value.name,
      status: created.status,
      progress: 0,
      processed: 0,
      total_frames: created.total_frames,
      fps: 0,
      started_at: new Date().toISOString(),
      finished_at: null,
      error: null,
      output_url: null,
      summary: null,
    }
    startPoll(created.job_id)
    loadJobs()
  } catch (err) {
    error.value = err?.message || '提交失败，请确认后端服务与本机 ffmpeg/OpenCV 正常。'
  } finally {
    submitting.value = false
  }
}

function startPoll(jobId) {
  stopPoll()
  pollTimer = window.setInterval(() => poll(jobId), POLL_MS)
  poll(jobId)
}

function stopPoll() {
  if (pollTimer !== null) {
    window.clearInterval(pollTimer)
    pollTimer = null
  }
}

async function poll(jobId) {
  try {
    const data = await api.job(jobId)
    job.value = data
    if (['done', 'failed', 'cancelled'].includes(data.status)) {
      stopPoll()
      loadJobs()
    }
  } catch (err) {
    // 任务被删除或后端瞬时异常：停止轮询并提示
    error.value = err?.message || '任务状态查询失败'
    stopPoll()
  }
}

async function selectJob(jobId) {
  stopPoll()
  error.value = ''
  try {
    job.value = await api.job(jobId)
    if (job.value.status === 'processing' || job.value.status === 'queued') startPoll(jobId)
  } catch (err) {
    error.value = err?.message || '无法加载任务详情'
  }
}

async function cancelJob() {
  const current = job.value
  if (!current) return
  try {
    await api.deleteJob(current.job_id)
  } catch (err) {
    error.value = err?.message || '取消任务失败'
  }
  stopPoll()
  job.value = null
  file.value = null
  loadJobs()
}

async function loadJobs() {
  loadingJobs.value = true
  try {
    const data = await api.jobs()
    jobs.value = Array.isArray(data?.items) ? data.items : []
  } catch {
    jobs.value = []
  } finally {
    loadingJobs.value = false
  }
}

onMounted(() => {
  loadJobs()
})

onBeforeUnmount(() => {
  stopPoll()
})
</script>

<style scoped>
.vid-body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 280px;
  gap: 18px;
}

.stage {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 340px;
  aspect-ratio: 16 / 9;
  background: var(--surface-sunken);
  border: 1px dashed var(--line-strong);
  border-radius: var(--r-md);
  overflow: hidden;
}

.stage.is-dragging {
  border-color: var(--accent);
  background: var(--accent-soft);
}

.player {
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: #0b1220;
}

.stage-mask {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 20px;
}

.mask-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  text-align: center;
  max-width: 320px;
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

.progress-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 8px;
  font-size: 12.5px;
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
  overflow-wrap: anywhere;
}

.summary {
  margin-top: 16px;
}

.table-wrap {
  max-height: 340px;
  overflow: auto;
}

.table tr.is-current td {
  background: var(--accent-soft);
}

.ellipsis {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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

.err {
  color: #b91c1c;
}

@media (max-width: 1000px) {
  .vid-body {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
