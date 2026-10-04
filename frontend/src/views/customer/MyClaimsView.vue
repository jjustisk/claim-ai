<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuth } from '../../stores/auth'
import { api } from '../../api/client'
import { damageLabel, formatDate, statusMeta } from '../../utils/claim'

const { state } = useAuth()
const route = useRoute()
const router = useRouter()

const claims = ref([])
const loading = ref(true)
const error = ref('')
const reference = ref('')
const trackError = ref('')

const drafts = computed(() => claims.value.filter((c) => c.status === 'draft'))
const submitted = computed(() => claims.value.filter((c) => c.status !== 'draft'))
const firstName = computed(() => (state.user?.name || 'there').split(/\s+/)[0])

onMounted(async () => {
  try {
    claims.value = await api.myClaims()
  } catch {
    error.value = 'Your claims could not be loaded. Please refresh and try again.'
  } finally {
    loading.value = false
  }
})

const notice = computed(() => {
  if (route.query.submitted) {
    return `Claim ${route.query.submitted} has been submitted successfully. Assessment is in progress. You may leave this page; claim status will update as review continues.`
  }
  if (route.query.deleted) return 'The draft claim has been deleted.'
  return ''
})

function trackClaim() {
  trackError.value = ''
  const query = reference.value.trim().toLowerCase()
  const match = submitted.value.find((c) => c.claim_reference?.toLowerCase() === query)
  if (!match) {
    trackError.value = 'No claim with that reference was found for this account.'
    return
  }
  router.push({ name: 'my-claim-status', params: { id: match.claim_id } })
}
</script>

<template>
  <div class="space-y-6">
    <div v-if="notice" class="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">{{ notice }}</div>

    <section>
      <h1 class="text-xl font-bold text-slate-900">Welcome, {{ firstName }}</h1>
      <p class="mt-1 text-sm text-slate-500">Lodge a new claim, continue a draft, or track the status of a submitted claim.</p>
      <RouterLink :to="{ name: 'my-claims-new' }" class="btn-primary mt-4 inline-flex">Lodge a claim</RouterLink>
    </section>

    <section class="rounded-xl border border-blue-100 bg-blue-50/40 p-4">
      <h2 class="text-sm font-bold text-slate-900">Track an existing claim</h2>
      <div class="mt-3 flex flex-col gap-2 sm:flex-row">
        <input v-model="reference" class="field" placeholder="Claim reference (for example, CLM-2026-001234)" @keyup.enter="trackClaim" />
        <button type="button" class="btn-primary shrink-0 px-5" @click="trackClaim">Track claim</button>
      </div>
      <p v-if="trackError" class="mt-2 text-sm text-red-600">{{ trackError }}</p>
      <p v-else-if="submitted.length" class="mt-2 text-xs text-slate-400">
        Recent references: {{ submitted.slice(0, 5).map((c) => c.claim_reference).join(', ') }}
      </p>
    </section>

    <p v-if="loading" class="text-sm text-slate-500">Loading claims…</p>
    <p v-else-if="error" class="text-sm text-red-600">{{ error }}</p>

    <section v-else>
      <h2 class="text-base font-bold">Draft claims</h2>
      <p class="mb-3 text-sm text-slate-500">Resume a saved draft or remove one that is no longer required.</p>
      <p v-if="!drafts.length" class="text-sm text-slate-500">There are no draft claims at this time.</p>
      <div v-else class="overflow-x-auto">
        <table class="w-full min-w-[640px] text-left text-sm">
          <thead>
            <tr class="border-b text-xs font-semibold text-slate-400">
              <th class="py-2">Reference</th><th>Policy</th><th>Type</th><th>Incident</th><th>Status</th><th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in drafts" :key="row.claim_id" class="border-b border-slate-100">
              <td class="py-2 font-medium">{{ row.claim_reference }}</td>
              <td>{{ row.policy_number }}</td>
              <td>{{ damageLabel(row) }}</td>
              <td>{{ formatDate(row.incident_date) }}</td>
              <td>{{ statusMeta(row.status).label }}</td>
              <td class="py-2">
                <RouterLink class="text-blue-600 hover:underline" :to="{ name: 'my-claims-draft', params: { draftId: row.claim_id } }">Resume</RouterLink>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section>
      <h2 class="text-base font-bold">Submitted claims</h2>
      <p v-if="!submitted.length" class="text-sm text-slate-500">No submitted claims are available for this account.</p>
      <div v-else class="overflow-x-auto">
        <table class="w-full min-w-[640px] text-left text-sm">
          <thead>
            <tr class="border-b text-xs font-semibold text-slate-400">
              <th class="py-2">Reference</th><th>Policy</th><th>Type</th><th>Incident</th><th>Status</th><th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in submitted" :key="row.claim_id" class="border-b border-slate-100">
              <td class="py-2">
                <RouterLink class="font-medium text-blue-600 hover:underline" :to="{ name: 'my-claim-status', params: { id: row.claim_id } }">
                  {{ row.claim_reference }}
                </RouterLink>
              </td>
              <td>{{ row.policy_number }}</td>
              <td>{{ damageLabel(row) }}</td>
              <td>{{ formatDate(row.incident_date) }}</td>
              <td>{{ statusMeta(row.status).label }}</td>
              <td class="py-2 text-slate-400">—</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>
