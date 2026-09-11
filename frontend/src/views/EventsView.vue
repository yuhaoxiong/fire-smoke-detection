<template>
  <div class="stack">
    <section class="card">
      <div class="card-head">
        <h3>筛选条件</h3>
        <div class="row">
          <span class="hint">共 {{ total }} 条记录</span>
          <button class="btn btn-sm" :disabled="loading" @click="load">刷新</button>
        </div>
      </div>
      <div class="card-body filters">
        <div class="field">
          <label class="label" for="f-level">级别</label>
          <select id="f-level" class="select" v-model="filters.level">
            <option value="">全部</option>
            <option value="critical">严重</option>
            <option value="warning">警告</option>
          </select>
        </div>
        <div class="field">
          <label class="label" for="f-source">来源</label>
          <select id="f-source" class="select" v-model="filters.source">
            <option value="">全部</option>
            <option value="camera">摄像头</option>
            <option value="image">图片</option>
            <option value="video">视频</option>
          </select>
        </div>
        <div class="field">
          <label class="label" for="f-cls">类别</label>
          <select id="f-cls" class="select" v-model="filters.cls">
            <option value="">全部</option>
            <option value="fire">火焰</option>
            <option value="smoke">烟雾</option>
          </select>
        </div>
        <div class="field">
          <label class="label" for="f-limit">每页</label>
          <select id="f-limit" class="select" v-model.number="filters.limit">
            <option :value="20">20</option>
            <option :value="50">50</option>
            <option :value="100">100</option>
          </select>
        </div>
        <div class="field filter-actions">
          <button class="btn btn-sm" @click="resetFilters">重置筛选</button>
          <button class="btn btn-sm btn-danger" :disabled="!total || clearing" @click="clearAll">
            {{ clearing ? '清空中…' : '清空全部' }}
          </button>
        </div>
      </div>
    </section>

    <section class="card">
      <div class="card-head">
        <h3>报警记录</h3>
        <span class="hint">{{ rangeText }}</span>
      </div>
      <div class="card-body">
        <EmptyState
          v-if="!loading && !items.length"
          title="暂无报警记录"
          desc="符合当前筛选条件的报警记录为空。"
        >
          <span v-if="hasFilters" class="hint">可尝试点击「重置筛选」查看全部记录。</span>
        </EmptyState>

        <p v-else-if="loading && !items.length" class="hint">正在加载…</p>

        <div v-else class="table-wrap">
          <table class="table">
            <thead>
              <tr>
                <th>时间</th>
                <th>级别</th>
                <th>类别</th>
                <th>来源</th>
                <th>置信度</th>
                <th>计数</th>
                <th>说明</th>
                <th>快照</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in items" :key="row.id">
                <td class="mono nowrap">{{ formatTime(row.created_at) }}</td>
                <td>
                  <span class="badge" :class="levelMeta(row.level).cls.split(' ')[1]">{{ levelMeta(row.level).text }}</span>
                </td>
                <td>
                  <span class="badge" :class="`badge-${row.cls}`">{{ row.label || row.cls }}</span>
                </td>
                <td>{{ sourceText(row.source) }}</td>
                <td class="num mono">{{ confPercent(row.conf) }}</td>
                <td class="num mono">{{ countsText(row.counts) }}</td>
                <td class="msg">{{ row.message || '—' }}</td>
                <td>
                  <button
                    v-if="row.snapshot_url"
                    class="thumb"
                    type="button"
                    title="查看快照"
                    @click="openSnapshot(row)"
                  >
                    <img :src="staticUrl(row.snapshot_url)" alt="报警快照" />
                  </button>
                  <span v-else class="muted">—</span>
                </td>
                <td class="num">
                  <button class="btn btn-sm" :disabled="deletingId === row.id" @click="removeOne(row)">
                    删除
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <div v-if="total > filters.limit" class="card-foot pager">
        <button class="btn btn-sm" :disabled="filters.offset <= 0 || loading" @click="prevPage">上一页</button>
        <span class="hint mono">{{ page }} / {{ totalPages }}</span>
        <button class="btn btn-sm" :disabled="!canNext || loading" @click="nextPage">下一页</button>
      </div>
    </section>

    <Transition name="fade">
      <div v-if="snapshot" class="modal" @click.self="snapshot = null">
        <div class="modal-card">
          <div class="modal-head">
            <strong>{{ snapshot.label || snapshot.cls }} · {{ formatTime(snapshot.created_at) }}</strong>
            <button class="btn btn-sm" @click="snapshot = null">关闭</button>
          </div>
          <img :src="staticUrl(snapshot.snapshot_url)" alt="报警快照" class="modal-img" />
          <p class="sub">{{ snapshot.message || '检测到风险目标' }}</p>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import EmptyState from '../components/EmptyState.vue'
