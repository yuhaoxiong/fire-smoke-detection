<template>
  <div class="shell">
    <header class="topbar">
      <RouterLink to="/" class="brand">
        <span class="brand-mark" aria-hidden="true">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 3c2.4 3 4 5 4 7.4a4 4 0 0 1-8 0c0-.7.2-1.4.5-2.1" />
            <path d="M12 21a5 5 0 0 0 5-5c0-2.5-2-4.5-3.4-6.2" />
            <path d="M4 20h16" />
          </svg>
        </span>
        <span class="brand-text">
          <strong>火灾烟雾智能识别系统</strong>
          <em>YOLOv8 · 实时 / 图片 / 视频检测</em>
        </span>
      </RouterLink>

      <nav class="nav" aria-label="主导航">
        <RouterLink
          v-for="item in navItems"
          :key="item.name"
          :to="{ name: item.name }"
          class="nav-link"
          :class="{ 'is-active': route.name === item.name }"
        >
          {{ item.nav }}
        </RouterLink>
      </nav>

      <div class="tools">
        <button
          type="button"
          class="sound-btn"
          :class="{ 'is-muted': muted }"
          :title="muted ? '开启告警提示音' : '关闭告警提示音'"
          @click="onToggleSound"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M11 5 6.5 9H3v6h3.5L11 19z" />
            <template v-if="!muted">
              <path d="M15.5 9.2a4 4 0 0 1 0 5.6" />
              <path d="M18.2 6.5a7.5 7.5 0 0 1 0 11" />
            </template>
            <template v-else>
              <path d="M16 10.5l4 3.5" />
              <path d="M20 10.5l-4 3.5" />
            </template>
          </svg>
          <span>{{ muted ? '静音' : '响铃' }}</span>
        </button>

        <span class="status" :class="status.cls" :title="status.title">
          <span class="dot" :class="{ 'dot-pulse': status.pulsing }"></span>
          {{ status.text }}
        </span>
      </div>
    </header>

    <Transition name="fade">
      <div v-if="feed.current" class="alarm" :class="`alarm-${feed.current.level}`" role="alert">
        <span class="alarm-icon" aria-hidden="true">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 4 2.6 20h18.8z" />
            <path d="M12 10v4" />
            <path d="M12 17.2h.01" />
          </svg>
        </span>
        <div class="alarm-body">
          <strong>{{ feed.current.label || '告警' }} · {{ levelText(feed.current.level) }}</strong>
          <span class="alarm-msg">{{ feed.current.message || '检测到风险目标' }}</span>
        </div>
        <span class="alarm-meta">
          {{ sourceText(feed.current.source) }}
          <template v-if="feed.current.at"> · {{ timeAgo(new Date(feed.current.at).toISOString()) }}</template>
        </span>
        <button type="button" class="alarm-close" title="关闭提示" @click="dismiss">✕</button>
      </div>
    </Transition>

    <main class="main">
      <div class="page-head">
        <div>
          <h1 class="page-title">{{ route.meta.title || '运行总览' }}</h1>
          <p class="page-desc">{{ route.meta.desc || '' }}</p>
        </div>
        <div v-if="state.connected" class="page-meta">
          <span class="chip mono">{{ modelName }}</span>
          <span class="chip">{{ deviceText(deviceLabel) }}</span>
        </div>
      </div>

      <BackendGate>
        <RouterView />
      </BackendGate>
    </main>

    <footer class="foot">
      <span>火灾烟雾智能识别系统 v{{ state.health?.version || '1.0.0' }}</span>
      <span class="spacer"></span>
      <span v-if="state.connected">
        运行 {{ formatSeconds(state.health?.uptime_sec) }}
      </span>
      <span v-else-if="state.probed">后端未连接</span>
    </footer>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import BackendGate from './components/BackendGate.vue'
import { useBackend } from './composables/useBackend'
import { useAlarmFeed } from './composables/useAlarmFeed'
import { useAlarmSound } from './composables/useAlarmSound'
import { deviceText, formatSeconds, levelMeta, sourceText, timeAgo } from './utils/format'

const route = useRoute()
const { state, modelName, deviceLabel, start, stop } = useBackend()
const { state: feed, dismiss } = useAlarmFeed()
const { muted, toggleMuted, unlock } = useAlarmSound()

const navItems = [
  { name: 'dashboard', nav: '总览' },
  { name: 'live', nav: '实时检测' },
  { name: 'image', nav: '图片检测' },
  { name: 'video', nav: '视频检测' },
  { name: 'events', nav: '报警记录' },
  { name: 'settings', nav: '参数设置' },
]

const status = computed(() => {
  if (!state.probed) {
    return { cls: 'is-pending', text: '连接中…', title: '正在探测后端服务', pulsing: true }
  }
  if (!state.connected) {
    return { cls: 'is-offline', text: '后端未连接', title: state.error || '无法访问后端服务', pulsing: false }
  }
  return {
    cls: 'is-online',
    text: state.health?.model_loaded ? '已连接' : '已连接 · 模型未加载',
    title: state.health?.model_loaded ? '推理服务正常' : '后端在线，但模型尚未加载',
    pulsing: false,
  }
})

function levelText(level) {
  return levelMeta(level).text
}

