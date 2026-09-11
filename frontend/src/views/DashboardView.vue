<template>
  <div class="stack">
    <div class="grid grid-kpi">
      <KpiCard label="报警总数 · 24h" :value="stats.total" tone="accent" :hint="`统计窗口 ${hours} 小时`" />
      <KpiCard label="火焰告警" :value="stats.fire" tone="fire" hint="命中 fire 类别" />
      <KpiCard label="烟雾告警" :value="stats.smoke" tone="smoke" hint="命中 smoke 类别" />
      <KpiCard label="严重级别" :value="stats.critical" tone="danger" hint="level = critical" />
      <KpiCard label="最近 1 小时" :value="stats.recent" tone="warn" hint="滚动窗口内新增" />
    </div>

    <div class="grid grid-2">
      <section class="card">
        <div class="card-head">
          <h3>小时报警趋势</h3>
          <span class="legend">
            <span class="legend-item"><i class="swatch swatch-fire"></i>火焰</span>
            <span class="legend-item"><i class="swatch swatch-smoke"></i>烟雾</span>
          </span>
        </div>
        <div class="card-body">
          <EmptyState
            v-if="!hourRows.length"
            title="暂无报警数据"
            desc="检测到火焰或烟雾后，这里会按小时展示趋势。"
          />
          <div v-else class="chart">
            <svg :viewBox="`0 0 ${chart.w} ${chart.h}`" class="bars" role="img"
                 aria-label="按小时的火焰与烟雾报警数量柱状图">
              <g v-for="line in chart.gridLines" :key="`g${line.y}`">
                <line :x1="chart.padL" :x2="chart.w - chart.padR" :y1="line.y" :y2="line.y"
                      stroke="var(--line)" stroke-width="1" />
                <text :x="chart.padL - 8" :y="line.y + 3.5" text-anchor="end"
                      class="axis">{{ line.value }}</text>
              </g>
              <g v-for="bar in chart.bars" :key="bar.key">
                <rect :x="bar.x" :y="bar.fireY" :width="bar.width" :height="bar.fireH"
                      fill="var(--fire)" rx="2">
                  <title>{{ bar.label }} 火焰 {{ bar.fire }}</title>
                </rect>
                <rect :x="bar.x" :y="bar.smokeY" :width="bar.width" :height="bar.smokeH"
                      fill="var(--smoke)" rx="2">
                  <title>{{ bar.label }} 烟雾 {{ bar.smoke }}</title>
                </rect>
                <text v-if="bar.showLabel" :x="bar.cx" :y="chart.h - 6" text-anchor="middle"
                      class="axis">{{ bar.tick }}</text>
              </g>
            </svg>
          </div>
        </div>
        <div class="card-foot">
          <span class="hint">窗口内共 {{ stats.total }} 条报警，峰值 {{ peakTotal }} 条/小时。</span>
        </div>
      </section>

      <section class="card">
        <div class="card-head">
          <h3>报警来源占比</h3>
          <span class="hint">按接入方式统计</span>
        </div>
        <div class="card-body">
          <EmptyState v-if="!sourceRows.length" title="暂无来源数据" desc="尚无报警事件，无法计算占比。" />
          <div v-else class="donut-wrap">
            <svg viewBox="0 0 120 120" class="donut" role="img" aria-label="报警来源占比环形图">
              <circle cx="60" cy="60" r="46" fill="none" stroke="var(--surface-sunken)" stroke-width="14" />
              <circle
                v-for="seg in donut"
                :key="seg.source"
                cx="60"
                cy="60"
                r="46"
                fill="none"
                :stroke="seg.color"
                stroke-width="14"
                :stroke-dasharray="seg.dash"
                :stroke-dashoffset="seg.offset"
                transform="rotate(-90 60 60)"
              >
                <title>{{ seg.label }} {{ seg.count }} 条（{{ seg.pct }}）</title>
              </circle>
              <text x="60" y="56" text-anchor="middle" class="donut-num">{{ stats.total }}</text>
              <text x="60" y="72" text-anchor="middle" class="axis">报警总数</text>
            </svg>
            <ul class="legend-list">
              <li v-for="seg in donut" :key="`l${seg.source}`">
                <i class="swatch" :style="{ background: seg.color }"></i>
                <span class="legend-name">{{ seg.label }}</span>
                <span class="legend-num mono">{{ seg.count }}</span>
                <span class="legend-pct">{{ seg.pct }}</span>
              </li>
            </ul>
          </div>
        </div>
      </section>
    </div>

    <div class="grid grid-2">
      <section class="card">
        <div class="card-head">
          <h3>系统与模型</h3>
          <span class="badge" :class="modelLoaded ? 'badge-ok' : 'badge-warning'">
            {{ modelLoaded ? '模型已加载' : '模型未加载' }}
          </span>
        </div>
        <div class="card-body">
          <dl class="kv">
            <div><dt>后端状态</dt><dd>{{ state.connected ? '正常' : '未连接' }}</dd></div>
            <div><dt>运行时长</dt><dd class="mono">{{ formatSeconds(state.health?.uptime_sec) }}</dd></div>
            <div><dt>当前模型</dt><dd class="mono">{{ modelName }}</dd></div>
            <div><dt>推理设备</dt><dd>{{ deviceText(deviceLabel) }}</dd></div>
            <div><dt>输入尺寸</dt><dd class="mono">{{ state.model?.imgsz || '—' }}</dd></div>
            <div><dt>权重体积</dt><dd class="mono">{{ formatMB(state.model?.weights_size_mb) }}</dd></div>
            <div><dt>可用类别</dt><dd>{{ classNames }}</dd></div>
            <div><dt>接口版本</dt><dd class="mono">v{{ state.health?.version || '1.0.0' }}</dd></div>
          </dl>
        </div>
        <div class="card-foot">
          <RouterLink class="btn btn-sm" to="/settings">前往参数设置</RouterLink>
          <span class="spacer"></span>
          <span class="hint">更新于 {{ updatedText }}</span>
        </div>
      </section>

      <section class="card">
        <div class="card-head">
          <h3>最近一次报警</h3>
          <RouterLink class="hint" to="/events">查看全部 →</RouterLink>
        </div>
        <div class="card-body">
          <EmptyState v-if="!stats.latest" title="暂无报警记录" desc="系统运行正常，未检测到火焰或烟雾。" />
          <div v-else class="latest">
            <div class="latest-main">
              <span class="badge" :class="latestMeta.badge">{{ latestMeta.text }}</span>
              <span class="badge" :class="`badge-${stats.latest.cls}`">{{ stats.latest.label }}</span>
              <span class="muted">{{ sourceText(stats.latest.source) }}</span>
              <span class="span spacer"></span>
              <span class="mono muted">{{ formatTime(stats.latest.created_at) }}</span>
            </div>
            <p class="latest-msg">{{ stats.latest.message || '检测到风险目标' }}</p>
            <div class="latest-stats">
              <span>最高置信度 <b class="mono">{{ confPercent(stats.latest.conf) }}</b></span>
              <span>火焰 <b class="mono">{{ stats.latest.counts?.fire ?? 0 }}</b></span>
              <span>烟雾 <b class="mono">{{ stats.latest.counts?.smoke ?? 0 }}</b></span>
            </div>
            <img
              v-if="stats.latest.snapshot_url"
              class="snapshot"
              :src="staticUrl(stats.latest.snapshot_url)"
              alt="报警快照"
            />
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import EmptyState from '../components/EmptyState.vue'
import KpiCard from '../components/KpiCard.vue'
import { api, staticUrl } from '../api/client'
import { useBackend } from '../composables/useBackend'
import {
  confPercent,
  deviceText,
  formatMB,
  formatSeconds,
  formatTime,
  levelMeta,
  sourceText,
} from '../utils/format'

