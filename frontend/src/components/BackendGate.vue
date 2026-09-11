<template>
  <section v-if="!state.probed" class="card">
    <div class="card-body row">
      <span class="dot dot-pulse" style="color: var(--accent)"></span>
      <span class="sub">正在连接后端服务…</span>
    </div>
  </section>

  <section v-else-if="!state.connected" class="card">
    <div class="card-body offline">
      <div class="row">
        <span class="dot dot-pulse" style="color: var(--danger)"></span>
        <strong>后端未连接</strong>
      </div>
      <p class="sub">{{ state.error || '无法访问 /api/health' }}</p>
      <p class="hint">请先在项目根目录启动后端服务（默认监听 127.0.0.1:8000）：</p>
      <pre class="cmd mono">{{ START_COMMAND }}</pre>
      <p class="hint">
        首次使用需先下载模型权重：<code class="mono">python scripts/download_weights.py</code>
      </p>
      <div class="row">
        <button class="btn btn-primary btn-sm" :disabled="state.loading" @click="refresh">
          重新连接
        </button>
        <span v-if="state.loading" class="hint">连接中…</span>
      </div>
    </div>
  </section>

  <slot v-else />
</template>

<script setup>
import { useBackend } from '../composables/useBackend'
import { START_COMMAND } from '../utils/format'

const { state, refresh } = useBackend()
</script>

<style scoped>
.offline {
  display: flex;
  flex-direction: column;
  gap: 10px;
  align-items: flex-start;
}

.cmd {
  margin: 0;
  padding: 10px 12px;
  width: 100%;
  overflow-x: auto;
  font-size: 12.5px;
  color: var(--text);
  background: var(--surface-sunken);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
}

code {
  padding: 1px 5px;
  font-size: 12px;
  background: var(--surface-sunken);
  border-radius: 4px;
}
</style>
