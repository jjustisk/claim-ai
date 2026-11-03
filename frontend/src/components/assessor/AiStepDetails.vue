<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { AlertTriangle, CheckCircle, ExternalLink } from 'lucide-vue-next'
import DetailField from './DetailField.vue'
import PolicyClauseCard from './PolicyClauseCard.vue'
import ScoreBar from './ScoreBar.vue'
import { formatMoney } from '../../utils/claim'
import {
  confidenceBand,
  decisionLabel,
  hasPath,
  humanise,
  imageMatchCloseness,
  mergeClauses,
  pick,
  unitToPercent,
} from '../../utils/aiSteps'

const props = defineProps({
  step: { type: Object, required: true },
  assessment: { type: Object, default: null },
  similarMatch: { type: Object, default: null },
})

const router = useRouter()

const details = computed(() => {
  const value = props.step.details
  return value && typeof value === 'object' && !Array.isArray(value) ? value : {}
})
const hasDetails = computed(() => Object.keys(details.value).length > 0)
const notRun = computed(() => props.step.status === 'pending' || props.step.status === 'skipped')
const flagged = computed(() => props.step.status === 'flag' || props.step.status === 'fail')

function toList(value) {
  if (Array.isArray(value)) return value.filter((item) => item != null && item !== '')
  if (typeof value === 'string' && value.trim()) return value.split(/\s*[,;]\s*/).filter(Boolean)
  return []
}

function itemText(item) {
  if (item && typeof item === 'object') return Object.values(item).filter((v) => v != null && v !== '').join(' / ')
  return String(item)
}

function plural(count, word) {
  return `${count} ${word}${Number(count) === 1 ? '' : 's'}`
}

const privacy = computed(() => {
  const d = details.value
  const defaults = {
    pass: 'Names, contact details and other personal information are replaced with placeholders before any text or photo is sent to an AI model (Privacy Act 1988, APP 11).',
    fail: 'Because screening did not complete, no AI model was called. Assess this claim manually.',
  }
  const masked = pick(d, 'masked_count', 'entities_masked', 'pii_count', 'entity_count')
  return {
    text: defaults[props.step.status] || '',
    masked: typeof masked === 'number' ? masked : null,
    categories: toList(pick(d, 'entity_types', 'categories')).map(humanise),
    reason: pick(d, 'reason', 'error'),
  }
})

const damage = computed(() => {
  const d = details.value
  const tiles = [
    { label: 'Object identified', value: humanise(pick(d, 'object_identified', 'object')) },
    { label: 'Damage type', value: humanise(pick(d, 'damage_type', 'type')) },
    { label: 'Severity', value: humanise(pick(d, 'severity')) },
    { label: 'Damage age', value: humanise(pick(d, 'damage_age_estimate', 'damage_age', 'age')) },
  ].filter((tile) => tile.value)
  const assessed = pick(d, 'images_assessed', 'images.assessed')
  const available = pick(d, 'images_available', 'images_total', 'image_count', 'images.available')
  let images = ''
  if (assessed != null && available != null) images = `${assessed} of ${plural(available, 'image')} assessed`
  else if (assessed != null) images = `${plural(assessed, 'image')} assessed`
  else if (available != null) images = `${plural(available, 'image')} available`
  return {
    description: pick(d, 'damage_description', 'description'),
    tiles,
    areas: toList(pick(d, 'affected_areas', 'areas')).map(itemText),
    reasoning: pick(d, 'reasoning'),
    images,
    notAssessable: pick(d, 'images_assessable') === false,
  }
})

const consistency = computed(() => {
  const d = details.value
  return {
    score: unitToPercent(pick(d, 'consistency_flag', 'consistency_score', 'score', 'consistency')),
    discrepancies: toList(d.discrepancies).map(itemText),
    hasDiscrepancyList: Array.isArray(d.discrepancies),
    reasoning: pick(d, 'reasoning'),
  }
})

