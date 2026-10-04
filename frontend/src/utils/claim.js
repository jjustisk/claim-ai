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

export function errorText(err, fallback) {
  const detail = err?.detail
  if (typeof detail === 'string' && detail) return detail
  if (Array.isArray(detail)) {
    return detail.map((item) => item?.msg || String(item)).join(' ')
  }
  return fallback
}
