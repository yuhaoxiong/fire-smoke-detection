<template>
  <div class="stack">
    <!-- ------------------------------------------------ 运行状态 -->
    <section class="card">
      <div class="card-head">
        <h3>运行状态</h3>
        <div class="row">
          <span class="hint">
            <template v-if="health">v{{ health.version }} · 已运行 {{ formatSeconds(health.uptime_sec) }}</template>
            <template v-else>—</template>
          </span>
          <button class="btn btn-sm" :disabled="loading" @click="loadAll">
            {{ loading ? '读取中…' : '刷新' }}
          </button>
        </div>
      </div>
      <div class="card-body">
        <p v-if="loadError" class="notice notice-error">{{ loadError }}</p>

        <div class="facts">
          <div class="fact">
            <span class="label">服务状态</span>
            <span class="badge" :class="health ? 'badge-ok' : 'badge-none'">
              {{ health ? '在线' : '未知' }}
            </span>
          </div>
          <div class="fact">
            <span class="label">模型状态</span>
            <span class="badge" :class="modelLoaded ? 'badge-ok' : 'badge-warning'">
              {{ modelLoaded ? '已加载' : '未加载' }}
            </span>
          </div>
          <div class="fact">
            <span class="label">推理设备</span>
            <span class="mono">{{ model?.device_name || deviceText(model?.device || health?.device) }}</span>
          </div>
          <div class="fact">
            <span class="label">推理尺寸</span>
            <span class="mono">{{ model?.imgsz ? model.imgsz + ' px' : '—' }}</span>
          </div>
          <div class="fact">
            <span class="label">加载时间</span>
            <span class="mono">{{ model?.loaded_at ? formatTime(model.loaded_at) : '—' }}</span>
          </div>
          <div class="fact">
            <span class="label">权重文件</span>
            <span class="mono ellipsis" :title="model?.weights_path || ''">{{ shortPath(model?.weights_path) }}</span>
          </div>
        </div>

        <div class="classes">
          <span class="label">类别</span>
          <template v-if="classes.length">
            <span
              v-for="item in classes"
              :key="item.id"
              class="badge"
              :style="{ color: item.color, background: withAlpha(item.color) }"
            >
              <span class="dot" :style="{ background: item.color }"></span>
              {{ item.label }} · {{ item.name }}
            </span>
          </template>
          <span v-else class="hint">模型尚未加载，暂无类别信息。</span>
        </div>

        <p v-if="!modelLoaded" class="notice notice-warning">
          当前未加载任何权重，检测接口会返回 409。请先在
          <code class="mono">backend/</code> 目录执行
          <code class="mono">python scripts/download_weights.py</code>
          下载权重，再回到本页选择模型。
        </p>
      </div>
    </section>

    <!-- ------------------------------------------------ 模型选择 -->
    <section class="card">
      <div class="card-head">
        <h3>模型选择</h3>
        <div class="row">
          <span class="hint">切换后立即重载，响应约 1–5 秒</span>
          <button
            class="btn btn-sm btn-primary"
            :disabled="switching || !canSwitch"
            @click="switchModel"
          >
            {{ switching ? '切换中…' : '切换模型' }}
          </button>
        </div>
      </div>
      <div class="card-body">
        <p v-if="switchError" class="notice notice-error">{{ switchError }}</p>
        <p v-if="switchOk" class="notice notice-ok">{{ switchOk }}</p>

        <EmptyState
          v-if="!available.length"
          title="未发现可用权重"
          desc="backend/weights/ 目录下没有可用的 .pt 文件。"
        >
          <code class="mono">python scripts/download_weights.py</code>
        </EmptyState>

        <div v-else class="models">
          <label
            v-for="item in available"
            :key="item.value"
            class="model"
            :class="{ 'is-active': currentModel === item.value, 'is-missing': !item.exists }"
          >
            <input
              type="radio"
              name="model-choice"
              :value="item.value"
              :disabled="!item.exists"
              :checked="pickedModel === item.value"
              @change="pickedModel = item.value"
            />
            <span class="model-body">
              <strong>{{ item.label }}</strong>
              <span class="mono hint">{{ shortPath(item.path) }}</span>
              <span v-if="item.note" class="hint">{{ item.note }}</span>
            </span>
            <span class="model-side">
              <span v-if="currentModel === item.value" class="badge badge-ok">使用中</span>
              <span class="badge" :class="item.exists ? 'badge-none' : 'badge-warning'">
                {{ item.exists ? formatMB(item.size_mb) : '文件缺失' }}
              </span>
            </span>
          </label>
        </div>
      </div>
    </section>

    <!-- ------------------------------------------------ 推理参数 -->
    <section class="card">
      <div class="card-head">
        <h3>推理参数</h3>
        <span class="hint">改动后点击右侧「保存参数」生效</span>
      </div>
      <div class="card-body">
        <div class="form-grid">
          <div class="field">
            <label class="label" for="conf_thres">置信度阈值 conf_thres</label>
            <input
              id="conf_thres"
              class="input"
              type="range"
              min="0.05"
              max="0.95"
              step="0.01"
              v-model.number="form.conf_thres"
            />
            <span class="hint mono">{{ percent(form.conf_thres) }}</span>
          </div>

          <div class="field">
            <label class="label" for="iou_thres">NMS IoU 阈值</label>
            <input
              id="iou_thres"
              class="input"
              type="range"
              min="0.05"
              max="0.95"
              step="0.01"
              v-model.number="form.iou_thres"
            />
            <span class="hint mono">{{ percent(form.iou_thres) }}</span>
          </div>

          <div class="field">
            <label class="label" for="imgsz">推理尺寸 imgsz</label>
            <select id="imgsz" class="select" v-model.number="form.imgsz">
              <option v-for="size in imgszOptions" :key="size" :value="size">{{ size }} px</option>
            </select>
            <span class="hint">必须为 32 的倍数，越大越准但越慢</span>
          </div>

          <div class="field">
            <label class="label" for="device">推理设备 device</label>
            <select id="device" class="select" v-model="form.device">
              <option v-for="item in deviceOptions" :key="item" :value="item">{{ item }}</option>
            </select>
            <span class="hint">auto = 有 CUDA 用 GPU，否则用 CPU</span>
          </div>
        </div>
      </div>
    </section>

    <!-- ------------------------------------------------ 告警策略 -->
    <section class="card">
      <div class="card-head">
        <h3>告警策略</h3>
        <span class="hint">命中类别且 conf 达标时才产生报警记录</span>
      </div>
      <div class="card-body">
        <div class="form-grid">
          <div class="field">
            <label class="label" for="alarm_conf">告警置信度 alarm_conf</label>
            <input
              id="alarm_conf"
              class="input"
              type="range"
              min="0.05"
              max="0.95"
              step="0.01"
              v-model.number="form.alarm_conf"
            />
            <span class="hint mono">{{ percent(form.alarm_conf) }}</span>
          </div>

          <div class="field">
            <label class="label" for="alarm_consecutive">连续命中帧数</label>
            <input
              id="alarm_consecutive"
              class="input"
              type="number"
              min="1"
              max="60"
              v-model.number="form.alarm_consecutive"
            />
            <span class="hint">仅摄像头实时流生效（防抖）</span>
          </div>

          <div class="field">
            <label class="label" for="alarm_cooldown_sec">告警冷却（秒）</label>
            <input
              id="alarm_cooldown_sec"
              class="input"
              type="number"
              min="0"
              max="3600"
              v-model.number="form.alarm_cooldown_sec"
            />
            <span class="hint">同一路画面在此时间内最多一条记录</span>
          </div>

          <div class="field">
            <label class="label" for="max_upload_mb">单文件上传上限（MB）</label>
            <input
              id="max_upload_mb"
              class="input"
              type="number"
              min="1"
              max="1024"
              v-model.number="form.max_upload_mb"
            />
            <span class="hint">图片 / 视频超出后返回 413</span>
          </div>

          <div class="field">
            <span class="label">保存报警快照</span>
            <label class="switch">
              <input type="checkbox" v-model="form.save_snapshots" />
              <span>{{ form.save_snapshots ? '保存到 backend/data/snapshots' : '不保存' }}</span>
            </label>
            <span class="hint">关闭后报警记录的快照列显示为空</span>
          </div>

          <div class="field">
            <span class="label">告警提示音</span>
            <label class="switch">
              <input type="checkbox" :checked="!muted" @change="onToggleSound" />
              <span>{{ muted ? '已静音' : '响铃开启' }}</span>
            </label>
            <button class="btn btn-sm" type="button" @click="testSound">试听提示音</button>
          </div>
        </div>

        <div class="actions">
          <span v-if="saveError" class="notice notice-error">{{ saveError }}</span>
          <span v-else-if="saveOk" class="notice notice-ok">{{ saveOk }}</span>
          <span v-else class="hint">{{ dirty ? '参数已修改，尚未保存' : '参数与后端一致' }}</span>
          <span class="spacer"></span>
          <button class="btn btn-sm" :disabled="!dirty || saving" @click="resetForm">还原</button>
          <button class="btn btn-sm btn-primary" :disabled="!dirty || saving" @click="saveConfig">
            {{ saving ? '保存中…' : '保存参数' }}
          </button>
        </div>
      </div>
    </section>

    <!-- ------------------------------------------------ 维护 -->
    <section class="card">
      <div class="card-head">
        <h3>数据维护</h3>
        <span class="hint">报警记录存放在 backend/data/events.db</span>
      </div>
      <div class="card-body">
        <div class="danger-row">
          <div>
            <strong>清空全部报警记录</strong>
            <p class="hint">删除所有历史报警与统计数据，操作不可撤销。</p>
          </div>
          <div class="row">
            <template v-if="confirmingClear">
              <button class="btn btn-sm" @click="confirmingClear = false">取消</button>
              <button class="btn btn-sm btn-danger" :disabled="clearing" @click="clearEvents">
                {{ clearing ? '清空中…' : '确认清空' }}
              </button>
            </template>
            <button v-else class="btn btn-sm btn-danger" @click="confirmingClear = true">清空记录</button>
          </div>
        </div>
        <p v-if="clearMsg" class="notice notice-ok">{{ clearMsg }}</p>
        <p v-if="clearError" class="notice notice-error">{{ clearError }}</p>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import EmptyState from '../components/EmptyState.vue'