const imageMatch = computed(() => {
  const own = details.value.image_match
  const match = own && typeof own === 'object' && own.matched_claim_id != null ? own : props.similarMatch
  if (!match || match.matched_claim_id == null) return null
  const reference = match.matched_claim_reference || `#${match.matched_claim_id}`
  return {
    reference,
    closeness: imageMatchCloseness(match.hamming_distance),
    href: router.resolve({ name: 'assessor-claim-detail', params: { id: String(match.matched_claim_id) } }).href,
  }
})

const fraud = computed(() => {
  const d = details.value
  const count = pick(d, 'claim_count', 'history.claim_count', 'fraud_history.claim_count')
  const rate = pick(d, 'rejection_rate', 'history.rejection_rate', 'fraud_history.rejection_rate')
  const history = []
  if (count != null) history.push(`${plural(count, 'other claim')} in the last 12 months`)
  if (rate != null) history.push(`${unitToPercent(rate)}% of resolved claims rejected`)
  const dayPaths = ['days_since_last_claim', 'frequency.days_since_last_claim', 'fraud_frequency.days_since_last_claim']
  let frequency = ''
  if (hasPath(d, ...dayPaths)) {
    const days = pick(d, ...dayPaths)
    frequency = days == null ? 'No previous claims on record' : `${plural(days, 'day')} since the previous claim`
  }
  return {
    risk: unitToPercent(pick(d, 'fraud_flag', 'fraud_risk', 'fraud_score')),
    history: history.join(' · '),
    frequency,
  }
})

const RETRIEVAL_ACTIONS = {
  correct: 'Clear match',
  ambiguous: 'Ambiguous — more than one clause could apply',
  incorrect: 'No clear match',
}

const policy = computed(() => {
  const d = details.value
  const reference = Array.isArray(props.assessment?.clauses) ? props.assessment.clauses : []
  const own = Array.isArray(d.clauses) ? d.clauses.map((c) => (typeof c === 'string' ? { section_ref: c } : c)) : []
  return {
    action: RETRIEVAL_ACTIONS[pick(d, 'action', 'retrieval_action')] || humanise(pick(d, 'action', 'retrieval_action')),
    needsReview: pick(d, 'needs_review', 'needs_human_review') === true,
    reasoning: pick(d, 'reasoning', 'retrieval_reasoning'),
    clauses: own.length ? mergeClauses(own, reference) : reference,
  }
})

const decision = computed(() => {
  const d = details.value
  const confidence = props.assessment?.confidence || {}
  const score = unitToPercent(pick(d, 'confidence.score', 'confidence_score', 'confidence') ?? confidence.score)
  const band = confidenceBand(score, pick(d, 'band', 'confidence.band') ?? confidence.band)
  const payout = pick(d, 'payout', 'recommended_payout', 'suggested_payout') ?? props.assessment?.recommended_payout ?? null
  const raw = pick(d, 'self_consistency')
  const samples = pick(d, 'self_consistency.samples', 'self_consistency_samples')
  const agreement = pick(d, 'self_consistency.agreement', 'self_consistency_agreement')
  let selfConsistency = ''
  if (typeof raw === 'string') selfConsistency = raw
  else if (Number(samples) > 1) {
    selfConsistency = `Confidence was borderline, so the decision was re-run ${samples} times${agreement ? ` — ${agreement} runs agreed on this outcome` : ''}.`
  } else if (Number(samples) === 1) {
    selfConsistency = 'Single run — confidence was clear enough that no re-check was needed.'
  }
  return {
    coverage: decisionLabel(pick(d, 'decision', 'coverage_decision') ?? props.assessment?.decision),
    score,
    band: band ? humanise(band) : '',
    payout,
    payoutNote: pick(d, 'payout_note'),
    reasoning: pick(d, 'reasoning'),
    capped: pick(d, 'retrieval_capped') === true,
    selfConsistency,
  }
})

const genericRows = computed(() =>
  Object.entries(details.value)
    .filter(([, value]) => value != null && value !== '' && typeof value !== 'object')
    .map(([key, value]) => ({ label: humanise(key), value: humanise(value) })),
)
</script>