import { api, staticUrl } from '../api/client'
import { confPercent, formatTime, levelMeta, sourceText } from '../utils/format'

const items = ref([])
const total = ref(0)
const loading = ref(false)
const clearing = ref(false)
const deletingId = ref(null)
const snapshot = ref(null)
const error = ref('')

const filters = reactive({ level: '', source: '', cls: '', limit: 50, offset: 0 })

let timer = null
let debounce = null

const page = computed(() => Math.floor(filters.offset / filters.limit) + 1)
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / filters.limit)))
const canNext = computed(() => filters.offset + filters.limit < total.value)
const hasFilters = computed(() => Boolean(filters.level || filters.source || filters.cls))

const rangeText = computed(() => {
  if (!total.value) return '无数据'
  const from = filters.offset + 1
  const to = Math.min(filters.offset + items.value.length, total.value)
  return `第 ${page.value} / ${totalPages.value} 页 · 显示 ${from}–${to} 条`
})

function countsText(counts) {
  if (!counts) return '—'
  return `火 ${counts.fire ?? 0} / 烟 ${counts.smoke ?? 0}`
}

async function load() {
  loading.value = true
  try {
    const data = await api.events({
      limit: filters.limit,
      offset: filters.offset,
      level: filters.level,
      source: filters.source,
      cls: filters.cls,
    })
    items.value = Array.isArray(data?.items) ? data.items : []
    total.value = Number(data?.total) || 0
    error.value = ''
  } catch (err) {
    error.value = err?.message || '报警记录加载失败'
    items.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function scheduleReload() {
  if (debounce !== null) window.clearTimeout(debounce)
  debounce = window.setTimeout(() => {
    filters.offset = 0
    load()
  }, 260)
}

watch(() => [filters.level, filters.source, filters.cls, filters.limit], scheduleReload)

function prevPage() {
  filters.offset = Math.max(0, filters.offset - filters.limit)
  load()
}

function nextPage() {
  if (!canNext.value) return
  filters.offset += filters.limit
  load()
}

function resetFilters() {
  filters.level = ''
  filters.source = ''
  filters.cls = ''
  filters.limit = 50
  filters.offset = 0
  load()
}

async function removeOne(row) {
  deletingId.value = row.id
  try {
    await api.deleteEvent(row.id)
    if (items.value.length === 1 && filters.offset > 0) {
      filters.offset = Math.max(0, filters.offset - filters.limit)
    }
    await load()
  } catch (err) {
    error.value = err?.message || '删除失败'
  } finally {
    deletingId.value = null
  }
}

async function clearAll() {
  if (!window.confirm('确定要清空全部报警记录吗？该操作不可撤销。')) return
  clearing.value = true
  try {
    await api.clearEvents()
    filters.offset = 0
    await load()
  } catch (err) {
    error.value = err?.message || '清空失败'
  } finally {
    clearing.value = false
  }
}

function openSnapshot(row) {
  snapshot.value = row
}

onMounted(() => {
  load()
  timer = window.setInterval(load, 15000)
})

onBeforeUnmount(() => {
  if (timer !== null) window.clearInterval(timer)
  if (debounce !== null) window.clearTimeout(debounce)
})
</script>

<style scoped>
.filters {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr)) auto;
  gap: 14px;
  align-items: end;
}

.filter-actions {
  flex-direction: row;
  gap: 8px;
}

.table-wrap {
  max-height: 560px;
  overflow: auto;
}

.nowrap {
  white-space: nowrap;
}

.msg {
  max-width: 240px;
  color: var(--text-2);
}

.thumb {
  padding: 0;
  width: 56px;
  height: 38px;
  border: 1px solid var(--line);
  border-radius: 6px;
  overflow: hidden;
  background: var(--surface-sunken);
  cursor: pointer;
}

.thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.pager {
  justify-content: center;
  gap: 12px;
}

.modal {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(15, 28, 46, 0.42);
  backdrop-filter: blur(2px);
}

.modal-card {
  width: min(880px, 100%);
  max-height: 88vh;
  overflow: auto;
  padding: 16px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-lg);
  box-shadow: 0 20px 60px rgba(15, 28, 46, 0.25);
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.modal-img {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
}

@media (max-width: 1000px) {
  .filters {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
