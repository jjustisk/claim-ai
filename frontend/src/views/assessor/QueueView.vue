<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  AlertCircle,
  AlertTriangle,
  AppWindow,
  Archive,
  ArrowUpDown,
  Car,
  CheckCircle,
  Clock,
  Cloud,
  Droplets,
  FileText,
  Flame,
  Hammer,
  House,
  Inbox,
  ListFilter,
  LoaderCircle,
  Lock,
  Sofa,
  Wind,
  XCircle,
  Zap,
} from 'lucide-vue-next'
import { api } from '../../api/client'
import {
  damageLabel,
  formatDate,
  formatMoney,
  statusBadgeClass,
  statusMeta,
  urgency,
  urgencyClass,
  urgencyRank,
} from '../../utils/claim'

const router = useRouter()

const claims = ref([])
const counts = ref(null)
const statusFilter = ref('')
const sortBy = ref('urgency')
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await api.claimsList(statusFilter.value || undefined)
    claims.value = res.items || []
    counts.value = res.counts || null
  } catch {
    error.value = 'The claims queue could not be loaded. Please try again.'
  } finally {
    loading.value = false
  }
}

onMounted(load)

const STATUS_ICONS = {
  submitted: Clock,
  under_review: AlertCircle,
  approved: CheckCircle,
  rejected: XCircle,
  closed: Archive,
  draft: FileText,
}

const DAMAGE_ICONS = [
  [/fire|burn/i, Flame],
  [/flood|water/i, Droplets],
  [/hail/i, Cloud],
  [/wind|storm|cyclone/i, Wind],
  [/motor|collision|vehicle|car/i, Car],
  [/theft|burglary/i, Lock],
  [/vandal|malicious/i, Hammer],
  [/electric/i, Zap],
  [/glass/i, AppWindow],
  [/content/i, Sofa],
  [/property|home|house|building/i, House],
  [/accident/i, AlertTriangle],
]

function damageIcon(label) {
  return DAMAGE_ICONS.find(([pattern]) => pattern.test(label))?.[1] || AlertCircle
}

const timeOf = (claim) => new Date(claim.submission_date || 0).getTime() || 0
const amountOf = (claim) => {
  const raw = claim.cost ?? claim.estimated_value
  const value = raw == null || raw === '' ? NaN : Number(raw)
  return Number.isFinite(value) ? value : -Infinity
}
const byNewest = (a, b) => timeOf(b) - timeOf(a)

const SORTS = {
  urgency: (a, b) => urgencyRank(b) - urgencyRank(a) || byNewest(a, b),
  newest: byNewest,
  amount: (a, b) => amountOf(b) - amountOf(a) || byNewest(a, b),
}

const rows = computed(() =>
  [...claims.value].sort(SORTS[sortBy.value] || SORTS.urgency).map((claim) => {
    const type = damageLabel(claim)
    const level = urgency(claim)
    return {
      claim,
      type,
      typeIcon: damageIcon(type),
      status: statusMeta(claim.status).label,
      statusClass: statusBadgeClass(claim.status),
      statusIcon: STATUS_ICONS[claim.status] || AlertCircle,
      urgency: level,
      urgencyClass: urgencyClass(level),
      description: String(claim.incident_description || '').replace(/\s+/g, ' ').trim(),
    }
  }),
)

const stats = computed(() => {
  const c = counts.value
  if (!c) return []
  const n = (key) => Number(c[key]) || 0
  return [
    { label: 'Total claims', value: n('all'), icon: FileText, tone: 'bg-gray-100 text-gray-600' },
    { label: 'Awaiting assessment', value: n('submitted'), icon: Clock, tone: 'bg-yellow-100 text-yellow-700' },
    { label: 'Under review', value: n('under_review'), icon: AlertCircle, tone: 'bg-blue-100 text-blue-700' },
    {
      label: 'Resolved',
      value: n('approved') + n('rejected') + n('closed'),
      icon: CheckCircle,
      tone: 'bg-green-100 text-green-700',
    },
  ]
})

function openClaim(claim) {
  router.push({ name: 'assessor-claim-detail', params: { id: claim.claim_id } })
}
</script>

