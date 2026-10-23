<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { AlertCircle, ArrowLeft, CheckCircle, Clock, FileText, XCircle } from 'lucide-vue-next'
import { api } from '../../api/client'
import { damageLabel, errorText, formatMoney, statusMeta } from '../../utils/claim'

const POLL_MS = 15000
const RESOLVED_STATUSES = ['approved', 'rejected', 'closed']
const STATUS_LABELS = {
  draft: 'Draft — not yet submitted',
  submitted: 'Waiting for automated assessment',
  under_review: 'Being reviewed by an assessor',
  approved: 'Claim approved',
  rejected: 'Claim declined',
  closed: 'Claim closed',
}
const OUTCOME_STYLES = {
  approved: { icon: CheckCircle, card: 'border-green-200 bg-green-50', icon_class: 'text-green-600', title: 'text-green-900', body: 'text-green-800' },
  rejected: { icon: XCircle, card: 'border-red-200 bg-red-50', icon_class: 'text-red-600', title: 'text-red-900', body: 'text-red-800' },
  closed: { icon: FileText, card: 'border-gray-200 bg-white', icon_class: 'text-gray-500', title: 'text-gray-900', body: 'text-gray-700' },
}

const props = defineProps({ id: { type: [String, Number], required: true } })

const claim = ref(null)
const loading = ref(true)
const error = ref('')
let timer = null
let requestSeq = 0
let backgroundInFlight = false

async function load({ background = false } = {}) {
  if (background && backgroundInFlight) return
  const seq = ++requestSeq
  backgroundInFlight = background
  try {
    const data = await api.myClaimDetail(props.id)
    if (seq !== requestSeq) return
    claim.value = data
    error.value = ''
  } catch (err) {
    if (seq === requestSeq && !background) {
      error.value = errorText(err, 'This claim could not be loaded. Please try again.')
    }
  } finally {
    if (seq === requestSeq) {
      backgroundInFlight = false
      loading.value = false
      syncPolling()
    }
  }
}

function stopPolling() {
  if (timer) clearInterval(timer)
  timer = null
}

function syncPolling() {
  if (claim.value && !isResolved.value && !isDraft.value) {
    timer ??= setInterval(() => {
      if (document.visibilityState === 'visible') load({ background: true })
    }, POLL_MS)
  } else {
    stopPolling()
  }
}

function onVisibilityChange() {
  if (document.visibilityState === 'visible' && timer) load({ background: true })
}

onMounted(() => {
  document.addEventListener('visibilitychange', onVisibilityChange)
  load()
})

onBeforeUnmount(() => {
  requestSeq++
  stopPolling()
  document.removeEventListener('visibilitychange', onVisibilityChange)
})

watch(
  () => props.id,
  () => {
    stopPolling()
    claim.value = null
    error.value = ''
    loading.value = true
    load()
  },
)

function fallbackProgress(c) {
  const status = c.status
  const resolved = RESOLVED_STATUSES.includes(status)
  const reviewed = resolved || status === 'under_review'
  const stages = [
    ['submitted', 'Claim Submitted', status !== 'draft', c.submission_date],
    ['ai_analysis', 'AI Analysis Complete', reviewed, null],
    ['under_review', 'Under Assessor Review', reviewed, null],
    ['resolved', 'Claim Resolved', resolved, c.outcome_date],
  ]
  const lastDone = stages.reduce((last, stage, index) => (stage[2] ? index : last), -1)
  return {
    current_status_label: STATUS_LABELS[status] || statusMeta(status).label,
    resolved,
    milestones: stages.map(([key, label, , timestamp], index) => {
      const state = index <= lastDone ? 'done' : index === lastDone + 1 ? 'active' : 'pending'
      return { key, label, state, timestamp: state === 'done' ? timestamp || null : null }
    }),
  }
}

const progress = computed(() => {
  const c = claim.value
  if (!c) return null
  const p = c.progress
  return p && Array.isArray(p.milestones) && p.milestones.length ? p : fallbackProgress(c)
})

const milestones = computed(() =>
  (progress.value?.milestones || []).map((m) => ({
    ...m,
    state: m.state === 'done' || m.state === 'active' ? m.state : 'pending',
  })),
)

const isResolved = computed(() => !!progress.value?.resolved)
const isDraft = computed(() => claim.value?.status === 'draft')

const outcome = computed(() => {
  if (!isResolved.value) return null
  const status = claim.value.outcome?.status || claim.value.status
  return {
    label: claim.value.outcome?.label || STATUS_LABELS[status] || statusMeta(status).label,
    explanation: claim.value.outcome?.explanation || '',
    style: OUTCOME_STYLES[status] || OUTCOME_STYLES.closed,
  }
})

const subtitle = computed(() => {
  const c = claim.value
  return c?.coverage_type || `${damageLabel(c)} claim`
})

const details = computed(() => {
  const c = claim.value
  const submitted = milestones.value.find((m) => m.key === 'submitted')?.timestamp || c.submission_date
  return [
    { label: 'Damage Type', value: damageLabel(c) },
    { label: 'Estimated Damage', value: formatMoney(c.estimated_value) },
    { label: 'Submitted', value: formatDateTime(submitted) },
    { label: 'Policy Number', value: c.policy_number || '—' },
  ]
})