import { api } from '../api/client'
import { useAlarmSound } from '../composables/useAlarmSound'
import { deviceText, formatMB, formatSeconds, formatTime, percent } from '../utils/format'

const { muted, setMuted, beep, unlock } = useAlarmSound()

const health = ref(null)
const model = ref(null)
const loading = ref(false)
const loadError = ref('')

const switching = ref(false)
const switchError = ref('')
const switchOk = ref('')
const pickedModel = ref('')

const saving = ref(false)
const saveError = ref('')
const saveOk = ref('')
const confirmingClear = ref(false)
const clearing = ref(false)
const clearMsg = ref('')
const clearError = ref('')

const form = reactive({
  conf_thres: 0.25,
  iou_thres: 0.45,
  imgsz: 640,
  device: 'auto',
  alarm_conf: 0.5,
  alarm_consecutive: 3,
  alarm_cooldown_sec: 20,
  save_snapshots: true,
  max_upload_mb: 50,
})

/** 后端返回的原始 config，用于计算差异与「还原」。 */
const baseline = ref('')

const modelLoaded = computed(() => Boolean(model.value?.loaded) || Boolean(health.value?.model_loaded))
const classes = computed(() => model.value?.classes || [])
const available = computed(() => model.value?.available || [])
const currentModel = computed(() => model.value?.name || '')

