<script setup>
import { computed } from 'vue'
import { AlertTriangle } from 'lucide-vue-next'

const props = defineProps({
  recommendation: { type: Object, default: null },
  status: { type: String, default: null },
  inProgress: { type: Boolean, default: false },
})

const emptyText = computed(() => {
  if (props.inProgress || props.status === 'pending') return 'The checks are still running. Check back shortly.'
  return 'No recommendation is available for this claim yet.'
})
</script>

<template>
  <div class="rounded-xl border border-gray-200 bg-white p-5">
    <p class="mb-3 text-xs font-semibold tracking-wide text-gray-400 uppercase">Recommendation</p>

    <template v-if="recommendation">
      <div class="rounded-lg border px-4 py-3" :class="recommendation.box">
        <p class="text-lg font-bold" :class="recommendation.text">{{ recommendation.label }}</p>
        <p class="mt-1 text-sm leading-snug text-gray-700">{{ recommendation.reason }}</p>
      </div>

      <p
        v-if="recommendation.possibleFraud"
        class="mt-3 flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm font-medium text-red-700"
      >
        <AlertTriangle class="h-4 w-4 shrink-0" />
        Possible fraud: please investigate
      </p>

      <p v-if="recommendation.sureness" class="mt-3 text-sm text-gray-600">
        How sure we are: <span class="font-semibold text-gray-900">{{ recommendation.sureness }}</span>
      </p>
    </template>
    <p v-else class="text-sm text-gray-500">{{ emptyText }}</p>

    <p class="mt-4 text-xs text-gray-400">Prepared automatically. You make the final decision.</p>
  </div>
</template>
