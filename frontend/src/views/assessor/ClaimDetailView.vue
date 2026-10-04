<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { marked } from 'marked'
import { api, ApiError } from '../../api/client'
import ClaimRecordDetails from '../../components/assessor/ClaimRecordDetails.vue'
import { aiBadge, damageLabel, errorText, formatDate, formatMoney, urgency } from '../../utils/claim'

marked.setOptions({ gfm: true, breaks: true })

const props = defineProps({ id: { type: [String, Number], required: true } })
const router = useRouter()

const claim = ref(null)
const decisionBrief = ref(null)
const briefLoading = ref(false)
const loading = ref(true)
const error = ref('')
const files = ref([])
const showAudit = ref(false)
const editingExplanation = ref(false)
const editingPayout = ref(false)
const explanation = ref('')
const payout = ref('')
const explanationDirty = ref(false)
const payoutDirty = ref(false)
const pending = ref(null)
const notes = ref('')
const submitting = ref(false)
const reviewError = ref('')

const latestDecision = computed(() => claim.value?.ai_decisions?.[0] ?? null)
const badge = computed(() => aiBadge(latestDecision.value?.decision))
const images = computed(() => files.value.filter((file) => file.isImage))
const otherFiles = computed(() => files.value.filter((file) => !file.isImage))
const briefHtml = computed(() => {
  const memo = decisionBrief.value?.memo
  if (!memo) return ''
  return marked.parse(memo)
})

function syncDrafts() {
  explanation.value = latestDecision.value?.customer_explanation || ''
  // Never fall back to the customer's estimate — that is not an AI payout.
  const amount = latestDecision.value?.suggested_payout
  payout.value = amount == null || amount === '' ? '' : String(amount)
  explanationDirty.value = false
  payoutDirty.value = false
  editingExplanation.value = false
  editingPayout.value = false
}

const recommendedPayoutLabel = computed(() => {
  const decision = latestDecision.value?.decision
  if (!latestDecision.value) return 'No automated recommendation is available yet'
  if (decision === 'refer_to_assessor') return 'No payout recommended — referred for manual review'
  if (decision === 'excluded') return 'No payout recommended — decline recommended'
  if (payout.value === '' || payout.value == null) return 'No payout amount has been calculated'
  return null
})

async function loadFiles(documents) {
  files.value.forEach((file) => URL.revokeObjectURL(file.url))
  const loaded = await Promise.all(
    (documents || []).map(async (doc, index) => {
      try {
        const blob = await api.documentBlob(doc.doc_id)
        return {
          id: doc.doc_id,
          label: `Damage ${index + 1}`,
          isImage: String(blob.type || doc.file_type || '').startsWith('image/'),
          url: blob.url,
        }
      } catch {
        return null
      }
    }),
  )
  files.value = loaded.filter(Boolean)
}