function onToggleSound() {
  unlock()
  toggleMuted()
}

onMounted(() => {
  start(6000)
  window.addEventListener('pointerdown', unlock, { once: true })
})

onBeforeUnmount(() => {
  stop()
  window.removeEventListener('pointerdown', unlock)
})
</script>

<style scoped>
.shell {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

/* ---------- 顶栏 ---------- */
.topbar {
  position: sticky;
  top: 0;
  z-index: 30;
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 12px 24px;
  background: rgba(255, 255, 255, 0.86);
  backdrop-filter: saturate(160%) blur(10px);
  border-bottom: 1px solid var(--line);
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  color: inherit;
  text-decoration: none;
  flex: 0 0 auto;
}

.brand-mark {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: var(--r-sm);
  color: #fff;
  background: linear-gradient(160deg, var(--accent) 0%, var(--accent-strong) 100%);
  box-shadow: 0 4px 12px rgba(30, 111, 255, 0.25);
}

.brand-text {
  display: flex;
  flex-direction: column;
  line-height: 1.25;
}

.brand-text strong {
  font-size: 15px;
  letter-spacing: 0.2px;
}

.brand-text em {
  font-size: 11.5px;
  font-style: normal;
  color: var(--text-3);
}

.nav {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 3px;
  border: 1px solid var(--line);
  border-radius: var(--r-pill);
  background: var(--surface-soft);
}

.nav-link {
  padding: 6px 14px;
  font-size: 13px;
  color: var(--text-2);
  text-decoration: none;
  border-radius: var(--r-pill);
  white-space: nowrap;
  transition: background 0.15s ease, color 0.15s ease;
}

.nav-link:hover {
  color: var(--text);
  background: #fff;
}

.nav-link.is-active {
  color: #fff;
  background: var(--accent);
  box-shadow: 0 2px 8px rgba(30, 111, 255, 0.28);
}

.tools {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-left: auto;
}

.sound-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  font-size: 12.5px;
  color: var(--text-2);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-pill);
  cursor: pointer;
  transition: border-color 0.15s ease, color 0.15s ease;
}

.sound-btn:hover {
  color: var(--text);
  border-color: var(--line-strong);
}

.sound-btn.is-muted {
  color: var(--warn);
  border-color: rgba(245, 158, 11, 0.35);
  background: var(--warn-soft);
}

.status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  font-size: 12.5px;
  border-radius: var(--r-pill);
  border: 1px solid var(--line);
  background: var(--surface);
  color: var(--text-2);
  white-space: nowrap;
}

.status.is-online {
  color: #0a7d5a;
  background: var(--ok-soft);
  border-color: rgba(16, 185, 129, 0.3);
}

.status.is-offline {
  color: #b91c1c;
  background: var(--danger-soft);
  border-color: rgba(239, 68, 68, 0.3);
}

.status.is-pending {
  color: var(--accent-strong);
  background: var(--accent-soft);
  border-color: var(--accent-line);
}

/* ---------- 告警横幅 ---------- */
.alarm {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 12px 24px 0;
  padding: 10px 14px;
  border-radius: var(--r-md);
  border: 1px solid var(--line);
  background: var(--surface);
  box-shadow: 0 6px 20px rgba(15, 28, 46, 0.06);
}

.alarm-critical {
  border-color: rgba(239, 68, 68, 0.4);
  background: linear-gradient(90deg, var(--danger-soft) 0%, #fff 55%);
}

.alarm-warning {
  border-color: rgba(245, 158, 11, 0.4);
  background: linear-gradient(90deg, var(--warn-soft) 0%, #fff 55%);
}

.alarm-icon {
  display: grid;
  place-items: center;
  color: var(--warn);
}

.alarm-critical .alarm-icon {
  color: var(--danger);
}

.alarm-body {
  display: flex;
  align-items: baseline;
  gap: 10px;
  min-width: 0;
}

.alarm-body strong {
  font-size: 13.5px;
  white-space: nowrap;
}

.alarm-msg {
  font-size: 13px;
  color: var(--text-2);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.alarm-meta {
  margin-left: auto;
  font-size: 12px;
  color: var(--text-3);
  white-space: nowrap;
}

.alarm-close {
  border: none;
  background: transparent;
  color: var(--text-3);
  font-size: 13px;
  cursor: pointer;
  padding: 2px 4px;
}

.alarm-close:hover {
  color: var(--text);
}

/* ---------- 主体 ---------- */
.main {
  flex: 1;
  width: 100%;
  max-width: 1360px;
  margin: 0 auto;
  padding: 20px 24px 32px;
}

.page-head {
  display: flex;
  align-items: flex-end;
  gap: 16px;
  margin-bottom: 16px;
}

.page-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
  padding-bottom: 2px;
}

.chip {
  padding: 4px 10px;
  font-size: 12px;
  color: var(--text-2);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-pill);
  white-space: nowrap;
}

.foot {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 24px 22px;
  font-size: 12px;
  color: var(--text-3);
}

@media (max-width: 980px) {
  .topbar {
    flex-wrap: wrap;
  }

  .nav {
    order: 3;
    width: 100%;
    overflow-x: auto;
  }

  .brand-text em {
    display: none;
  }
}
</style>
