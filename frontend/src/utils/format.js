/** 展示层格式化工具。 */

export const START_COMMAND =
  'cd backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000'

const pad = (n) => String(n).padStart(2, '0')

/** ISO8601（带时区）-> `MM-DD HH:mm:ss`，解析失败时原样返回。 */
export function formatTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(
    d.getMinutes(),
  )}:${pad(d.getSeconds())}`
}

/** ISO8601 -> `HH:mm`，用于图表刻度。 */
export function formatHour(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return `${pad(d.getHours())}:00`
}

/** 相对时间：刚刚 / 3 分钟前 / 2 小时前 / 具体日期。 */
export function timeAgo(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const diff = (Date.now() - d.getTime()) / 1000
  if (diff < 0) return formatTime(iso)
  if (diff < 45) return '刚刚'
  if (diff < 3600) return `${Math.round(diff / 60)} 分钟前`
  if (diff < 86400) return `${Math.round(diff / 3600)} 小时前`
  if (diff < 86400 * 7) return `${Math.round(diff / 86400)} 天前`
  return formatTime(iso)
}

export function formatSeconds(sec) {
  const s = Math.max(0, Math.round(Number(sec) || 0))
  if (s < 60) return `${s} 秒`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m} 分 ${pad(s % 60)} 秒`
  const h = Math.floor(m / 60)
  return `${h} 小时 ${pad(m % 60)} 分`
}

export function formatBytes(bytes) {
  const n = Number(bytes) || 0
  if (n < 1024) return `${n} B`
  if (n < 1048576) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1073741824) return `${(n / 1048576).toFixed(1)} MB`
  return `${(n / 1073741824).toFixed(2)} GB`
}

export function formatMB(mb) {
  const n = Number(mb)
  if (!Number.isFinite(n) || n <= 0) return '—'
  return n < 1 ? `${(n * 1024).toFixed(0)} KB` : `${n.toFixed(2)} MB`
}

export function percent(value, digits = 1) {
  const n = Number(value)
  if (!Number.isFinite(n)) return '—'
  return `${(n * 100).toFixed(digits)}%`
}

export function confPercent(value) {
  const n = Number(value)
  if (!Number.isFinite(n)) return '—'
  return `${Math.round(n * 100)}%`
}

/** 告警级别 -> 文案与徽标样式。 */
export function levelMeta(level) {
  switch (level) {
    case 'critical':
      return { text: '严重', cls: 'badge badge-critical' }
    case 'warning':
      return { text: '警告', cls: 'badge badge-warning' }
    default:
      return { text: '正常', cls: 'badge badge-none' }
  }
}

/** 来源 -> 中文名。 */
export function sourceText(source) {
  return { camera: '摄像头', image: '图片', video: '视频' }[source] || source || '未知'
}

/** 类别 -> 中文名 + 颜色（后端也会下发 color，这里作为兜底）。 */
export function classMeta(cls) {
  if (cls === 'fire' || cls === 'flame') {
    return { text: '火焰', color: '#ff4d3d', badge: 'badge badge-fire' }
  }
  if (cls === 'smoke') {
    return { text: '烟雾', color: '#7c8ba1', badge: 'badge badge-smoke' }
  }
  return { text: cls || '未知', color: '#0ea5e9', badge: 'badge badge-none' }
}

/** 设备串 -> 更友好的显示。 */
export function deviceText(device) {
  if (!device) return '未知'
  return device.startsWith('cuda') ? `GPU ${device.replace('cuda:', '#')}` : device.toUpperCase()
}
