export function formatDate(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 10)
  return date.toLocaleDateString('en-AU', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

export function formatMoney(value, { spaced = false } = {}) {
  if (value == null || value === '') return '—'
  const amount = Number(value)
  if (Number.isNaN(amount)) return '—'
  const formatted = amount.toLocaleString('en-AU', { maximumFractionDigits: 0 })
  return spaced ? `$ ${formatted}` : `$${formatted}`
}

export function confidencePercent(score) {
  if (score == null || score === '') return null
  const value = Number(score)
  if (Number.isNaN(value)) return null
  return value <= 1 ? Math.round(value * 100) : Math.round(value)
}

const STATUS = {
  submitted: { label: 'Submitted', tone: 'amber' },
  under_review: { label: 'Under review', tone: 'blue' },
  approved: { label: 'Approved', tone: 'green' },
  rejected: { label: 'Declined', tone: 'red' },
  closed: { label: 'Closed', tone: 'slate' },
  draft: { label: 'Draft', tone: 'slate' },
}

export function statusMeta(status) {
  return STATUS[status] || { label: status || 'Unknown', tone: 'slate' }
}

export function urgency(claim) {
  const fraud = Number(claim?.fraud_risk_score || 0)
  if (fraud >= 0.3) return 'High'
  if (fraud > 0) return 'Medium'
  const priority = Number(claim?.priority_level || 0)
  if (priority >= 3) return 'High'
  if (priority >= 2) return 'Medium'
  return 'Low'
}

const DAMAGE_LABELS = {
  storm_hail_water: 'Flood',
  cyclone: 'Wind',
  burglary_theft: 'Theft',
  accidental: 'Accidental',
  glass: 'Glass',
  motor_burnout: 'Electrical',
  impact_malicious: 'Vandalism',
  fire: 'Fire',
  motor: 'Motor',
  property: 'Property',
  water_damage: 'Flood',
  theft: 'Theft',
  damage: 'Damage',
  other: 'Other',
}

export function damageLabel(claim) {
  const type = claim?.claim_type || claim?.insurance_type
  if (type && DAMAGE_LABELS[type]) return DAMAGE_LABELS[type]
  const coverage = String(claim?.coverage_type || '')
  if (/flood|storm|water/i.test(coverage)) return 'Flood'
  if (/fire/i.test(coverage)) return 'Fire'
  if (/motor|vehicle/i.test(coverage)) return 'Motor'
  if (/content/i.test(coverage)) return 'Contents'
  if (/home|building|property/i.test(coverage)) return 'Property'
  return coverage.split(' - ').pop()?.trim() || 'Claim'
}

export function isMotorPolicy(policy) {
  const text = String(policy?.coverage_type || '').toLowerCase()
  return text.includes('motor') || text.includes('vehicle')
}

export function aiBadge(decision) {
  const value = String(decision || '').toLowerCase()
  if (value === 'covered' || value.includes('approv')) return { label: 'Recommend approve', tone: 'green' }
  if (value === 'excluded' || value.includes('reject')) return { label: 'Recommend decline', tone: 'red' }
  if (!value) return null
  return { label: 'Manual review', tone: 'amber' }
}

const STATUS_MESSAGES = {
  0: 'Unable to reach the service. Check your connection and try again.',
  400: 'The request could not be processed. Please check your details and try again.',
  401: 'Your session has expired. Please sign in again.',
  403: 'You do not have permission to perform this action.',
  404: 'The requested item could not be found.',
  408: 'The request timed out. Please try again.',
  413: 'The upload is too large. Please use smaller files.',
  422: 'Some details could not be validated. Please review and try again.',
  429: 'Too many attempts. Please wait a moment and try again.',
  500: 'Something went wrong on our side. Please try again shortly.',
  502: 'The service is temporarily unavailable. Please try again shortly.',
  503: 'The service is temporarily unavailable. Please try again shortly.',
  504: 'The service is still starting. Please wait a moment and try again.',
}

const INTERNAL_DETAIL = /traceback|exception:|error:|file ".*", line |stack|sqlalchemy|psycopg|internal server|nginx|<!doctype|<html|<head|<body|<pre/i

function looksLikeMarkup(text) {
  return /<\/?[a-z][\s\S]*>/i.test(text) || /<!DOCTYPE/i.test(text)
}

function cleanValidationMsg(msg) {
  if (!msg || typeof msg !== 'string') return ''
  // pydantic-style "Value error, ..." → keep the human part when present
  return msg.replace(/^Value error,\s*/i, '').replace(/\s+/g, ' ').trim()
}

function isSafePublicDetail(text) {
  if (!text || typeof text !== 'string') return false
  const trimmed = text.trim()
  if (!trimmed || trimmed.length > 240) return false
  if (looksLikeMarkup(trimmed) || INTERNAL_DETAIL.test(trimmed)) return false
  return true
}

/** User-facing API error copy — never returns HTML or stack traces. */
export function errorText(err, fallback = 'Something went wrong. Please try again.') {
  const status = Number(err?.status) || 0
  const statusFallback = STATUS_MESSAGES[status] || fallback
  const detail = err?.detail

  if (typeof detail === 'string' && isSafePublicDetail(detail)) {
    return detail.trim()
  }

  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => cleanValidationMsg(item?.msg || ''))
      .filter((msg) => isSafePublicDetail(msg))
    if (parts.length) return parts.slice(0, 3).join(' ')
  }

  return statusFallback
}