const HOURS = 24
const SOURCE_COLORS = { camera: '#1e6fff', image: '#7c8ba1', video: '#10b981' }
const SOURCE_LABELS = { camera: '摄像头实时', image: '图片检测', video: '视频检测' }
const POLL_MS = 12000

const { state, modelName, deviceLabel, modelLoaded } = useBackend()

const hours = ref(HOURS)
const stats = ref(emptyStats())
const error = ref('')
const updatedAt = ref(0)

let timer = null

function emptyStats() {
  return {
    total: 0,
    fire: 0,
    smoke: 0,
    critical: 0,
    warning: 0,
    recent: 0,
    by_hour: [],
    by_source: [],
    latest: null,
  }
}

async function load() {
  try {
    const data = await api.eventStats(hours.value)
    stats.value = { ...emptyStats(), ...data }
    error.value = ''
  } catch (err) {
    error.value = err?.message || '统计加载失败'
  } finally {
    updatedAt.value = Date.now()
  }
}

const updatedText = computed(() => {
  if (!updatedAt.value) return '—'
  return formatTime(new Date(updatedAt.value).toISOString())
})

const classNames = computed(() => {
  const list = state.model?.classes || []
  if (!list.length) return '—'
  return list.map((item) => item.label || item.name).join(' / ')
})

const latestMeta = computed(() => levelMeta(stats.value.latest?.level))

/* ---------- 小时趋势（纯 SVG 柱状图） ---------- */
const hourRows = computed(() => {
  const rows = Array.isArray(stats.value.by_hour) ? stats.value.by_hour : []
  return rows.map((row) => ({
    t: row.t,
    label: formatTime(row.t),
    tick: formatHourLabel(row.t),
    fire: Number(row.fire) || 0,
    smoke: Number(row.smoke) || 0,
  }))
})

const peakTotal = computed(() =>
  hourRows.value.reduce((max, row) => Math.max(max, row.fire + row.smoke), 0),
)

function formatHourLabel(iso) {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return `${String(d.getHours()).padStart(2, '0')}时`
}

