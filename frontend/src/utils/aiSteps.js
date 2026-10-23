import { markRaw } from 'vue'
import { AlertTriangle, CheckCircle, Clock, Eye, Lock, Scale, Search, ShieldCheck, Sparkles, XCircle } from 'lucide-vue-next'

const NEUTRAL_ICON = { iconBg: 'bg-gray-100', iconColor: 'text-gray-500' }

export const AI_STEPS = [
  { key: 'pii_reduction', label: 'Privacy screening', icon: markRaw(Lock), ...NEUTRAL_ICON },
  { key: 'damage_description', label: 'AI damage description & analysis', icon: markRaw(Search), ...NEUTRAL_ICON },
  { key: 'consistency_check', label: 'Statement vs photo consistency check', icon: markRaw(Eye), ...NEUTRAL_ICON },
  { key: 'fraud_check', label: 'Fraud & duplicate image check', icon: markRaw(ShieldCheck), ...NEUTRAL_ICON },
  { key: 'policy_match', label: 'Policy clause matching', icon: markRaw(Scale), ...NEUTRAL_ICON },
  { key: 'decision', label: 'AI recommendation & confidence', icon: markRaw(Sparkles), iconBg: 'bg-violet-100', iconColor: 'text-violet-500' },
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
  pass: { label: 'Passed', dotBg: 'bg-emerald-100', icon: markRaw(CheckCircle), iconColor: 'text-emerald-600', subtitleClass: 'text-gray-500', subtitleIcon: null },
  flag: { label: 'Flagged for assessor awareness', dotBg: 'bg-amber-100', icon: markRaw(AlertTriangle), iconColor: 'text-amber-600', subtitleClass: 'text-amber-600', subtitleIcon: markRaw(AlertTriangle) },
  fail: { label: 'Failed', dotBg: 'bg-red-100', icon: markRaw(XCircle), iconColor: 'text-red-600', subtitleClass: 'text-red-600', subtitleIcon: markRaw(XCircle) },
  pending: { label: 'Not run yet', dotBg: 'bg-gray-100', icon: markRaw(Clock), iconColor: 'text-gray-400', subtitleClass: 'text-gray-500', subtitleIcon: null },
  skipped: { label: 'Skipped', dotBg: 'bg-gray-100', icon: markRaw(Clock), iconColor: 'text-gray-400', subtitleClass: 'text-gray-500', subtitleIcon: null },
}

export function stepStatusMeta(status) {
  return STEP_STATUS[status] || STEP_STATUS.pending
}

const AUDIT_LABELS = {
  pii_reduction: 'Privacy screening',
  damage_description: 'AI damage description & analysis',
  consistency_check: 'Statement vs photo consistency check',
  fraud_check: 'Fraud & duplicate image check',
  policy_match: 'Policy clause matching',
  retrieval: 'Policy clause matching',
  generation: 'AI recommendation & confidence',
  decision: 'AI recommendation & confidence',
}

export function auditActionLabel(actionType) {
  return AUDIT_LABELS[actionType] || humanise(actionType) || 'Pipeline event'
}

const RECOMMENDATIONS = {
  approve: { label: 'APPROVE', pill: 'bg-emerald-50 text-emerald-700 border-emerald-200', box: 'bg-emerald-50 border-emerald-200', text: 'text-emerald-700' },
  reject: { label: 'REJECT', pill: 'bg-red-50 text-red-700 border-red-200', box: 'bg-red-50 border-red-200', text: 'text-red-700' },
  escalate: { label: 'ESCALATE', pill: 'bg-amber-50 text-amber-700 border-amber-200', box: 'bg-amber-50 border-amber-200', text: 'text-amber-700' },
}

export function recommendationMeta(decision) {
  const value = String(decision || '').toLowerCase()
  if (!value || value === 'pending') return null
  if (value === 'partial') return { ...RECOMMENDATIONS.approve, label: 'APPROVE (PARTIAL)' }
  if (value === 'covered' || value.includes('approv')) return RECOMMENDATIONS.approve
  if (value === 'excluded' || value.includes('reject') || value.includes('declin')) return RECOMMENDATIONS.reject
  return RECOMMENDATIONS.escalate
}

const DECISION_LABELS = {
  covered: 'Covered',
  partial: 'Partially covered',
  excluded: 'Excluded — not covered',
  refer_to_assessor: 'Referred to assessor',
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