<template>
  <div>
    <div class="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h2 class="text-2xl font-semibold text-gray-900">Claims Queue</h2>
        <p class="mt-1 text-gray-600">Review and process insurance claims with AI assistance</p>
      </div>
      <div class="flex flex-wrap items-center gap-3">
        <label class="relative block">
          <span class="sr-only">Filter by status</span>
          <ListFilter class="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-gray-400" />
          <select v-model="statusFilter" class="field w-auto min-w-[170px] pl-9" @change="load">
            <option value="">All statuses</option>
            <option value="submitted">Submitted</option>
            <option value="under_review">Under review</option>
            <option value="approved">Approved</option>
            <option value="rejected">Declined</option>
            <option value="closed">Closed</option>
          </select>
        </label>
        <label class="relative block">
          <span class="sr-only">Sort by</span>
          <ArrowUpDown class="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-gray-400" />
          <select v-model="sortBy" class="field w-auto min-w-[200px] pl-9">
            <option value="urgency">Urgency (high → low)</option>
            <option value="newest">Newest first</option>
            <option value="amount">Amount (high → low)</option>
          </select>
        </label>
      </div>
    </div>

    <div v-if="stats.length" class="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
      <div v-for="stat in stats" :key="stat.label" class="card flex items-center gap-3 p-4">
        <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg" :class="stat.tone">
          <component :is="stat.icon" class="h-5 w-5" />
        </span>
        <div class="min-w-0">
          <p class="truncate text-sm text-gray-500">{{ stat.label }}</p>
          <p class="text-2xl font-semibold text-gray-900">{{ stat.value }}</p>
        </div>
      </div>
    </div>

    <div class="overflow-hidden rounded-lg border border-gray-200 bg-white">
      <div v-if="loading" class="flex items-center justify-center gap-2 px-6 py-16 text-sm text-gray-500">
        <LoaderCircle class="h-5 w-5 animate-spin text-blue-600" />
        Loading claims…
      </div>

      <div v-else-if="error" class="flex flex-col items-center gap-3 px-6 py-16 text-center">
        <span class="flex h-10 w-10 items-center justify-center rounded-full bg-red-100 text-red-600">
          <AlertCircle class="h-5 w-5" />
        </span>
        <p class="text-sm text-gray-700">{{ error }}</p>
        <button type="button" class="btn-primary" @click="load">Try again</button>
      </div>

      <div v-else-if="!rows.length" class="flex flex-col items-center gap-2 px-6 py-16 text-center">
        <Inbox class="h-10 w-10 text-gray-300" />
        <p class="font-medium text-gray-900">No claims match this filter</p>
        <p class="text-sm text-gray-500">
          {{ statusFilter ? 'Try a different status.' : 'New claims will appear here once they are submitted.' }}
        </p>
      </div>

      <div v-else class="overflow-x-auto">
        <table class="w-full">
          <thead class="border-b border-gray-200 bg-gray-50">
            <tr>
              <th class="px-6 py-3 text-left text-xs font-medium tracking-wider text-gray-500 uppercase">Claim</th>
              <th class="px-6 py-3 text-left text-xs font-medium tracking-wider text-gray-500 uppercase">Customer</th>
              <th class="px-6 py-3 text-left text-xs font-medium tracking-wider text-gray-500 uppercase">Type</th>
              <th class="px-6 py-3 text-left text-xs font-medium tracking-wider text-gray-500 uppercase">Status</th>
              <th class="px-6 py-3 text-left text-xs font-medium tracking-wider text-gray-500 uppercase">Urgency</th>
              <th class="px-6 py-3 text-left text-xs font-medium tracking-wider text-gray-500 uppercase">Amount</th>
              <th class="px-6 py-3 text-left text-xs font-medium tracking-wider text-gray-500 uppercase">Date</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-200">
            <tr
              v-for="row in rows"
              :key="row.claim.claim_id"
              class="cursor-pointer transition-colors hover:bg-gray-50"
              @click="openClaim(row.claim)"
            >
              <td class="px-6 py-4">
                <RouterLink
                  :to="{ name: 'assessor-claim-detail', params: { id: row.claim.claim_id } }"
                  class="font-medium whitespace-nowrap text-gray-900 hover:text-blue-700"
                  @click.stop
                >
                  {{ row.claim.claim_reference }}
                </RouterLink>
                <p class="line-clamp-1 max-w-xs text-sm text-gray-500" :title="row.description || undefined">
                  {{ row.description || 'No incident description provided' }}
                </p>
              </td>
              <td class="px-6 py-4">
                <p class="text-sm whitespace-nowrap text-gray-900">{{ row.claim.customer_name || '—' }}</p>
                <p class="text-sm whitespace-nowrap text-gray-500">{{ row.claim.policy_number || '—' }}</p>
              </td>
              <td class="px-6 py-4">
                <div class="flex items-center gap-2 whitespace-nowrap text-gray-700">
                  <component :is="row.typeIcon" class="h-5 w-5 shrink-0" />
                  <span class="text-sm">{{ row.type }}</span>
                </div>
              </td>
              <td class="px-6 py-4">
                <span
                  class="inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-medium whitespace-nowrap"
                  :class="row.statusClass"
                >
                  <component :is="row.statusIcon" class="h-4 w-4" />
                  {{ row.status }}
                </span>
              </td>
              <td class="px-6 py-4">
                <span class="text-sm font-semibold" :class="row.urgencyClass">{{ row.urgency }}</span>
              </td>
              <td class="px-6 py-4">
                <span class="font-semibold whitespace-nowrap text-gray-900">
                  {{ formatMoney(row.claim.cost ?? row.claim.estimated_value) }}
                </span>
              </td>
              <td class="px-6 py-4 text-sm whitespace-nowrap text-gray-500">{{ formatDate(row.claim.submission_date) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
