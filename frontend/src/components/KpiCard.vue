<template>
  <div class="card kpi" :class="toneClass">
    <span class="label">{{ label }}</span>
    <div class="kpi-value">
      <span>{{ display }}</span>
      <small v-if="unit">{{ unit }}</small>
    </div>
    <span v-if="hint" class="hint">{{ hint }}</span>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  label: { type: String, required: true },
  value: { type: [Number, String], default: 0 },
  unit: { type: String, default: '' },
  tone: { type: String, default: 'accent' }, // accent | fire | smoke | danger | warn | ok
  hint: { type: String, default: '' },
})

const display = computed(() => {
  if (typeof props.value === 'number') {
    if (!Number.isFinite(props.value)) return '—'
    return Number.isInteger(props.value) ? String(props.value) : props.value.toFixed(1)
  }
  return props.value ?? '—'
})

const toneClass = computed(() => (props.tone === 'accent' ? '' : `kpi-${props.tone}`))
</script>
