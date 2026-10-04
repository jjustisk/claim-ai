import { isMotorPolicy } from './claim'

export function policyKind(policy) {
  return isMotorPolicy(policy) ? 'motor' : 'property'
}

export function createEmptyForm(user) {
  const name = String(user?.name || '').trim()
  const [first, ...rest] = name.split(/\s+/)
  return {
    insurance_type: '',
    policy_id: '',
    policy_number: '',
    holder_title: '',
    holder_first_name: first || '',
    holder_last_name: rest.join(' ') || '',
    holder_company: '',
    holder_unit: '',
    holder_street_number: '',
    holder_street_name: '',
    holder_suburb: '',
    holder_state: '',
    holder_postcode: '',
    preferred_contact_method: '',
    holder_email: user?.email || '',
    holder_phone: user?.phone || '',
    alternate_phone: '',
    postal_same_as_insured: '',
    gst_registered: '',
    abn: '',
    gst_itc_percent: '',
    eft_account_name: '',
    eft_bsb: '',
    eft_account_number: '',
    incident_date: '',
    incident_time: '',
    property_claim_type: '',
    incident_description: '',
    incident_at_insured_address: '',
    incident_street: '',
    incident_cross_street: '',
    incident_suburb: '',
    incident_state: '',
    incident_postcode: '',
    is_policyholder: 'yes',
    relationship_to_holder: '',
    reporter_reason: '',
    broker_name: '',
    broker_phone: '',
    notify_policyholder: '',
    witnesses_present: '',
    police_involved: '',
    police_report_number: '',
    police_reported_date: '',
    charges_laid: '',
    charges_details: '',
    person_injured: '',
    vehicle_driven: '',
    policyholder_was_driver: '',
    driver_title: '',
    driver_first_name: '',
    driver_last_name: '',
    driver_dob: '',
    driver_phone: '',
    driver_email: '',
    driver_licence_number: '',
    driver_licence_years: '',
    driver_unit: '',
    driver_street_number: '',
    driver_street_name: '',
    driver_suburb: '',
    driver_state: '',
    driver_postcode: '',
    alcohol_or_drugs: '',
    alcohol_details: '',
    vehicle_registration: '',
    vehicle_type: '',
    vehicle_year: '',
    vehicle_make: '',
    vehicle_model: '',
    vehicle_damage: [],
    vehicle_towed: '',
    vehicle_now_location: '',
    airbags_deployed: '',
    speed_over_40: '',
    other_vehicle_involved: '',
    other_property_damaged: '',
    licence_cancelled_3yrs: '',
    cancelled_fine_defaults: '',
    convicted_alcohol_crime_3yrs: '',
    insurance_declined_5yrs: '',
    building_damaged: '',
    building_area: [],
    bathroom_rooms: '',
    bedroom_rooms: '',
    lounge_rooms: '',
    damage_carpet: '',
    damage_ceiling: '',
    damage_floor: '',
    damage_wall: '',
    damage_windows: '',
    damage_other: '',
    property_secure: '',
    repairs_done: '',
    property_habitable: '',
    contents_affected: '',
    contents_total_value: '',
    other_person_responsible: '',
    convicted_crime_5yrs: '',
    additional_comments: '',
    declaration_accepted: false,
    declaration_name: name,
    declaration_position: '',
    declaration_date: new Date().toISOString().slice(0, 10),
    witness_1_title: '',
    witness_1_first_name: '',
    witness_1_last_name: '',
    witness_1_unit: '',
    witness_1_street_number: '',
    witness_1_street_name: '',
    witness_1_suburb: '',
    witness_1_state: '',
    witness_1_postcode: '',
    witness_1_phone: '',
    witness_1_email: '',
    witness_2_title: '',
    witness_2_first_name: '',
    witness_2_last_name: '',
    witness_2_unit: '',
    witness_2_street_number: '',
    witness_2_street_name: '',
    witness_2_suburb: '',
    witness_2_state: '',
    witness_2_postcode: '',
    witness_2_phone: '',
    witness_2_email: '',
    other_1_title: '',
    other_1_first_name: '',
    other_1_last_name: '',
    other_1_company_name: '',
    other_1_unit: '',
    other_1_street_number: '',
    other_1_street_name: '',
    other_1_suburb: '',
    other_1_state: '',
    other_1_postcode: '',
    other_1_phone: '',
    other_1_email: '',
    other_1_insurance_company: '',
    other_1_insurance_policy_number: '',
    other_1_insurance_claim_number: '',
    other_1_licence_number: '',
    other_1_vehicle_registration: '',
    other_1_vehicle_type: '',
    other_1_vehicle_year: '',
    other_1_vehicle_make: '',
    other_1_vehicle_model: '',
    other_1_vehicle_damage: [],
    other_2_title: '',
    other_2_first_name: '',
    other_2_last_name: '',
    other_2_company_name: '',
    other_2_unit: '',
    other_2_street_number: '',
    other_2_street_name: '',
    other_2_suburb: '',
    other_2_state: '',
    other_2_postcode: '',
    other_2_phone: '',
    other_2_email: '',
    other_2_insurance_company: '',
    other_2_insurance_policy_number: '',
    other_2_insurance_claim_number: '',
    other_2_licence_number: '',
    other_2_vehicle_registration: '',
    other_2_vehicle_type: '',
    other_2_vehicle_year: '',
    other_2_vehicle_make: '',
    other_2_vehicle_model: '',
    other_2_vehicle_damage: [],
  }
}

