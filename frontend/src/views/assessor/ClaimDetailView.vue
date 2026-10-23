<script setup>
import { computed, onBeforeUnmount, onMounted, provide, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  CheckCircle,
  DollarSign,
  ExternalLink,
  FileText,
  Pencil,
  XCircle,
} from 'lucide-vue-next'
import { api, ApiError } from '../../api/client'
import AiSteps from '../../components/assessor/AiSteps.vue'
import AssessorMemo from '../../components/assessor/AssessorMemo.vue'
import AuditLog from '../../components/assessor/AuditLog.vue'
import ClaimRecordDetails from '../../components/assessor/ClaimRecordDetails.vue'
import ConfidenceCard from '../../components/assessor/ConfidenceCard.vue'
import DecisionModal from '../../components/assessor/DecisionModal.vue'
import SimilarImageCard from '../../components/assessor/SimilarImageCard.vue'
import { POLICY_DOCUMENT_KEY, usePolicyDocument } from '../../components/assessor/usePolicyDocument'
import { recommendationMeta } from '../../utils/aiSteps'
import { damageLabel, errorText, formatDate, formatMoney, statusMeta, urgency } from '../../utils/claim'

const props = defineProps({ id: { type: [String, Number], required: true } })
const router = useRouter()

provide(POLICY_DOCUMENT_KEY, usePolicyDocument(() => props.id))

const vFocus = { mounted: (el) => el.focus() }

const claim = ref(null)
const loading = ref(true)
const error = ref('')
const files = ref([])
const filesLoading = ref(false)
const editingExplanation = ref(false)
const editingPayout = ref(false)
const explanation = ref('')
const payout = ref('')
const explanationDirty = ref(false)
const payoutDirty = ref(false)
const pending = ref(null)
const submitting = ref(false)
const reviewError = ref('')
const reviewSaved = ref('')

const assessment = computed(() => {
  const value = claim.value?.ai_assessment
  return value && typeof value === 'object' ? value : null
})
const latestDecision = computed(() => claim.value?.ai_decisions?.[0] ?? null)
const aiStatus = computed(() => {
  if (assessment.value) return assessment.value.status || 'complete'
  const decision = latestDecision.value?.decision
  return decision && decision !== 'pending' ? 'complete' : null
})
const hasDecision = computed(() => Boolean(aiStatus.value) && aiStatus.value !== 'pending')
const inProgress = computed(() => aiStatus.value === 'pending' || (!aiStatus.value && claim.value?.status === 'submitted'))
const decisionValue = computed(() => assessment.value?.decision ?? latestDecision.value?.decision ?? null)
const recommendation = computed(() => recommendationMeta(decisionValue.value))
const aiPayout = computed(() => {
  const value = assessment.value ? assessment.value.recommended_payout : latestDecision.value?.suggested_payout
  return value == null || value === '' ? null : value
})
const aiExplanation = computed(() => assessment.value?.customer_explanation || latestDecision.value?.customer_explanation || '')
const similarMatch = computed(() => {
  const match = claim.value?.similar_image_match
  return match && typeof match === 'object' && match.matched_claim_id != null ? match : null
})

const images = computed(() => files.value.filter((file) => file.isImage))
const otherFiles = computed(() => files.value.filter((file) => !file.isImage))
const description = computed(
  () => claim.value?.incident_description || claim.value?.loss_description || 'No description was provided.',
)

const STATUS_TONES = {
  green: 'bg-emerald-50 text-emerald-700',
  red: 'bg-red-50 text-red-700',
  amber: 'bg-amber-50 text-amber-700',
  blue: 'bg-blue-50 text-blue-700',
}
const status = computed(() => {
  const meta = statusMeta(claim.value?.status)
  return { label: meta.label, classes: STATUS_TONES[meta.tone] || 'bg-gray-100 text-gray-600' }
})
const urgencyLevel = computed(() => urgency(claim.value))
const urgencyClass = computed(
  () => ({ High: 'text-red-600', Medium: 'text-amber-600', Low: 'text-emerald-600' })[urgencyLevel.value] || 'text-gray-800',
)

