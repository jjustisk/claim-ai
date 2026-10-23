<script setup>
import { computed } from 'vue'

const props = defineProps({
  score: { type: Number, required: true },
  label: { type: String, required: true },
  // Lower is better (e.g. fraud risk).
  invert: { type: Boolean, default: false },
})

const value = computed(() => Math.max(0, Math.min(100, Math.round(props.score))))
const tone = computed(() => {
  const goodness = props.invert ? 100 - value.value : value.value
  if (goodness >= 85) return { bar: 'bg-emerald-500', text: 'text-emerald-700' }
  if (goodness >= 70) return { bar: 'bg-amber-500', text: 'text-amber-700' }
  return { bar: 'bg-red-500', text: 'text-red-700' }
})
</script>

<template>
  <div>
    <div class="mb-1 flex items-center justify-between gap-3">
      <span class="text-xs text-gray-400">{{ label }}</span>
      <span class="text-xs font-bold" :class="tone.text">{{ value }}%</span>
    </div>
    <div class="h-1.5 w-full rounded-full bg-gray-200">
      <div class="h-1.5 rounded-full" :class="tone.bar" :style="{ width: `${value}%` }" />
    </div>
  </div>
</template>