async function loadDecisionBrief() {
  briefLoading.value = true
  try {
    decisionBrief.value = await api.claimDecisionBrief(props.id)
  } catch {
    decisionBrief.value = null
  } finally {
    briefLoading.value = false
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    claim.value = await api.claimDetail(props.id)
    syncDrafts()
    await Promise.all([loadFiles(claim.value.documents), loadDecisionBrief()])
  } catch {
    error.value = 'This claim could not be loaded. Please try again.'
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => props.id, load)
onBeforeUnmount(() => files.value.forEach((file) => URL.revokeObjectURL(file.url)))

const actions = {
  approved: {
    title: 'Approve claim',
    body: 'Confirm approval of this claim. Add any notes required for the claim record.',
    confirm: 'Confirm approval',
    button: 'bg-emerald-600 hover:bg-emerald-700',
  },
  rejected: {
    title: 'Decline claim',
    body: 'Confirm that this claim should be declined. Provide a clear explanation for the record.',
    confirm: 'Confirm decline',
    button: 'bg-red-600 hover:bg-red-700',
  },
  under_review: {
    title: 'Escalate claim',
    body: 'Escalate this claim for senior assessor review. Provide the reason for escalation.',
    confirm: 'Confirm escalation',
    button: 'bg-orange-500 hover:bg-orange-600',
  },
}

function openReview(outcome) {
  reviewError.value = ''
  notes.value = ''
  pending.value = outcome
}

async function confirmReview() {
  if (pending.value === 'rejected' && !notes.value.trim()) {
    reviewError.value = 'Notes are required before a claim can be declined.'
    return
  }
  reviewError.value = ''
  submitting.value = true
  const payload = { outcome: pending.value, notes: notes.value }
  if (explanationDirty.value) payload.customer_explanation = explanation.value
  if (payoutDirty.value && payout.value !== '') payload.suggested_payout = Number(payout.value)
  try {
    claim.value = await api.reviewClaim(props.id, payload)
    syncDrafts()
    pending.value = null
  } catch (err) {
    reviewError.value = err instanceof ApiError ? errorText(err, 'The review decision could not be saved.') : 'The review decision could not be saved.'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div>
    <button class="mb-4 text-sm font-medium text-slate-500 hover:text-slate-900" @click="router.push({ name: 'assessor-queue' })">
      ← Back to claims queue
    </button>

    <p v-if="loading" class="text-sm text-slate-500">Loading claim details…</p>
    <p v-else-if="error" class="text-sm text-red-600">{{ error }}</p>

    <div v-else-if="claim" class="space-y-4">
      <section class="rounded-xl border border-slate-200 p-4">
        <div class="mb-4 flex items-start justify-between gap-3">
          <div>
            <p class="text-base font-bold text-slate-900">{{ claim.claim_reference }}</p>
            <p class="text-sm text-slate-500">{{ claim.customer_name }} — {{ claim.policy_number }}</p>
          </div>
          <span
            v-if="badge"
            class="rounded-full px-2.5 py-1 text-[11px] font-bold tracking-wide"
            :class="{
              'bg-emerald-50 text-emerald-700': badge.tone === 'green',
              'bg-red-50 text-red-700': badge.tone === 'red',
              'bg-amber-50 text-amber-700': badge.tone === 'amber',
            }"
          >
            {{ badge.label }}
          </span>
        </div>
        <dl class="grid grid-cols-2 gap-4 text-xs sm:grid-cols-4">
          <div>
            <dt class="font-semibold tracking-wide text-slate-400">SUBMITTED</dt>
            <dd class="mt-1 text-sm font-medium text-slate-800">{{ formatDate(claim.submission_date) }}</dd>
          </div>
          <div>
            <dt class="font-semibold tracking-wide text-slate-400">DAMAGE TYPE</dt>
            <dd class="mt-1 text-sm font-medium text-slate-800">{{ damageLabel(claim) }}</dd>
          </div>
          <div>
            <dt class="font-semibold tracking-wide text-slate-400">CUSTOMER ESTIMATE</dt>
            <dd class="mt-1 text-sm font-medium text-slate-800">{{ formatMoney(claim.estimated_value ?? claim.cost) }}</dd>
          </div>
          <div>
            <dt class="font-semibold tracking-wide text-slate-400">URGENCY</dt>
            <dd
              class="mt-1 text-sm font-semibold"
              :class="{
                'text-red-500': urgency(claim) === 'High',
                'text-amber-500': urgency(claim) === 'Medium',
                'text-emerald-600': urgency(claim) === 'Low',
              }"
            >
              {{ urgency(claim) }}
            </dd>
          </div>
        </dl>
      </section>

      <section class="rounded-xl border border-slate-200 p-4">
        <h2 class="mb-2 text-xs font-bold tracking-wide text-slate-500">CUSTOMER SUBMISSION</h2>
        <p class="text-sm leading-relaxed text-slate-700">
          {{ claim.incident_description || claim.loss_description || 'No description was provided.' }}
        </p>
        <div v-if="images.length" class="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
          <figure v-for="file in images" :key="file.id" class="overflow-hidden rounded-lg border border-slate-200">
            <img :src="file.url" :alt="file.label" class="h-28 w-full object-cover" />
            <figcaption class="px-2 py-1.5 text-xs text-slate-500">{{ file.label }}</figcaption>
          </figure>
        </div>
        <ul v-if="otherFiles.length" class="mt-3 space-y-1 text-sm">
          <li v-for="file in otherFiles" :key="file.id">
            <a class="text-blue-600 hover:underline" :href="file.url" target="_blank" rel="noopener">{{ file.label }}</a>
          </li>
        </ul>
        <p
          v-if="claim.similar_image_match"
          class="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800"
        >
          Potential image match identified on claim {{ claim.similar_image_match.matched_claim_reference }}
          ({{ claim.similar_image_match.matched_customer_name }}). Verify before relying on this finding.
        </p>
      </section>

      <section class="rounded-xl border border-violet-100 bg-violet-50/60 p-4">
        <div class="mb-3 flex flex-wrap items-center gap-2">
          <h2 class="text-sm font-semibold text-violet-900">Decision brief</h2>
          <span class="rounded-full bg-white px-2 py-0.5 text-[11px] font-semibold text-violet-600">
            Assessor review required
          </span>
          <span
            v-if="decisionBrief?.status === 'ready'"
            class="rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-semibold text-emerald-800"
          >
            Preliminary recommendation available
          </span>
        </div>
        <p v-if="briefLoading" class="text-sm text-slate-500">Preparing decision brief…</p>
        <div
          v-else-if="briefHtml"
          class="decision-brief prose-brief text-sm text-slate-800"
          v-html="briefHtml"
        />
        <p v-else class="text-sm leading-relaxed text-slate-800">
          A decision brief is not available yet. Automated assessment may still be in progress.
        </p>
        <p v-if="decisionBrief?.preliminary_decision && decisionBrief?.status === 'ready'" class="mt-3 text-xs text-slate-500">
          System outcome: {{ decisionBrief.preliminary_decision.replace(/_/g, ' ') }}
          <span v-if="decisionBrief.indicative_payment"> · indicative payment {{ decisionBrief.indicative_payment }}</span>
          <span v-else-if="decisionBrief.preliminary_decision === 'refer_to_assessor' || decisionBrief.preliminary_decision === 'excluded'"> · no indicative payment</span>
          <span v-if="decisionBrief.source"> · {{ decisionBrief.source === 'llm' ? 'generated summary' : 'standard template' }}</span>
        </p>
        <button class="mt-3 text-sm font-medium text-blue-600 hover:text-blue-700" @click="showAudit = !showAudit">
          {{ showAudit ? 'Hide technical detail' : 'View technical assessment detail and audit trail' }}
        </button>
        <div v-if="showAudit" class="mt-3 space-y-3 border-t border-violet-100 pt-3 text-sm text-slate-600">
          <div v-if="latestDecision?.assessor_memo">
            <p class="text-xs font-bold tracking-wide text-slate-400">INTERNAL ASSESSMENT MEMO</p>
            <p class="mt-1 whitespace-pre-wrap text-xs leading-relaxed">{{ latestDecision.assessor_memo }}</p>
          </div>
          <ul class="space-y-2">
            <li v-if="!claim.audit_trail?.length">No audit entries have been recorded for this decision.</li>
            <li v-for="entry in claim.audit_trail" :key="entry.log_id">
              <span class="font-semibold text-slate-800">{{ entry.action_type }}</span>
              — {{ entry.description || 'No description recorded' }}
              <span class="text-slate-400"> · {{ formatDate(entry.timestamp) }}</span>
            </li>
          </ul>
        </div>
      </section>

      <section class="rounded-xl border border-slate-200 p-4">
        <div class="mb-1 flex items-center justify-between">
          <h2 class="text-xs font-bold tracking-wide text-slate-400">RECOMMENDED PAYOUT</h2>
          <button class="text-sm font-medium text-violet-600" @click="editingPayout = !editingPayout">
            {{ editingPayout ? 'Done' : 'Edit' }}
          </button>
        </div>
        <input
          v-if="editingPayout"
          v-model="payout"
          type="number"
          min="0"
          step="1"
          class="field mt-2 max-w-xs"
          @input="payoutDirty = true"
        />
        <template v-else>
          <p v-if="recommendedPayoutLabel" class="mt-1 text-lg font-semibold leading-snug text-slate-700">
            {{ recommendedPayoutLabel }}
          </p>
          <p v-else class="text-3xl font-extrabold tracking-tight text-slate-900">{{ formatMoney(payout, { spaced: true }) }}</p>
        </template>
        <p class="mt-1 text-[11px] font-semibold text-violet-500">
          Automated recommendation only · Customer estimate is shown separately above
        </p>
      </section>

      <section class="rounded-xl border border-slate-200 p-4">
        <div class="mb-2 flex items-center justify-between">
          <h2 class="text-xs font-bold tracking-wide text-slate-400">CUSTOMER EXPLANATION</h2>
          <button class="text-sm font-medium text-violet-600" @click="editingExplanation = !editingExplanation">
            {{ editingExplanation ? 'Done' : 'Edit' }}
          </button>
        </div>
        <p class="mb-2 text-[11px] font-semibold text-violet-500">Draft explanation · Editable</p>
        <textarea
          v-if="editingExplanation"
          v-model="explanation"
          rows="5"
          class="field"
          @input="explanationDirty = true"
        />
        <p v-else class="text-sm leading-relaxed text-slate-700">
          {{ explanation || 'No customer explanation has been generated yet.' }}
        </p>
      </section>

      <ClaimRecordDetails :claim="claim" />

      <div class="grid gap-3 sm:grid-cols-3">
        <button class="rounded-lg bg-emerald-600 py-3 text-sm font-semibold text-white hover:bg-emerald-700" @click="openReview('approved')">
          Approve
        </button>
        <button class="rounded-lg bg-red-600 py-3 text-sm font-semibold text-white hover:bg-red-700" @click="openReview('rejected')">
          Decline
        </button>
        <button class="rounded-lg bg-orange-500 py-3 text-sm font-semibold text-white hover:bg-orange-600" @click="openReview('under_review')">
          Escalate
        </button>
      </div>
    </div>

    <div v-if="pending" class="fixed inset-0 z-20 grid place-items-center bg-slate-900/40 px-4" @click.self="pending = null">
      <div class="w-full max-w-md rounded-xl bg-white p-5 shadow-2xl">
        <div class="mb-2 flex items-start justify-between">
          <h3 class="text-base font-bold">{{ actions[pending].title }}</h3>
          <button class="text-slate-400 hover:text-slate-700" @click="pending = null">×</button>
        </div>
        <p class="text-sm text-slate-600">{{ actions[pending].body }}</p>
        <label class="mt-4 mb-1 block text-sm font-medium text-slate-700">Notes</label>
        <textarea v-model="notes" rows="4" class="field" placeholder="Enter notes for the claim record…" />
        <p v-if="reviewError" class="mt-2 text-sm text-red-600">{{ reviewError }}</p>
        <div class="mt-4 flex justify-end gap-2">
          <button class="rounded-lg px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100" @click="pending = null">Cancel</button>
          <button class="rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" :class="actions[pending].button" :disabled="submitting" @click="confirmReview">
            {{ submitting ? 'Saving…' : actions[pending].confirm }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.decision-brief :deep(h1) {
  margin: 0 0 0.75rem;
  font-size: 1.05rem;
  font-weight: 800;
  letter-spacing: 0.01em;
  color: #312e81;
}
.decision-brief :deep(h2) {
  margin: 1.25rem 0 0.5rem;
  font-size: 0.95rem;
  font-weight: 700;
  color: #1e1b4b;
}
.decision-brief :deep(h3) {
  margin: 0.85rem 0 0.35rem;
  font-size: 0.875rem;
  font-weight: 700;
  color: #312e81;
}
.decision-brief :deep(p),
.decision-brief :deep(li) {
  line-height: 1.55;
  margin: 0.35rem 0;
}
.decision-brief :deep(ul),
.decision-brief :deep(ol) {
  margin: 0.35rem 0 0.6rem 1.1rem;
  list-style: disc;
}
.decision-brief :deep(hr) {
  margin: 0.9rem 0;
  border: 0;
  border-top: 1px solid #ddd6fe;
}
.decision-brief :deep(.fraud-alert) {
  margin: 0 0 1rem;
  padding: 0.85rem 1rem;
  border: 1px solid #fecaca;
  border-left: 4px solid #dc2626;
  border-radius: 0.5rem;
  background: #fef2f2;
  color: #991b1b;
}
.decision-brief :deep(.fraud-alert h3) {
  color: #991b1b;
  margin-top: 0;
}
.decision-brief :deep(.fraud-alert strong) {
  color: #7f1d1d;
}
.decision-brief :deep(.fraud-alert ul) {
  margin-bottom: 0.35rem;
}
.decision-brief :deep(blockquote) {
  margin: 0.75rem 0;
  padding: 0.65rem 0.85rem;
  border-left: 3px solid #7c3aed;
  background: #ffffff;
  border-radius: 0.4rem;
  color: #4c1d95;
  white-space: pre-wrap;
}
.decision-brief :deep(table) {
  width: 100%;
  margin: 0.6rem 0 0.85rem;
  border-collapse: collapse;
  font-size: 0.8125rem;
  background: #fff;
}
.decision-brief :deep(th),
.decision-brief :deep(td) {
  border: 1px solid #e9e4ff;
  padding: 0.45rem 0.55rem;
  text-align: left;
  vertical-align: top;
}
.decision-brief :deep(th) {
  background: #f5f3ff;
  font-weight: 700;
}
.decision-brief :deep(strong) {
  font-weight: 700;
  color: #1e1b4b;
}
</style>