function syncDrafts() {
  explanation.value = aiExplanation.value
  // Never fall back to the customer's estimate — that is not an AI payout.
  payout.value = aiPayout.value == null ? '' : String(aiPayout.value)
  explanationDirty.value = false
  payoutDirty.value = false
  editingExplanation.value = false
  editingPayout.value = false
}

const recommendedPayoutLabel = computed(() => {
  if (payoutDirty.value && payout.value !== '') return null
  if (!hasDecision.value) {
    return inProgress.value ? 'AI assessment in progress — no payout calculated yet' : 'No automated recommendation is available yet'
  }
  if (decisionValue.value === 'refer_to_assessor') return 'No payout recommended — referred for manual review'
  if (decisionValue.value === 'excluded') return 'No payout recommended — decline recommended'
  if (payout.value === '' || payout.value == null) return 'No payout amount has been calculated'
  return null
})
const payoutDisplay = computed(() => {
  const amount = Number(payout.value)
  return Number.isNaN(amount) ? '—' : amount.toLocaleString('en-AU', { maximumFractionDigits: 2 })
})
const payoutModified = computed(() => {
  if (!payoutDirty.value || payout.value === '') return ''
  if (aiPayout.value == null) return 'Set manually — no AI payout was suggested'
  return Number(payout.value) !== Number(aiPayout.value) ? `Modified from AI suggestion of ${formatMoney(aiPayout.value)}` : ''
})
const explanationModified = computed(() => explanationDirty.value && explanation.value !== aiExplanation.value)

function fileName(doc, fallback) {
  const raw = String(doc?.file_url || '').replace(/\\/g, '/').split('?')[0].split('/').pop() || ''
  let name = raw
  try {
    name = decodeURIComponent(raw)
  } catch {
    // keep the raw segment
  }
  return name.replace(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}-/i, '') || fallback
}

function revokeFiles() {
  files.value.forEach((file) => URL.revokeObjectURL(file.url))
  files.value = []
}

let filesGeneration = 0
async function loadFiles(documents) {
  const current = ++filesGeneration
  revokeFiles()
  filesLoading.value = true
  const loaded = await Promise.all(
    (Array.isArray(documents) ? documents : []).map(async (doc) => {
      try {
        const blob = await api.documentBlob(doc.doc_id)
        return { id: doc.doc_id, doc, url: blob.url, isImage: String(blob.type || doc.file_type || '').startsWith('image/') }
      } catch {
        return null
      }
    }),
  )
  if (current !== filesGeneration) {
    loaded.forEach((file) => file && URL.revokeObjectURL(file.url))
    return
  }
  let photo = 0
  let other = 0
  files.value = loaded
    .filter(Boolean)
    .map((file) => ({ ...file, label: file.isImage ? `Photo ${++photo}` : fileName(file.doc, `Document ${++other}`) }))
  filesLoading.value = false
}

async function load() {
  loading.value = true
  error.value = ''
  reviewSaved.value = ''
  pending.value = null
  try {
    claim.value = await api.claimDetail(props.id)
    syncDrafts()
  } catch {
    claim.value = null
    error.value = 'This claim could not be loaded. Please try again.'
  } finally {
    loading.value = false
  }
  if (claim.value) loadFiles(claim.value.documents)
}

onMounted(load)
watch(() => props.id, load)
onBeforeUnmount(() => {
  filesGeneration += 1
  revokeFiles()
})

function openReview(outcome) {
  reviewError.value = ''
  reviewSaved.value = ''
  pending.value = outcome
}