function formatDateTime(value) {
  if (!value) return '—'
  const text = String(value)
  // The API stores UTC; timestamps without an offset are UTC too.
  const iso = text.includes('T') && !/(Z|[+-]\d{2}:?\d{2})$/i.test(text) ? `${text}Z` : text
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return text
  return date.toLocaleString('en-AU', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

function nodeClass(state) {
  if (state === 'done') return 'bg-green-500'
  if (state === 'active') return 'bg-blue-500'
  return 'bg-gray-200'
}
</script>

<template>
  <div>
    <RouterLink
      :to="{ name: 'my-claims' }"
      class="mb-6 inline-flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900"
    >
      <ArrowLeft class="h-4 w-4" />
      Back to my claims
    </RouterLink>

    <p v-if="loading" class="text-sm text-gray-500">Loading claim details…</p>

    <div v-else-if="error" class="py-12 text-center">
      <AlertCircle class="mx-auto mb-4 h-12 w-12 text-gray-400" />
      <p class="text-gray-600">{{ error }}</p>
    </div>

    <template v-else-if="claim && progress">
      <div class="mb-6 rounded-lg border border-gray-200 bg-white p-6">
        <div class="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div class="min-w-0">
            <h1 class="break-words text-2xl font-semibold text-gray-900">{{ claim.claim_reference }}</h1>
            <p class="mt-1 text-gray-600">{{ subtitle }}</p>
          </div>
          <div class="sm:text-right">
            <p class="text-sm text-gray-600">Current Status</p>
            <p class="font-medium text-gray-900">{{ progress.current_status_label }}</p>
          </div>
        </div>

        <dl class="mb-6 grid grid-cols-2 gap-4 border-b border-gray-200 pb-6">
          <div v-for="item in details" :key="item.label" class="min-w-0">
            <dt class="text-sm text-gray-600">{{ item.label }}</dt>
            <dd class="break-words font-medium text-gray-900">{{ item.value }}</dd>
          </div>
        </dl>

        <h3 class="mb-4 font-semibold text-gray-900">Processing Timeline</h3>
        <ol class="space-y-6">
          <li
            v-for="(milestone, index) in milestones"
            :key="milestone.key"
            class="relative flex gap-4"
            :aria-current="milestone.state === 'active' ? 'step' : undefined"
          >
            <div
              v-if="index !== milestones.length - 1"
              class="absolute bottom-0 left-4 top-10 w-0.5"
              :class="milestone.state === 'done' ? 'bg-green-500' : 'bg-gray-200'"
              aria-hidden="true"
            />
            <div
              class="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full"
              :class="nodeClass(milestone.state)"
            >
              <CheckCircle v-if="milestone.state === 'done'" class="h-5 w-5 text-white" />
              <Clock v-else-if="milestone.state === 'active'" class="h-5 w-5 text-white" />
              <span v-else class="h-3 w-3 rounded-full bg-white" />
            </div>
            <div class="flex-1 pb-2">
              <p class="font-medium" :class="milestone.state === 'pending' ? 'text-gray-500' : 'text-gray-900'">
                {{ milestone.label }}
              </p>
              <p v-if="milestone.timestamp" class="mt-1 text-sm text-gray-500">
                {{ formatDateTime(milestone.timestamp) }}
              </p>
              <p v-if="milestone.state === 'active'" class="mt-1 text-sm text-blue-600">In progress…</p>
            </div>
          </li>
        </ol>
      </div>

      <div v-if="outcome" class="rounded-lg border p-6" :class="outcome.style.card">
        <div class="flex items-start gap-3">
          <component :is="outcome.style.icon" class="mt-0.5 h-6 w-6 flex-shrink-0" :class="outcome.style.icon_class" />
          <div class="min-w-0">
            <p class="font-semibold" :class="outcome.style.title">{{ outcome.label }}</p>
            <p class="mt-2 whitespace-pre-line text-sm leading-relaxed" :class="outcome.style.body">
              {{ outcome.explanation || 'You will receive an email with the details of this decision.' }}
            </p>
          </div>
        </div>
      </div>

      <div v-else-if="isDraft" class="rounded-lg border border-gray-200 bg-white p-4 text-sm text-gray-600">
        This claim has not been submitted yet.
        <RouterLink
          :to="{ name: 'my-claims-draft', params: { draftId: claim.claim_id } }"
          class="font-medium text-blue-600 hover:text-blue-700"
        >
          Continue your draft
        </RouterLink>
      </div>

      <div v-else class="flex items-start gap-3 rounded-lg border border-blue-200 bg-blue-50 p-4">
        <Clock class="mt-0.5 h-5 w-5 flex-shrink-0 text-blue-600" />
        <div>
          <p class="text-sm font-medium text-blue-900">Estimated Resolution</p>
          <p class="text-sm text-blue-700">
            Your claim should be resolved within 24-48 hours. You'll receive an email notification once a decision
            has been made.
          </p>
        </div>
      </div>
    </template>
  </div>
</template>
