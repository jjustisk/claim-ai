<script setup>
import { ref, onMounted, computed } from 'vue'
import { api } from '../../api/client'

const claims = ref([])
const counts = ref({})
const statusFilter = ref('')
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await api.claimsList(statusFilter.value || undefined)
    claims.value = res.items
    counts.value = res.counts
  } catch (err) {
    error.value = 'Could not load the claim queue.'
  } finally {
    loading.value = false
  }
}

onMounted(load)

// NOTE: /claims (list_claims) currently returns priority_level and
// fraud_risk_score, but not the AI confidence band — that only comes
// back on the single-claim detail endpoint via ai_decisions[0].
// Sorting by priority_level + fraud_risk_score as the best available
// proxy until the list endpoint is extended to include it.
const sortedClaims = computed(() =>
  [...claims.value].sort((a, b) => {
    const priorityDiff = (b.priority_level ?? 0) - (a.priority_level ?? 0)
    if (priorityDiff !== 0) return priorityDiff
    const fraudDiff = (b.fraud_risk_score ?? 0) - (a.fraud_risk_score ?? 0)
    if (fraudDiff !== 0) return fraudDiff
    return new Date(b.submission_date || 0) - new Date(a.submission_date || 0)
  }),
)

function fraudStyle(score) {
  if (score >= 0.7) return 'bg-red-100 text-red-800'
  if (score >= 0.3) return 'bg-amber-100 text-amber-800'
  return 'bg-slate-100 text-slate-600'
}
</script>

<template>
  <div>
    <div class="mb-6 flex items-center justify-between">
      <h1 class="text-lg font-semibold">Claim queue</h1>
      <select v-model="statusFilter" class="rounded border border-slate-300 px-2 py-1 text-sm" @change="load">
        <option value="">All statuses</option>
        <option value="under_review">Under review</option>
        <option value="approved">Approved</option>
        <option value="rejected">Rejected</option>
        <option value="closed">Closed</option>
      </select>
    </div>

    <div class="mb-6 flex gap-4 text-sm text-slate-600">
      <span v-for="(value, key) in counts" :key="key">{{ key }}: <strong class="text-slate-900">{{ value }}</strong></span>
    </div>

    <p v-if="loading" class="text-slate-500">Loading…</p>
    <p v-else-if="error" class="text-red-600">{{ error }}</p>
    <p v-else-if="!sortedClaims.length" class="text-slate-500">No claims match this filter.</p>

    <ul v-else class="divide-y divide-slate-200 rounded border border-slate-200 bg-white">
      <li v-for="claim in sortedClaims" :key="claim.claim_id">
        <RouterLink
          :to="{ name: 'assessor-claim-detail', params: { id: claim.claim_id } }"
          class="flex items-center justify-between px-4 py-3 hover:bg-slate-50"
        >
          <div>
            <p class="font-medium">{{ claim.claim_reference }}</p>
            <p class="text-sm text-slate-500">
              {{ claim.customer_name }} · {{ claim.coverage_type }} · {{ claim.status }}
            </p>
          </div>
          <span
            class="rounded-full px-2 py-1 text-xs font-medium"
            :class="fraudStyle(claim.fraud_risk_score ?? 0)"
          >
            fraud risk {{ ((claim.fraud_risk_score ?? 0) * 100).toFixed(0) }}%
          </span>
        </RouterLink>
      </li>
    </ul>
  </div>
</template>
