import { markRaw } from 'vue'
import { AlertTriangle, CheckCircle, Clock, Eye, Lock, Scale, Search, ShieldCheck, Sparkles, XCircle } from 'lucide-vue-next'

const NEUTRAL_ICON = { iconBg: 'bg-gray-100', iconColor: 'text-gray-500' }

export const AI_STEPS = [
  { key: 'pii_reduction', label: 'Personal details protected', icon: markRaw(Lock), ...NEUTRAL_ICON },
  { key: 'damage_description', label: 'Photos reviewed', icon: markRaw(Search), ...NEUTRAL_ICON },
  { key: 'consistency_check', label: 'Account matches photos', icon: markRaw(Eye), ...NEUTRAL_ICON },
  { key: 'fraud_check', label: 'Warning signs', icon: markRaw(ShieldCheck), ...NEUTRAL_ICON },
  { key: 'policy_match', label: 'Policy match', icon: markRaw(Scale), ...NEUTRAL_ICON },
  { key: 'decision', label: 'Overall recommendation', icon: markRaw(Sparkles), ...NEUTRAL_ICON },
]

const STEP_BY_KEY = Object.fromEntries(AI_STEPS.map((step) => [step.key, step]))

export function stepMeta(key, fallbackLabel) {
  return STEP_BY_KEY[key] || { key, label: fallbackLabel || humanise(key) || 'Pipeline step', icon: markRaw(Sparkles), ...NEUTRAL_ICON }
}

export function orderSteps(steps) {
  const list = Array.isArray(steps) ? steps.filter((step) => step && typeof step === 'object') : []
  const rank = (key) => {
    const index = AI_STEPS.findIndex((step) => step.key === key)
    return index === -1 ? AI_STEPS.length : index
  }
  return list.map((step, index) => ({ step, index })).sort((a, b) => rank(a.step.key) - rank(b.step.key) || a.index - b.index).map(({ step }) => step)
}

const STEP_STATUS = {
  pass: { label: 'All clear', dotBg: 'bg-emerald-100', icon: markRaw(CheckCircle), iconColor: 'text-emerald-600', subtitleClass: 'text-gray-500', subtitleIcon: null },
  flag: { label: 'Needs a look', dotBg: 'bg-amber-100', icon: markRaw(AlertTriangle), iconColor: 'text-amber-600', subtitleClass: 'text-amber-600', subtitleIcon: markRaw(AlertTriangle) },
  fail: { label: 'Problem', dotBg: 'bg-red-100', icon: markRaw(XCircle), iconColor: 'text-red-600', subtitleClass: 'text-red-600', subtitleIcon: markRaw(XCircle) },
  pending: { label: 'Not done yet', dotBg: 'bg-gray-100', icon: markRaw(Clock), iconColor: 'text-gray-400', subtitleClass: 'text-gray-500', subtitleIcon: null },
  skipped: { label: 'Skipped', dotBg: 'bg-gray-100', icon: markRaw(Clock), iconColor: 'text-gray-400', subtitleClass: 'text-gray-500', subtitleIcon: null },
}

export function stepStatusMeta(status) {
  return STEP_STATUS[status] || STEP_STATUS.pending
}

const AUDIT_LABELS = {
  pii_reduction: 'Personal details protected',
  damage_description: 'Photos reviewed',
  consistency_check: 'Account matched against photos',
  fraud_check: 'Warning signs checked',
  policy_match: 'Policy matched',
  retrieval: 'Policy matched',
  generation: 'Recommendation prepared',
  decision: 'Recommendation prepared',
}

export function auditActionLabel(actionType) {
  return AUDIT_LABELS[actionType] || humanise(actionType) || 'Pipeline event'
}

const RECOMMENDATIONS = {
  approve: { key: 'approve', label: 'Approve', pill: 'bg-emerald-50 text-emerald-700 border-emerald-200', box: 'bg-emerald-50 border-emerald-200', text: 'text-emerald-700' },
  review: { key: 'review', label: 'Review', pill: 'bg-amber-50 text-amber-700 border-amber-200', box: 'bg-amber-50 border-amber-200', text: 'text-amber-700' },
  decline: { key: 'decline', label: 'Decline recommended', pill: 'bg-red-50 text-red-700 border-red-200', box: 'bg-red-50 border-red-200', text: 'text-red-700' },
}

function isCoveredDecision(value) {
  return value === 'covered' || value === 'partial' || value.includes('approv')
}

function isExcludedDecision(value) {
  return value === 'excluded' || value.includes('reject') || value.includes('declin')
}

// Simple mapping from the stored decision alone (no checks); used when no assessment detail is available.
export function recommendationMeta(decision) {
  const value = String(decision || '').toLowerCase()
  if (!value || value === 'pending') return null
  if (isCoveredDecision(value)) return RECOMMENDATIONS.approve
  if (isExcludedDecision(value)) return RECOMMENDATIONS.decline
  return RECOMMENDATIONS.review
}

const SURENESS = { high: 'Strong', moderate: 'Moderate', low: 'Limited' }

function reviewReason(byKey, concerns, covered, excluded) {
  if (byKey.pii_reduction?.status === 'fail') return "Personal details couldn't be protected, so the automatic checks didn't run."
  if (byKey.damage_description && ['flag', 'fail'].includes(byKey.damage_description.status)) {
    return "The photos weren't clear enough to judge the damage."
  }
  if (byKey.fraud_check?.status === 'flag') {
    const ref = byKey.fraud_check.details?.image_match?.matched_claim_reference
    return ref ? `A photo matches one on claim ${ref}.` : 'There are warning signs in this customer\'s claim history.'
  }
  if (byKey.consistency_check?.status === 'flag') return "The customer's account doesn't fully match the photos."
  if (byKey.policy_match?.status === 'flag') {
    return byKey.policy_match.details?.action === 'incorrect'
      ? 'No policy section clearly matches this claim.'
      : "It's unclear which policy section applies."
  }
  if (excluded) return 'This looks like it is not covered, but it needs a check first.'
  if (covered) return 'Likely covered, but not certain enough to approve without a look.'
  return concerns.length ? 'Some checks need your attention.' : 'Sent for your review.'
}

