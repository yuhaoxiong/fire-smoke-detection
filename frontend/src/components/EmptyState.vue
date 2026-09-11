<template>
  <div class="empty">
    <svg
      width="32"
      height="32"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="1.4"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
    >
      <path d="M3 6.5A2 2 0 0 1 5 4.5h3.2l1.3 2h9.5a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
    </svg>
    <div class="empty-title">{{ title }}</div>
    <p v-if="desc" class="empty-desc">{{ desc }}</p>
    <slot />
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, default: '暂无数据' },
  desc: { type: String, default: '' },
})
</script>