<template>
  <div class="space-y-4">
    <p v-if="notRun && !hasDetails" class="text-sm text-gray-500">
      {{ step.status === 'skipped' ? 'This step was skipped for this claim.' : 'This step has not run yet.' }}
    </p>

    <template v-else-if="step.key === 'pii_reduction'">
      <p v-if="privacy.text" class="text-sm leading-relaxed text-gray-700">{{ privacy.text }}</p>
      <p v-if="privacy.masked != null" class="text-sm text-gray-700">{{ plural(privacy.masked, 'personal detail') }} masked</p>
      <div v-if="privacy.categories.length" class="flex flex-wrap gap-1.5">
        <span v-for="item in privacy.categories" :key="item" class="rounded-full border border-gray-200 bg-white px-2 py-0.5 text-xs text-gray-700">{{ item }}</span>
      </div>
      <DetailField v-if="privacy.reason && step.status === 'fail'" label="Reason" :value="privacy.reason" />
    </template>

    <template v-else-if="step.key === 'damage_description'">
      <div v-if="damage.description">
        <p class="mb-1.5 text-xs font-semibold tracking-wide text-violet-700 uppercase">What the AI observed in the photos</p>
        <p class="rounded-lg border border-violet-100 bg-violet-50 p-3 text-sm leading-relaxed text-gray-700">{{ damage.description }}</p>
      </div>
      <div v-if="damage.notAssessable" class="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3">
        <AlertTriangle class="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
        <p class="text-sm text-amber-700">The photos were not clear or complete enough for a confident assessment.</p>
      </div>
      <div v-if="damage.tiles.length" class="grid grid-cols-2 gap-3">
        <div v-for="tile in damage.tiles" :key="tile.label" class="rounded-lg border border-gray-100 bg-white p-3">
          <p class="mb-0.5 text-xs tracking-wide text-gray-400 uppercase">{{ tile.label }}</p>
          <p class="text-sm font-medium text-gray-800">{{ tile.value }}</p>
        </div>
      </div>
      <DetailField v-if="damage.areas.length" label="Affected areas">
        <div class="flex flex-wrap gap-1.5">
          <span v-for="area in damage.areas" :key="area" class="rounded-full border border-gray-200 bg-white px-2 py-0.5 text-xs text-gray-700">{{ area }}</span>
        </div>
      </DetailField>
      <DetailField v-if="damage.reasoning" label="Reasoning" :value="damage.reasoning" />
      <p v-if="damage.images" class="text-xs text-gray-400">{{ damage.images }}</p>
    </template>

    <template v-else-if="step.key === 'consistency_check'">
      <ScoreBar v-if="consistency.score != null" :score="consistency.score" label="Statement–photo consistency" />
      <DetailField v-if="consistency.discrepancies.length" label="Discrepancies">
        <ul class="space-y-1.5">
          <li v-for="(item, i) in consistency.discrepancies" :key="i" class="flex items-start gap-2 text-sm text-gray-700">
            <AlertTriangle class="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
            <span class="leading-relaxed">{{ item }}</span>
          </li>
        </ul>
      </DetailField>
      <p v-else-if="consistency.hasDiscrepancyList" class="flex items-center gap-2 text-sm text-gray-700">
        <CheckCircle class="h-4 w-4 shrink-0 text-emerald-500" />
        No discrepancies found between the statement and the photos.
      </p>
      <DetailField v-if="consistency.reasoning" label="Reasoning" :value="consistency.reasoning" />
    </template>

    <template v-else-if="step.key === 'fraud_check'">
      <div v-if="flagged" class="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3">
        <AlertTriangle class="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
        <p class="text-sm text-amber-700">
          One or more awareness flags were raised. These do not constitute evidence of fraud and are provided for assessor transparency only.
        </p>
      </div>
      <ScoreBar v-if="fraud.risk != null" :score="fraud.risk" label="Fraud risk signal (lower is better)" invert />
      <div v-if="fraud.history" class="border-l-2 border-gray-200 pl-3">
        <p class="mb-0.5 text-xs font-semibold tracking-wide text-gray-400 uppercase">Claim history</p>
        <p class="text-sm text-gray-700">{{ fraud.history }}</p>
      </div>
      <div v-if="fraud.frequency" class="border-l-2 border-gray-200 pl-3">
        <p class="mb-0.5 text-xs font-semibold tracking-wide text-gray-400 uppercase">Claim frequency</p>
        <p class="text-sm text-gray-700">{{ fraud.frequency }}</p>
      </div>
      <div class="border-l-2 border-gray-200 pl-3">
        <p class="mb-0.5 text-xs font-semibold tracking-wide text-gray-400 uppercase">Duplicate image check</p>
        <p v-if="imageMatch" class="text-sm text-gray-700">
          {{ imageMatch.closeness }} found on claim {{ imageMatch.reference }}.
          <a :href="imageMatch.href" target="_blank" rel="noopener" class="ml-1 inline-flex items-center gap-1 font-medium text-indigo-600 hover:text-indigo-800">
            Open claim {{ imageMatch.reference }} in new tab
            <ExternalLink class="h-3.5 w-3.5" />
          </a>
        </p>
        <p v-else class="text-sm text-gray-700">No similar images found on other claims.</p>
      </div>
    </template>

    <template v-else-if="step.key === 'policy_match'">
      <div v-if="policy.needsReview" class="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3">
        <AlertTriangle class="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
        <p class="text-sm text-amber-700">The clause match was ambiguous, so this claim was flagged for human review.</p>
      </div>
      <DetailField v-if="policy.action" label="Retrieval outcome" :value="policy.action" />
      <DetailField v-if="policy.reasoning" label="Reasoning" :value="policy.reasoning" />
      <div v-if="policy.clauses.length" class="space-y-3">
        <p class="text-xs font-semibold tracking-wide text-gray-400 uppercase">Matched clauses</p>
        <PolicyClauseCard v-for="(clause, i) in policy.clauses" :key="`${clause.section_ref}-${i}`" :clause="clause" variant="evidence" />
      </div>
      <p v-else class="text-sm text-gray-500">No policy clauses were matched.</p>
    </template>

    <template v-else-if="step.key === 'decision'">
      <div class="grid grid-cols-2 gap-3">
        <div class="rounded-lg border border-gray-100 bg-white p-3">
          <p class="mb-0.5 text-xs tracking-wide text-gray-400 uppercase">Coverage decision</p>
          <p class="text-sm font-medium text-gray-800">{{ decision.coverage || '—' }}</p>
        </div>
        <div class="rounded-lg border border-gray-100 bg-white p-3">
          <p class="mb-0.5 text-xs tracking-wide text-gray-400 uppercase">Recommended payout</p>
          <p class="text-sm font-medium text-gray-800">{{ decision.payout != null ? formatMoney(decision.payout) : 'No payout recommended' }}</p>
        </div>
      </div>
      <div v-if="decision.score != null">
        <ScoreBar :score="decision.score" label="Overall decision confidence" />
        <p v-if="decision.band" class="mt-1 text-xs text-gray-400">{{ decision.band }} confidence band</p>
      </div>
      <p v-else class="text-sm text-gray-500">No automated confidence score — referred for manual review.</p>
      <p v-if="decision.capped" class="text-xs text-amber-600">
        Confidence was capped at moderate because the policy clause match needed human review.
      </p>
      <DetailField v-if="decision.reasoning" label="Reasoning" :value="decision.reasoning" />
      <DetailField v-if="decision.selfConsistency" label="Self-consistency check" :value="decision.selfConsistency" />
      <DetailField v-if="decision.payoutNote" label="Payout note" :value="decision.payoutNote" />
    </template>

    <template v-else>
      <dl v-if="genericRows.length" class="grid gap-3">
        <div v-for="row in genericRows" :key="row.label">
          <dt class="text-xs tracking-wide text-gray-400 uppercase">{{ row.label }}</dt>
          <dd class="text-sm font-medium text-gray-800">{{ row.value }}</dd>
        </div>
      </dl>
      <p v-else class="text-sm text-gray-500">{{ step.summary || 'No further detail was recorded for this step.' }}</p>
    </template>
  </div>
</template>
