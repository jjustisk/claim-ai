<script setup>
defineProps({
  label: { type: String, required: true },
  value: { type: [String, Number], default: null },
})
</script>

<template>
  <div>
    <p class="mb-1 text-xs font-semibold tracking-wide text-gray-400 uppercase">{{ label }}</p>
    <slot>
      <p class="text-sm leading-relaxed whitespace-pre-line text-gray-700">{{ value }}</p>
    </slot>
  </div>
</template>