const chart = computed(() => {
  const w = 640
  const h = 240
  const padL = 34
  const padR = 12
  const padT = 14
  const padB = 26
  const rows = hourRows.value
  const innerW = w - padL - padR
  const innerH = h - padT - padB
  const maxValue = Math.max(1, peakTotal.value)
  const niceMax = niceCeil(maxValue)

  const gridLines = []
  for (let i = 0; i <= 4; i += 1) {
    const value = Math.round((niceMax / 4) * i)
    const y = padT + innerH - (innerH * i) / 4
    gridLines.push({ y, value })
  }

  const gap = rows.length > 1 ? Math.min(10, innerW / rows.length / 3) : 0
  const slot = rows.length ? innerW / rows.length : innerW
  const width = Math.max(3, slot - gap)
  const labelStep = Math.ceil(rows.length / 12)

  const bars = rows.map((row, index) => {
    const x = padL + slot * index + (slot - width) / 2
    const total = row.fire + row.smoke
    const totalH = (innerH * total) / niceMax
    const fireH = (innerH * row.fire) / niceMax
    const smokeH = (innerH * row.smoke) / niceMax
    const baseY = padT + innerH
    return {
      key: `${row.t}-${index}`,
      x,
      cx: x + width / 2,
      width,
      label: row.label,
      tick: row.tick,
      showLabel: index % labelStep === 0 || index === rows.length - 1,
      fire: row.fire,
      smoke: row.smoke,
      total,
      fireH,
      smokeH,
      fireY: baseY - fireH,
      smokeY: baseY - fireH - smokeH,
      totalH,
    }
  })

  return { w, h, padL, padR, gridLines, bars }
})

function niceCeil(value) {
  if (value <= 4) return 4
  const pow = 10 ** Math.floor(Math.log10(value))
  const norm = value / pow
  const step = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10
  return step * pow
}

/* ---------- 来源占比（纯 SVG 环形图） ---------- */
const sourceRows = computed(() => {
  const rows = Array.isArray(stats.value.by_source) ? stats.value.by_source : []
  return rows
    .map((row) => ({ source: row.source, count: Number(row.count) || 0 }))
    .filter((row) => row.count > 0)
})

const donut = computed(() => {
  const rows = sourceRows.value
  const total = rows.reduce((sum, row) => sum + row.count, 0) || 1
  const circumference = 2 * Math.PI * 46
  let acc = 0
  return rows.map((row) => {
    const fraction = row.count / total
    const length = circumference * fraction
    const seg = {
      source: row.source,
      count: row.count,
      label: SOURCE_LABELS[row.source] || sourceText(row.source),
      color: SOURCE_COLORS[row.source] || '#0ea5e9',
      pct: `${(fraction * 100).toFixed(1)}%`,
      dash: `${length} ${circumference - length}`,
      offset: -acc,
    }
    acc += length
    return seg
  })
})

onMounted(() => {
  load()
  timer = window.setInterval(load, POLL_MS)
})

onBeforeUnmount(() => {
  if (timer !== null) window.clearInterval(timer)
})
</script>

<style scoped>
.kv {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 20px;
  margin: 0;
}

.kv > div {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  padding: 7px 0;
  border-bottom: 1px dashed var(--line);
}

.kv dt {
  font-size: 12.5px;
  color: var(--text-3);
}

.kv dd {
  margin: 0;
  font-size: 13px;
  color: var(--text);
  text-align: right;
}

.legend {
  display: inline-flex;
  gap: 12px;
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  color: var(--text-3);
}

.swatch {
  display: inline-block;
  width: 9px;
  height: 9px;
  border-radius: 2px;
}

.swatch-fire {
  background: var(--fire);
}

.swatch-smoke {
  background: var(--smoke);
}

.chart {
  width: 100%;
}

.bars {
  display: block;
  width: 100%;
  height: 240px;
}

.bars :deep(.axis) {
  font-size: 10.5px;
  fill: var(--text-3);
}

.donut-wrap {
  display: flex;
  align-items: center;
  gap: 24px;
}

.donut {
  width: 168px;
  height: 168px;
  flex: 0 0 auto;
}

.donut :deep(.donut-num) {
  font-size: 22px;
  font-weight: 600;
  fill: var(--text);
}

.legend-list {
  list-style: none;
  margin: 0;
  padding: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 9px;
}

.legend-list li {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.legend-name {
  color: var(--text-2);
}

.legend-num {
  margin-left: auto;
  color: var(--text);
}

.legend-pct {
  width: 52px;
  text-align: right;
  color: var(--text-3);
  font-size: 12px;
}

.latest {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.latest-main {
  display: flex;
  align-items: center;
  gap: 8px;
}

.latest-msg {
  margin: 0;
  font-size: 13.5px;
  color: var(--text-2);
}

.latest-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  font-size: 12.5px;
  color: var(--text-3);
}

.latest-stats b {
  color: var(--text);
  font-weight: 600;
}

.snapshot {
  width: 100%;
  max-height: 220px;
  object-fit: cover;
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
}

@media (max-width: 860px) {
  .donut-wrap {
    flex-direction: column;
  }
}
</style>
