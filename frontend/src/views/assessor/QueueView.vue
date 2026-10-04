<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../../api/client'
import { damageLabel, formatDate, formatMoney, statusMeta, urgency } from '../../utils/claim'

const router = useRouter()

const claims = ref([])
const statusFilter = ref('')
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await api.claimsList(statusFilter.value || undefined)
    claims.value = res.items || []
  } catch {
    error.value = 'The claims queue could not be loaded. Please try again.'
  } finally {
    loading.value = false
  }
}

onMounted(load)

const rows = computed(() =>
  [...claims.value].sort((a, b) => new Date(b.submission_date || 0) - new Date(a.submission_date || 0)),
)

function snippet(text) {
  const value = String(text || '').replace(/\s+/g, ' ').trim()
  if (!value) return 'No incident description provided'
  return value.length > 52 ? `${value.slice(0, 52)}…` : value
}
</script>

<template>
  <div>
    <div class="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h2 class="text-lg font-bold text-slate-900">Claims queue</h2>
        <p class="text-sm text-slate-500">Review and process claims with automated assessment support</p>
      </div>
      <select v-model="statusFilter" class="field w-auto min-w-[160px]" @change="load">
        <option value="">All statuses</option>
        <option value="submitted">Submitted</option>
        <option value="under_review">Under review</option>
        <option value="approved">Approved</option>
        <option value="rejected">Declined</option>
        <option value="closed">Closed</option>
      </select>
    </div>

    <p v-if="loading" class="text-sm text-slate-500">Loading claims…</p>
    <p v-else-if="error" class="text-sm text-red-600">{{ error }}</p>
    <p v-else-if="!rows.length" class="text-sm text-slate-500">There are no claims matching this filter.</p>

    <div v-else class="overflow-x-auto">
      <table class="w-full min-w-[720px] text-left text-sm">
        <thead>
          <tr class="border-b border-slate-200 text-[11px] font-semibold tracking-wide text-slate-400">
            <th class="px-2 py-2 font-semibold">CLAIM</th>
            <th class="px-2 py-2 font-semibold">CUSTOMER</th>
            <th class="px-2 py-2 font-semibold">TYPE</th>
            <th class="px-2 py-2 font-semibold">STATUS</th>
            <th class="px-2 py-2 font-semibold">URGENCY</th>
            <th class="px-2 py-2 font-semibold">AMOUNT</th>
            <th class="px-2 py-2 font-semibold">DATE</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="claim in rows"
            :key="claim.claim_id"
            class="cursor-pointer border-b border-slate-100 last:border-0 hover:bg-slate-50"
            @click="router.push({ name: 'assessor-claim-detail', params: { id: claim.claim_id } })"
          >
            <td class="px-2 py-3 align-top">
              <RouterLink
                :to="{ name: 'assessor-claim-detail', params: { id: claim.claim_id } }"
                class="font-semibold text-slate-900 hover:text-blue-700"
              >
                {{ claim.claim_reference }}
              </RouterLink>
              <p class="max-w-[220px] text-xs text-slate-400">{{ snippet(claim.incident_description) }}</p>
            </td>
            <td class="px-2 py-3 align-top">
              <p class="font-medium text-slate-800">{{ claim.customer_name }}</p>
              <p class="text-xs text-slate-400">{{ claim.policy_number }}</p>
            </td>
            <td class="px-2 py-3 align-top text-slate-700">{{ damageLabel(claim) }}</td>
            <td class="px-2 py-3 align-top">
              <span
                class="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset"
                :class="{
                  'bg-amber-50 text-amber-600 ring-amber-200': statusMeta(claim.status).tone === 'amber',
                  'bg-blue-50 text-blue-600 ring-blue-200': statusMeta(claim.status).tone === 'blue',
                  'bg-emerald-50 text-emerald-600 ring-emerald-200': statusMeta(claim.status).tone === 'green',
                  'bg-red-50 text-red-600 ring-red-200': statusMeta(claim.status).tone === 'red',
                  'bg-slate-100 text-slate-600 ring-slate-200': statusMeta(claim.status).tone === 'slate',
                }"
              >
                {{ statusMeta(claim.status).label }}
              </span>
            </td>
            <td
              class="px-2 py-3 align-top font-semibold"
              :class="{
                'text-red-500': urgency(claim) === 'High',
                'text-amber-500': urgency(claim) === 'Medium',
                'text-emerald-600': urgency(claim) === 'Low',
              }"
            >
              {{ urgency(claim) }}
            </td>
            <td class="px-2 py-3 align-top font-medium text-slate-800">{{ formatMoney(claim.cost ?? claim.estimated_value) }}</td>
            <td class="px-2 py-3 align-top text-slate-500">{{ formatDate(claim.submission_date) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