// One clear recommendation: Approve only when the decision is covered, the checks are strong and nothing was
// flagged. A clear exclusion with nothing flagged is Decline. Anything unsure or flagged (including possible
// fraud) goes to Review so a person decides.
export function buildRecommendation(assessment, decisionValue) {
  const value = String(decisionValue || '').toLowerCase()
  if (!value || value === 'pending') return null

  const steps = Array.isArray(assessment?.steps) ? assessment.steps : []
  const byKey = Object.fromEntries(steps.map((step) => [step.key, step]))
  const concerns = steps.filter((step) => step.key !== 'decision' && (step.status === 'flag' || step.status === 'fail'))
  const band = confidenceBand(assessment?.confidence?.score, assessment?.confidence?.band)
  const clauses = Array.isArray(assessment?.clauses) ? assessment.clauses : []
  const covered = isCoveredDecision(value)
  const excluded = isExcludedDecision(value)
  const partial = value === 'partial'

  const strong = band === 'high' || band == null
  let kind = 'review'
  if (covered && strong && !concerns.length) kind = 'approve'
  else if (excluded && band !== 'low' && !concerns.length) kind = 'decline'

  const section = sectionLabel((clauses.find((clause) => excluded === isExclusion(clause)) || clauses[0])?.section_ref)
  let reason
  if (kind === 'approve') {
    reason = partial
      ? `Covered in part${section ? ` under ${section}` : ''}. The suggested amount reflects what isn't covered.`
      : `Covered${section ? ` under ${section}` : ' by the policy'}.${steps.length ? ' The photos match the account and nothing looks wrong.' : ''}`
  } else if (kind === 'decline') {
    reason = `The policy doesn't cover this${section ? ` (${section})` : ''}.`
  } else {
    reason = reviewReason(byKey, concerns, covered, excluded)
  }

  return {
    ...RECOMMENDATIONS[kind],
    reason,
    partial: partial && kind === 'approve',
    possibleFraud: byKey.fraud_check?.status === 'flag',
    sureness: SURENESS[band] || null,
  }
}

const DECISION_LABELS = {
  covered: 'Covered',
  partial: 'Covered in part',
  excluded: 'Not covered',
  refer_to_assessor: 'Sent for review',
  pending: 'Pending',
}

export function decisionLabel(decision) {
  return DECISION_LABELS[decision] || humanise(decision)
}

export function confidenceBand(score, band) {
  if (band === 'high' || band === 'moderate' || band === 'low') return band
  if (score == null || Number.isNaN(Number(score))) return null
  const value = Number(score)
  if (value >= 85) return 'high'
  if (value >= 70) return 'moderate'
  return 'low'
}

export function pick(obj, ...paths) {
  for (const path of paths) {
    const value = path.split('.').reduce((acc, key) => (acc == null ? undefined : acc[key]), obj)
    if (value !== undefined && value !== null && value !== '') return value
  }
  return null
}

export function hasPath(obj, ...paths) {
  return paths.some((path) => {
    const keys = path.split('.')
    const last = keys.pop()
    const parent = keys.reduce((acc, key) => (acc == null ? undefined : acc[key]), obj)
    return parent != null && typeof parent === 'object' && last in parent
  })
}

export function unitToPercent(value) {
  if (value == null || value === '') return null
  const number = Number(value)
  if (Number.isNaN(number)) return null
  return Math.round(number <= 1 ? number * 100 : number)
}

export function toPercent(value) {
  if (value == null || value === '') return null
  const number = Number(value)
  return Number.isNaN(number) ? null : Math.round(number)
}

export function humanise(value) {
  if (value == null || value === '') return ''
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  const text = String(value).replace(/_/g, ' ').trim()
  return text.charAt(0).toUpperCase() + text.slice(1)
}

export function normaliseSectionRef(ref) {
  return String(ref ?? '')
    .trim()
    .replace(/^section\s+/i, '')
    .replace(/\.+$/, '')
    .trim()
    .toLowerCase()
}

export function sectionLabel(ref) {
  const text = String(ref ?? '').trim().replace(/\.+$/, '')
  if (!text) return ''
  return /^[\d.]+[a-z]?$/i.test(text) ? `Section ${text}` : text
}

export function mergeClauses(primary, reference) {
  const byRef = new Map()
  for (const clause of Array.isArray(reference) ? reference : []) {
    const key = normaliseSectionRef(clause?.section_ref)
    if (key && !byRef.has(key)) byRef.set(key, clause)
  }
  return (Array.isArray(primary) ? primary : [])
    .filter((clause) => clause && typeof clause === 'object')
    .map((clause) => {
      const match = byRef.get(normaliseSectionRef(clause.section_ref)) || {}
      const merged = { ...match }
      for (const [key, value] of Object.entries(clause)) {
        if (value != null && value !== '') merged[key] = value
      }
      return merged
    })
}

export function isExclusion(clause) {
  return /exclu/i.test(String(clause?.chunk_type || ''))
}

export function formatStepTime(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString('en-AU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

export function formatDateTime(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString('en-AU', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export function imageMatchCloseness(distance) {
  const value = Number(distance)
  return distance != null && !Number.isNaN(value) && value <= 5 ? 'Near-identical image' : 'Possible match'
}
