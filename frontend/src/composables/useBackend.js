/**
 * 后端连接状态：全局共享一份，所有页面复用。
 * 启动后先探一次 /api/health 与 /api/model，之后按固定间隔轮询。
 */
import { computed, reactive, readonly } from 'vue'
import { api } from '../api/client'

const state = reactive({
  probed: false,
  connected: false,
  error: '',
  health: null,
  model: null,
  checkedAt: 0,
  loading: false,
})

let timer = null
let inflight = null

const DEFAULT_CLASSES = [
  { id: 0, name: 'fire', label: '火焰', color: '#ff4d3d' },
  { id: 1, name: 'smoke', label: '烟雾', color: '#7c8ba1' },
]

async function refresh() {
  if (inflight) return inflight
  state.loading = true
  inflight = (async () => {
    try {
      const [health, model] = await Promise.all([api.health(), api.model()])
      state.health = health
      state.model = model
      state.connected = true
      state.error = ''
    } catch (err) {
      state.connected = false
      state.error = err?.message || '无法连接后端服务'
    } finally {
      state.probed = true
      state.checkedAt = Date.now()
      state.loading = false
      inflight = null
    }
  })()
  return inflight
}

function start(intervalMs = 6000) {
  stop()
  refresh()
  timer = window.setInterval(refresh, intervalMs)
}

function stop() {
  if (timer !== null) {
    window.clearInterval(timer)
    timer = null
  }
}

export function useBackend() {
  const classes = computed(() => {
    const list = state.model?.classes
    return list && list.length ? list : DEFAULT_CLASSES
  })

  const modelLoaded = computed(
    () => Boolean(state.model?.loaded) || Boolean(state.health?.model_loaded),
  )

  const deviceLabel = computed(() => state.model?.device || state.health?.device || '—')

  const modelName = computed(() => state.model?.name || state.health?.model || '—')

  return {
    state: readonly(state),
    raw: state,
    classes,
    modelLoaded,
    deviceLabel,
    modelName,
    refresh,
    start,
    stop,
  }
}

export { DEFAULT_CLASSES }