const dirty = computed(() => serialize(form) !== baseline.value)
const canSwitch = computed(() => Boolean(pickedModel.value) && pickedModel.value !== currentModel.value)

const imgszOptions = computed(() => {
  const base = [320, 416, 512, 640, 800, 960, 1280]
  const value = Number(form.imgsz)
  return base.includes(value) ? base : [...base, value].sort((a, b) => a - b)
})

const deviceOptions = computed(() => {
  const base = ['auto', 'cpu', 'cuda:0']
  return base.includes(form.device) ? base : [...base, form.device]
})

function serialize(obj) {
  const keys = Object.keys(obj).sort()
  return JSON.stringify(keys.map((key) => [key, obj[key]]))
}

function shortPath(path) {
  if (!path) return '—'
  return String(path).replace(/\\/g, '/').replace(/^.*\/(weights\/.*)$/, '$1')
}

function withAlpha(color) {
  const hex = String(color || '').replace('#', '')
  if (hex.length !== 6) return 'var(--surface-sunken)'
  const num = Number.parseInt(hex, 16)
  const r = (num >> 16) & 255
  const g = (num >> 8) & 255
  const b = num & 255
  return `rgba(${r}, ${g}, ${b}, 0.12)`
}

function applyConfig(cfg) {
  if (!cfg) return
  Object.keys(form).forEach((key) => {
    if (cfg[key] !== undefined && cfg[key] !== null) form[key] = cfg[key]
  })
  baseline.value = serialize(form)
}

async function loadAll() {
  loading.value = true
  loadError.value = ''
  try {
    const [healthData, modelData, configData] = await Promise.all([
      api.health(),
      api.model(),
      api.getConfig(),
    ])
    health.value = healthData || null
    model.value = modelData || null
    if (!pickedModel.value || pickedModel.value === currentModel.value) {
      pickedModel.value = modelData?.name || ''
    }
    applyConfig(configData)
  } catch (err) {
    loadError.value = err?.message || '无法读取后端配置'
  } finally {
    loading.value = false
  }
}

