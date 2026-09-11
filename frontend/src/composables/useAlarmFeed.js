/**
 * 全局告警流：各检测页把命中的告警推进来，App 顶部横幅统一展示 + 响铃。
 */
import { reactive, readonly } from 'vue'
import { useAlarmSound } from './useAlarmSound'

const AUTO_DISMISS_MS = 9000

const state = reactive({
  current: null, // { level, label, message, source, at, eventId, snapshotUrl }
  recent: [], // 最近的告警，最新在前（最多 20 条）
})

let timer = null
const { beep } = useAlarmSound()

function push(alarm, { source = 'camera', meta = '' } = {}) {
  if (!alarm || !alarm.active) return
  const entry = {
    level: alarm.level || 'warning',
    label: alarm.label || null,
    message: alarm.message || '',
    eventId: alarm.event_id ?? null,
    snapshotUrl: alarm.snapshot_url || null,
    source,
    meta,
    at: Date.now(),
  }
  // 同一条事件（event_id 相同）不重复播报
  const duplicated =
    entry.eventId !== null && state.recent.some((item) => item.eventId === entry.eventId)
  if (duplicated) return

  state.current = entry
  state.recent = [entry, ...state.recent].slice(0, 20)
  beep(entry.level)

  if (timer !== null) window.clearTimeout(timer)
  timer = window.setTimeout(() => {
    // 只清理「还是这一条」的横幅，避免误清新告警
    if (state.current && state.current.at === entry.at) state.current = null
  }, AUTO_DISMISS_MS)
}

function dismiss() {
  state.current = null
  if (timer !== null) {
    window.clearTimeout(timer)
    timer = null
  }
}

function clearRecent() {
  state.recent = []
}

export function useAlarmFeed() {
  return { state: readonly(state), push, dismiss, clearRecent }
}