function boolToYesNo(value) {
  if (value === true) return 'yes'
  if (value === false) return 'no'
  return value ?? ''
}

export function claimToForm(claim) {
  const base = createEmptyForm({
    name: claim.claimant_name || claim.holder_first_name,
    email: claim.claimant_email || claim.holder_email,
    phone: claim.claimant_phone || claim.holder_phone,
  })
  const merged = { ...base, ...claim }
  merged.insurance_type = claim.insurance_type || ''
  if (!merged.insurance_type && claim.claim_type === 'motor') merged.insurance_type = 'motor'
  if (!merged.insurance_type && claim.claim_type) merged.insurance_type = 'property'
  if (merged.insurance_type === 'property' && claim.claim_type && claim.claim_type !== 'property') {
    merged.property_claim_type = claim.claim_type
  }
  merged.policy_id = claim.policy_id != null ? String(claim.policy_id) : ''
  merged.policy_number = claim.policy_number || ''
  merged.is_policyholder = boolToYesNo(claim.is_policyholder) || merged.is_policyholder
  merged.witnesses_present = boolToYesNo(claim.witnesses_present)
  merged.police_involved = boolToYesNo(claim.police_involved)
  merged.gst_registered = boolToYesNo(claim.gst_registered)
  merged.declaration_accepted = !!claim.declaration_accepted
  merged.vehicle_damage = merged.vehicle_damage || []
  merged.building_area = merged.building_area || []
  merged.other_1_vehicle_damage = merged.other_1_vehicle_damage || []
  merged.other_2_vehicle_damage = merged.other_2_vehicle_damage || []
  if (claim.incident_date) merged.incident_date = String(claim.incident_date).slice(0, 10)
  if (claim.declaration_date) merged.declaration_date = String(claim.declaration_date).slice(0, 10)
  return merged
}

export function appendClaimFormData(form, formData, { intent, claimId, files, contentsCategories = [] }) {
  if (claimId) formData.append('claim_id', String(claimId))
  formData.append('intent', intent)

  const arrayKeys = ['vehicle_damage', 'building_area', 'other_1_vehicle_damage', 'other_2_vehicle_damage']
  const skip = new Set(['policy_number', 'declaration_accepted', '_declarationTouched', ...arrayKeys])

  for (const [key, value] of Object.entries(form)) {
    if (skip.has(key) || key.startsWith('contents_')) continue
    if (value === null || value === undefined || value === '') continue
    if (Array.isArray(value)) continue
    formData.append(key, String(value))
  }

  for (const key of arrayKeys) {
    for (const item of form[key] || []) formData.append(key, item)
  }

  for (const cat of contentsCategories) {
    const value = typeof cat === 'string' ? cat : cat.value
    const desc = form[`contents_${value}_description`]
    const amount = form[`contents_${value}_value`]
    if (desc) formData.append(`contents_${value}_description`, desc)
    if (amount) formData.append(`contents_${value}_value`, amount)
  }

  if (form.declaration_accepted) formData.append('declaration_accepted', 'yes')
  for (const file of files || []) formData.append('files', file)
}

export function filteredPolicies(policies, insuranceType) {
  if (!insuranceType) return policies
  return policies.filter((p) => policyKind(p) === insuranceType)
}
