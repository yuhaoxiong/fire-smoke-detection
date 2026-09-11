/**
 * 后端接口客户端 —— 字段与 docs/API.md 严格一致。
 *
 * 开发模式下 VITE_API_BASE 留空，由 vite 代理转发到 127.0.0.1:8000；
 * 生产构建默认直连后端，可用 VITE_API_BASE 覆盖。
 */
const RAW_BASE = import.meta.env.VITE_API_BASE

export const API_BASE = RAW_BASE ?? (import.meta.env.DEV ? '' : 'http://127.0.0.1:8000')

export class ApiError extends Error {
  constructor(message, status = 0) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export function apiUrl(path = '') {
  const normalized = path.startsWith('/') ? path : `/${path}`
  return `${API_BASE}${normalized}`
}

/** 静态资源（/static/...）转成可直接放到 src 里的地址。 */
export function staticUrl(path) {
  if (!path) return ''
  if (/^(https?:)?\/\//.test(path) || path.startsWith('data:')) return path
  return apiUrl(path)
}

/** WebSocket 地址：开发模式走 vite 的 ws 代理，生产模式直连后端。 */
export function wsUrl(path) {
  const suffix = path.startsWith('/') ? path : `/${path}`
  if (!API_BASE) {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${proto}//${window.location.host}${suffix}`
  }
  return `${API_BASE.replace(/^http/, 'ws')}${suffix}`
}

function toQuery(params) {
  const search = new URLSearchParams()
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return
    search.append(key, String(value))
  })
  const text = search.toString()
  return text ? `?${text}` : ''
}

async function parse(res) {
  const text = await res.text()
  let data = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = null
    }
  }
  if (!res.ok) {
    let detail = `请求失败（HTTP ${res.status}）`
    if (data && data.detail) {
      detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
    }
    throw new ApiError(detail, res.status)
  }
  return data
}

async function request(path, { method = 'GET', body, headers, signal } = {}) {
  const res = await fetch(apiUrl(path), { method, headers, body, signal })
  return parse(res)
}

function json(payload) {
  return { 'Content-Type': 'application/json', body: JSON.stringify(payload) }
}

/** 把普通对象转成 multipart 表单，自动跳过空值。 */
export function buildForm(fields) {
  const form = new FormData()
  Object.entries(fields).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return
    form.append(key, value)
  })
  return form
}

export const api = {
  // 系统与模型
  health: (signal) => request('/api/health', { signal }),
  model: (signal) => request('/api/model', { signal }),
  switchModel: (name) => request('/api/model/switch', { method: 'POST', ...json({ name }) }),

  // 运行参数
  getConfig: (signal) => request('/api/config', { signal }),
  updateConfig: (patch) => request('/api/config', { method: 'PUT', ...json(patch) }),

  // 图片检测
  detectImage: (form) => request('/api/detect/image', { method: 'POST', body: form }),
  detectImageRaw: async (form) => {
    const res = await fetch(apiUrl('/api/detect/image/raw'), { method: 'POST', body: form })
    if (!res.ok) return parse(res)
    return res.blob()
  },

  // 视频检测
  detectVideo: (form) => request('/api/detect/video', { method: 'POST', body: form }),
  jobs: (signal) => request('/api/jobs', { signal }),
  job: (jobId, signal) => request(`/api/jobs/${encodeURIComponent(jobId)}`, { signal }),
  deleteJob: (jobId) => request(`/api/jobs/${encodeURIComponent(jobId)}`, { method: 'DELETE' }),

  // 事件与统计
  events: (params, signal) => request(`/api/events${toQuery(params)}`, { signal }),
  eventStats: (hours = 24, signal) => request(`/api/events/stats?hours=${hours}`, { signal }),
  deleteEvent: (id) => request(`/api/events/${id}`, { method: 'DELETE' }),
  clearEvents: () => request('/api/events', { method: 'DELETE' }),
}

export { toQuery }