async function confirmReview(notes) {
  const outcome = pending.value
  const text = String(notes || '')
  if (outcome === 'rejected' && !text.trim()) {
    reviewError.value = 'Notes are required before a claim can be rejected.'
    return
  }
  const payload = { outcome, notes: text }
  if (explanationDirty.value) payload.customer_explanation = explanation.value
  if (payoutDirty.value && payout.value !== '') {
    const amount = Number(payout.value)
    if (Number.isNaN(amount) || amount < 0) {
      reviewError.value = 'Enter a valid payout amount before saving.'
      return
    }
    payload.suggested_payout = amount
  }
  reviewError.value = ''
  submitting.value = true
  try {
    claim.value = await api.reviewClaim(props.id, payload)
    syncDrafts()
    pending.value = null
    reviewSaved.value = `Decision saved — claim marked ${statusMeta(claim.value?.status || outcome).label.toLowerCase()}.`
  } catch (err) {
    reviewError.value =
      err instanceof ApiError ? errorText(err, 'The review decision could not be saved.') : 'The review decision could not be saved.'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div>
    <button
      type="button"
      class="mb-6 flex items-center gap-2 text-sm text-gray-500 transition-colors hover:text-gray-900"
      @click="router.push({ name: 'assessor-queue' })"
    >
      <ArrowLeft class="h-4 w-4" />
      Back to Claims
    </button>

    <p v-if="loading" class="text-sm text-gray-500">Loading claim details…</p>
    <div v-else-if="error" class="rounded-xl border border-red-200 bg-white p-6 text-sm text-red-600">
      {{ error }}
      <button type="button" class="ml-2 font-medium underline" @click="load">Retry</button>
    </div>

    <div v-else-if="claim" class="grid grid-cols-1 gap-6 lg:grid-cols-3">
      <div class="space-y-5 lg:col-span-2">
        <div class="rounded-xl border border-gray-200 bg-white p-6">
          <div class="mb-5 flex items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <h1 class="text-xl font-semibold tracking-tight text-gray-900">{{ claim.claim_reference }}</h1>
                <span class="rounded-full px-2 py-0.5 text-xs font-medium" :class="status.classes">{{ status.label }}</span>
              </div>
              <p class="mt-0.5 text-sm text-gray-500">{{ claim.customer_name }} — {{ claim.policy_number }}</p>
            </div>
            <span v-if="recommendation" class="shrink-0 rounded-full border px-2.5 py-1 text-xs font-semibold" :class="recommendation.pill">
              AI: {{ recommendation.label }}
            </span>
          </div>
          <div class="grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
            <div>
              <p class="mb-0.5 text-xs tracking-wide text-gray-400 uppercase">Submitted</p>
              <p class="font-medium text-gray-800">{{ formatDate(claim.submission_date) }}</p>
            </div>
            <div>
              <p class="mb-0.5 text-xs tracking-wide text-gray-400 uppercase">Damage Type</p>
              <p class="font-medium text-gray-800">{{ damageLabel(claim) }}</p>
            </div>
            <div>
              <p class="mb-0.5 text-xs tracking-wide text-gray-400 uppercase">Estimated Damage</p>
              <p class="font-medium text-gray-800">{{ formatMoney(claim.estimated_value ?? claim.cost) }}</p>
            </div>
            <div>
              <p class="mb-0.5 text-xs tracking-wide text-gray-400 uppercase">Urgency</p>
              <p class="font-medium" :class="urgencyClass">{{ urgencyLevel }}</p>
            </div>
          </div>
        </div>

        <div class="space-y-4 rounded-xl border border-gray-200 bg-white p-6">
          <h2 class="text-sm font-semibold tracking-wide text-gray-900 uppercase">Customer Submission</h2>
          <p class="text-sm leading-relaxed whitespace-pre-line text-gray-700">{{ description }}</p>
          <p v-if="filesLoading" class="text-xs text-gray-400">Loading attachments…</p>
          <div v-if="images.length" class="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <a v-for="file in images" :key="file.id" :href="file.url" target="_blank" rel="noopener" class="relative block" :title="`Open ${file.label} in a new tab`">
              <img :src="file.url" :alt="file.label" class="h-44 w-full rounded-lg border border-gray-100 object-cover" />
              <span class="absolute bottom-2 left-2 rounded bg-black/55 px-1.5 py-0.5 text-xs font-medium text-white">{{ file.label }}</span>
            </a>
          </div>
          <ul v-if="otherFiles.length" class="space-y-1.5">
            <li v-for="file in otherFiles" :key="file.id">
              <a :href="file.url" target="_blank" rel="noopener" class="inline-flex items-center gap-2 text-sm text-indigo-600 hover:text-indigo-800">
                <FileText class="h-4 w-4 shrink-0" />
                <span class="break-all">{{ file.label }}</span>
                <ExternalLink class="h-3.5 w-3.5 shrink-0" />
              </a>
            </li>
          </ul>
          <template v-if="!filesLoading && !files.length">
            <p v-if="claim.documents?.length" class="text-xs text-gray-400">Attachments could not be loaded.</p>
            <p v-else class="text-xs text-gray-400">No photos or documents were attached.</p>
          </template>
        </div>

        <SimilarImageCard v-if="similarMatch" :match="similarMatch" />

        <ClaimRecordDetails :claim="claim" />

        <div class="flex items-center gap-2 pt-3">
          <p class="text-xs font-bold tracking-widest text-gray-400 uppercase">AI Assessment</p>
          <div class="h-px flex-1 bg-gray-200" />
        </div>

        <AssessorMemo :assessment="assessment" :fallback-text="latestDecision?.assessor_memo || ''" :in-progress="inProgress" />

        <div class="rounded-xl border border-gray-200 bg-white p-6">
          <div class="mb-4 flex items-center justify-between gap-3">
            <h2 class="text-sm font-semibold tracking-wide text-gray-900 uppercase">Recommended Payout</h2>
            <span class="rounded-full bg-violet-100 px-2 py-0.5 text-xs font-medium text-violet-700">AI Draft · Editable</span>
          </div>
          <div v-if="editingPayout" class="flex items-center gap-2">
            <span class="text-lg font-medium text-gray-500">$</span>
            <input
              v-model="payout"
              v-focus
              type="number"
              min="0"
              step="1"
              aria-label="Recommended payout"
              class="min-w-0 flex-1 rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:ring-2 focus:ring-violet-300 focus:outline-none"
              @input="payoutDirty = true"
              @keydown.enter.prevent="editingPayout = false"
            />
            <button
              type="button"
              class="flex items-center gap-1.5 rounded-lg bg-emerald-100 px-3 py-2.5 text-sm font-medium text-emerald-700 transition-colors hover:bg-emerald-200"
              @click="editingPayout = false"
            >
              <Check class="h-4 w-4" />
              Save
            </button>
          </div>
          <div v-else class="flex items-center justify-between gap-3">
            <p v-if="recommendedPayoutLabel" class="text-base leading-snug font-medium text-gray-600">{{ recommendedPayoutLabel }}</p>
            <div v-else class="flex items-center gap-2">
              <DollarSign class="h-6 w-6 text-emerald-500" />
              <span class="text-3xl font-bold text-gray-900">{{ payoutDisplay }}</span>
            </div>
            <button
              type="button"
              class="flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-2 text-sm text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-800"
              @click="editingPayout = true"
            >
              <Pencil class="h-3.5 w-3.5" />
              Edit
            </button>
          </div>
          <p v-if="payoutModified" class="mt-2 text-xs text-amber-600">{{ payoutModified }}</p>
          <p class="mt-3 text-xs text-gray-400">AI recommendation only — the customer's own estimate is shown in the claim header.</p>
        </div>

        <div class="rounded-xl border border-gray-200 bg-white p-6">
          <div class="mb-4 flex items-center justify-between gap-3">
            <h2 class="text-sm font-semibold tracking-wide text-gray-900 uppercase">Customer Explanation</h2>
            <div class="flex items-center gap-2">
              <span class="rounded-full bg-violet-100 px-2 py-0.5 text-xs font-medium text-violet-700">AI Draft · Editable</span>
              <button
                v-if="!editingExplanation"
                type="button"
                class="flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-800"
                @click="editingExplanation = true"
              >
                <Pencil class="h-3.5 w-3.5" />
                Edit
              </button>
            </div>
          </div>
          <div v-if="editingExplanation" class="space-y-3">
            <textarea
              v-model="explanation"
              v-focus
              rows="6"
              aria-label="Customer explanation"
              class="w-full resize-y rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:ring-2 focus:ring-violet-300 focus:outline-none"
              @input="explanationDirty = true"
            />
            <button
              type="button"
              class="flex items-center gap-1.5 rounded-lg bg-emerald-100 px-3 py-2 text-sm font-medium text-emerald-700 transition-colors hover:bg-emerald-200"
              @click="editingExplanation = false"
            >
              <Check class="h-4 w-4" />
              Save
            </button>
          </div>
          <p v-else-if="explanation" class="text-sm leading-relaxed whitespace-pre-line text-gray-700">{{ explanation }}</p>
          <p v-else class="text-sm text-gray-500">
            {{ inProgress ? 'The customer explanation will appear once the AI assessment completes.' : 'No customer explanation has been generated yet.' }}
          </p>
          <p v-if="explanationModified" class="mt-2 text-xs text-amber-600">Edited from AI draft</p>
          <p class="mt-3 text-xs text-gray-400">The customer is notified by email when you record a decision.</p>
        </div>

        <div class="space-y-3">
          <div class="flex flex-col gap-3 sm:flex-row">
            <button
              type="button"
              class="flex flex-1 items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-3 font-medium text-white transition-colors hover:bg-emerald-700"
              @click="openReview('approved')"
            >
              <CheckCircle class="h-5 w-5" />
              Approve
            </button>
            <button
              type="button"
              class="flex flex-1 items-center justify-center gap-2 rounded-xl bg-red-600 px-4 py-3 font-medium text-white transition-colors hover:bg-red-700"
              @click="openReview('rejected')"
            >
              <XCircle class="h-5 w-5" />
              Reject
            </button>
            <button
              type="button"
              class="flex flex-1 items-center justify-center gap-2 rounded-xl bg-amber-500 px-4 py-3 font-medium text-white transition-colors hover:bg-amber-600"
              @click="openReview('under_review')"
            >
              <AlertTriangle class="h-5 w-5" />
              Escalate
            </button>
          </div>
          <p v-if="reviewSaved" class="flex items-center gap-1.5 text-sm text-emerald-700">
            <CheckCircle class="h-4 w-4" />
            {{ reviewSaved }}
          </p>
        </div>

        <AuditLog :entries="Array.isArray(claim.audit_trail) ? claim.audit_trail : []" />
      </div>

      <aside class="lg:col-span-1">
        <div class="space-y-4 lg:sticky lg:top-6 lg:max-h-[calc(100vh-3rem)] lg:overflow-y-auto">
          <ConfidenceCard
            :assessment="assessment"
            :recommendation="recommendation"
            :fallback-score="hasDecision ? latestDecision?.confidence_score ?? null : null"
            :in-progress="inProgress"
          />
          <AiSteps :assessment="assessment" :similar-match="similarMatch" :in-progress="inProgress" />
          <SimilarImageCard v-if="similarMatch" :match="similarMatch" compact />
        </div>
      </aside>
    </div>

    <DecisionModal
      v-if="pending"
      :outcome="pending"
      :submitting="submitting"
      :error="reviewError"
      @close="pending = null"
      @confirm="confirmReview"
    />
  </div>
</template>