async function switchModel() {
  if (!canSwitch.value) return
  switching.value = true
  switchError.value = ''
  switchOk.value = ''
  const target = pickedModel.value
  try {
    const info = await api.switchModel(target)
    model.value = info || model.value
    pickedModel.value = info?.name || target
    switchOk.value = `已切换到 ${target}${info?.device ? ` · ${deviceText(info.device)}` : ''}`
    const configData = await api.getConfig()
    applyConfig(configData)
    await loadAll()
  } catch (err) {
    switchError.value = err?.message || '模型切换失败'
  } finally {
    switching.value = false
  }
}

/** 只把真正变化的字段发给后端（PUT /api/config 支持部分更新）。 */
function buildPatch() {
  const patch = {}
  Object.keys(form).forEach((key) => {
    const original = JSON.parse(baseline.value || '[]').find((pair) => pair[0] === key)
    if (!original || original[1] !== form[key]) patch[key] = form[key]
  })
  return patch
}

async function saveConfig() {
  if (!dirty.value) return
  saving.value = true
  saveError.value = ''
  saveOk.value = ''
  try {
    const patch = buildPatch()
    const updated = await api.updateConfig(patch)
    applyConfig(updated)
    saveOk.value = `已保存 ${Object.keys(patch).join('、')}`
  } catch (err) {
    saveError.value = err?.message || '保存失败'
  } finally {
    saving.value = false
  }
}

function resetForm() {
  saveError.value = ''
  saveOk.value = ''
  loadAll()
}

function onToggleSound(event) {
  unlock()
  setMuted(!event.target.checked)
  if (event.target.checked) beep('warning')
}

function testSound() {
  unlock()
  beep('critical')
}

async function clearEvents() {
  clearing.value = true
  clearError.value = ''
  clearMsg.value = ''
  try {
    const data = await api.clearEvents()
    clearMsg.value = `已清空 ${data?.deleted ?? 0} 条报警记录`
    confirmingClear.value = false
  } catch (err) {
    clearError.value = err?.message || '清空失败'
  } finally {
    clearing.value = false
  }
}

onMounted(loadAll)
</script>

<style scoped>
.facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 10px 18px;
  margin-bottom: 16px;
}

.fact {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  background: var(--surface-soft);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
}

.fact .mono {
  font-size: 12.5px;
  color: var(--text-2);
}

.ellipsis {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.classes {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.models {
  display: grid;
  gap: 8px;
}

.model {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  background: var(--surface);
  border: 1px solid var(--line-strong);
  border-radius: var(--r-sm);
  cursor: pointer;
  transition: border-color 0.16s, box-shadow 0.16s, background 0.16s;
}

.model:hover {
  border-color: var(--accent);
}

.model.is-active {
  border-color: var(--accent);
  background: var(--accent-soft);
}

.model.is-missing {
  opacity: 0.62;
  cursor: not-allowed;
}

.model input[type='radio'] {
  accent-color: var(--accent);
  width: 15px;
  height: 15px;
  flex: 0 0 auto;
}

.model-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.model-body strong {
  font-size: 13.5px;
  font-weight: 600;
}

.model-side {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 0 0 auto;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 16px 20px;
}

.actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 18px;
  padding-top: 14px;
  border-top: 1px solid var(--line);
}

.danger-row {
  display: flex;
  align-items: center;
  gap: 16px;
}

.danger-row > div:first-child {
  min-width: 0;
}

.danger-row > .row {
  margin-left: auto;
}

.danger-row strong {
  font-size: 13.5px;
}

.notice {
  display: inline-block;
  margin: 0 0 12px;
  padding: 8px 12px;
  font-size: 12.5px;
  line-height: 1.6;
  border-radius: var(--r-sm);
  border: 1px solid var(--line);
  background: var(--surface-soft);
  color: var(--text-2);
}

.notice code {
  padding: 1px 5px;
  background: var(--surface-sunken);
  border-radius: 4px;
}

.notice-error {
  color: #b42318;
  border-color: rgba(180, 35, 24, 0.28);
  background: rgba(180, 35, 24, 0.06);
}

.notice-warning {
  color: #8a5a00;
  border-color: rgba(180, 120, 0, 0.28);
  background: rgba(180, 120, 0, 0.07);
}

.notice-ok {
  color: #0b7a48;
  border-color: rgba(11, 122, 72, 0.28);
  background: rgba(11, 122, 72, 0.07);
}

@media (max-width: 720px) {
  .danger-row {
    flex-direction: column;
    align-items: flex-start;
  }

  .danger-row > .row {
    margin-left: 0;
  }
}
</style>
