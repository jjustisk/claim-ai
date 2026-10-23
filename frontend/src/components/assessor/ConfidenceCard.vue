<script setup>
import { computed } from 'vue'
import ScoreBar from './ScoreBar.vue'
import { confidenceBand, unitToPercent } from '../../utils/aiSteps'

const props = defineProps({
  assessment: { type: Object, default: null },
  recommendation: { type: Object, default: null },
  fallbackScore: { type: [Number, String], default: null },
  inProgress: { type: Boolean, default: false },
})

const BANDS = {
  high: { text: 'text-emerald-600', bar: 'bg-emerald-500', caption: 'High confidence — strong evidence alignment' },
  moderate: { text: 'text-amber-600', bar: 'bg-amber-500', caption: 'Moderate confidence — review recommended' },
  low: { text: 'text-red-600', bar: 'bg-red-500', caption: 'Lower confidence — careful review required' },
}

const score = computed(() => {
  const own = props.assessment?.confidence?.score
  if (own != null) return unitToPercent(own)
  return props.assessment?.status === 'referred' ? null : unitToPercent(props.fallbackScore)
})
const band = computed(() => BANDS[confidenceBand(score.value, props.assessment?.confidence?.band)] || null)
const caption = computed(() => {
  if (score.value != null && band.value) return band.value.caption
  if (props.assessment?.status === 'referred') return 'Referred for manual review — no automated confidence'
  if (props.inProgress || props.assessment?.status === 'pending') return 'AI assessment in progress — check back shortly'
  return 'No automated confidence is available for this claim'
})

const signals = computed(() => {
  const values = props.assessment?.confidence?.signals || {}
  return [
    { label: 'Consistency', score: unitToPercent(values.consistency), invert: false },
    { label: 'Policy match', score: unitToPercent(values.policy_match), invert: false },
    { label: 'Fraud risk (lower is better)', score: unitToPercent(values.fraud_risk), invert: true },
  ].filter((signal) => signal.score != null)
})
</script>

<template>
  <div class="rounded-xl border border-gray-200 bg-white p-5">
    <p class="mb-4 text-xs font-semibold tracking-wide text-gray-400 uppercase">AI Assessment</p>
    <div class="mb-4">
      <div class="mb-1.5 flex items-end justify-between">
        <span class="text-sm text-gray-600">Confidence Score</span>
        <span class="text-2xl font-bold" :class="score != null && band ? band.text : 'text-gray-300'">
          {{ score != null ? `${score}%` : '—' }}
        </span>
      </div>
      <div class="h-2 w-full rounded-full bg-gray-100">
        <div
          v-if="score != null && band"
          class="h-2 rounded-full transition-all"
          :class="band.bar"
          :style="{ width: `${Math.max(0, Math.min(100, score))}%` }"
        />
      </div>
      <p class="mt-1 text-xs text-gray-400">{{ caption }}</p>
    </div>

    <div
      class="flex items-center justify-between rounded-lg border px-3 py-2.5"
      :class="recommendation ? recommendation.box : 'border-gray-200 bg-gray-50'"
    >
      <span class="text-sm text-gray-600">Recommendation</span>
      <span class="text-sm font-bold" :class="recommendation ? recommendation.text : 'text-gray-400'">
        {{ recommendation ? recommendation.label : inProgress ? 'PENDING' : '—' }}
      </span>
    </div>

    <div v-if="signals.length" class="mt-5 space-y-3 border-t border-gray-100 pt-4">
      <p class="text-xs font-semibold tracking-wide text-gray-400 uppercase">Signal breakdown</p>
      <ScoreBar v-for="signal in signals" :key="signal.label" :score="signal.score" :label="signal.label" :invert="signal.invert" />
    </div>
  </div>
</template>
