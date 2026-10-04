<script setup>
import { computed, watch } from 'vue'
import YesNoField from './YesNoField.vue'
import PersonBlock from './PersonBlock.vue'
import OtherPartyBlock from './OtherPartyBlock.vue'
import { filteredPolicies } from '../../utils/claimFormData'

const props = defineProps({
  form: { type: Object, required: true },
  policies: { type: Array, default: () => [] },
  options: { type: Object, default: () => ({}) },
  files: { type: Array, default: () => [] },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['update:files'])

const insuranceTypes = [
  { value: 'motor', label: 'Motor vehicle', help: 'Includes vehicle, driver, and other-party details.' },
  { value: 'property', label: 'Property', help: 'Includes building damage and contents details.' },
]

const isMotor = computed(() => props.form.insurance_type === 'motor')
const isProperty = computed(() => props.form.insurance_type === 'property')
const visiblePolicies = computed(() => filteredPolicies(props.policies, props.form.insurance_type))
const showReporter = computed(() => props.form.is_policyholder === 'no')
const showWitnesses = computed(() => props.form.witnesses_present === 'yes')
const showPolice = computed(() => props.form.police_involved === 'yes')
const showGst = computed(() => props.form.gst_registered === 'yes')
const showDriver = computed(() => props.form.vehicle_driven === 'yes')
const showAlcohol = computed(() => props.form.alcohol_or_drugs === 'yes')
const showTowed = computed(() => props.form.vehicle_towed === 'yes')
const showBuilding = computed(() => props.form.building_damaged === 'yes')
const showContents = computed(() => props.form.contents_affected === 'yes')
const showPropertyOther = computed(() => props.form.other_person_responsible === 'yes')
const showMotorOther = computed(
  () => props.form.other_vehicle_involved === 'yes' || props.form.other_property_damaged === 'yes',
)
const showIncidentLocation = computed(
  () => isMotor.value || (isProperty.value && props.form.incident_at_insured_address === 'no'),
)
const showMotorCharges = computed(() => isMotor.value && props.form.police_involved === 'yes')
const showChargesDetails = computed(() => props.form.charges_laid === 'yes')
const showFineDefaults = computed(() => props.form.licence_cancelled_3yrs === 'yes')
const showReporterReason = computed(() => props.form.relationship_to_holder === 'Other')
const relationships = computed(() =>
  isMotor.value ? props.options.motor_relationships || [] : props.options.property_relationships || [],
)

watch(
  () => props.form.policy_id,
  (id) => {
    const policy = props.policies.find((p) => String(p.policy_id) === String(id))
    props.form.policy_number = policy?.policy_number || ''
  },
)

watch(
  () => [props.form.holder_first_name, props.form.holder_last_name],
  () => {
    if (!props.form._declarationTouched) {
      props.form.declaration_name = [props.form.holder_first_name, props.form.holder_last_name].filter(Boolean).join(' ')
    }
  },
)

function onFiles(list) {
  emit('update:files', [...props.files, ...list])
}

function toggleArray(key, value, checked) {
  const list = [...(props.form[key] || [])]
  const i = list.indexOf(value)
  if (checked && i === -1) list.push(value)
  if (!checked && i !== -1) list.splice(i, 1)
  props.form[key] = list
}
</script>

<template>
  <div class="space-y-8" :class="{ 'pointer-events-none opacity-60': disabled }">
    <section>
      <h2 class="text-base font-bold text-slate-900">1. Claim type</h2>
      <p class="mt-1 text-sm text-slate-500">Select motor vehicle or property. The form will show the fields required for that claim type.</p>
      <div class="mt-4 grid gap-3 sm:grid-cols-2">
        <label
          v-for="type in insuranceTypes"
          :key="type.value"
          class="cursor-pointer rounded-xl border p-4"
          :class="form.insurance_type === type.value ? 'border-blue-600 bg-blue-50/40' : 'border-slate-200'"
        >
          <span class="flex items-center gap-2 font-semibold">
            <input v-model="form.insurance_type" type="radio" name="insurance_type" :value="type.value" required />
            {{ type.label }}
          </span>
          <span class="mt-1 block text-xs text-slate-500">{{ type.help }}</span>
        </label>
      </div>
    </section>

    <template v-if="form.insurance_type">
      <section>
        <h2 class="text-base font-bold">2. Policy details</h2>
        <div class="mt-3 grid gap-4 sm:grid-cols-2">
          <label class="block text-sm">
            <span class="mb-1 block font-medium">Policy</span>
            <select v-model="form.policy_id" class="field" required>
              <option value="">Select a policy</option>
              <option v-for="p in visiblePolicies" :key="p.policy_id" :value="String(p.policy_id)">
                {{ p.policy_number }} — {{ p.coverage_type }}
              </option>
            </select>
          </label>
          <label class="block text-sm">
            <span class="mb-1 block font-medium">Policy number</span>
            <input v-model="form.policy_number" class="field bg-slate-50" readonly />
          </label>
        </div>
      </section>

      <section>
        <h2 class="text-base font-bold">3. Policy holder details</h2>
        <div class="mt-3 grid gap-4 sm:grid-cols-2">
          <label class="block text-sm">
            <span class="mb-1 block font-medium">Title</span>
            <select v-model="form.holder_title" class="field" required>
              <option value="">Select</option>
              <option v-for="t in options.titles || []" :key="t.value" :value="t.value">{{ t.label }}</option>
            </select>
          </label>
          <label class="block text-sm">
            <span class="mb-1 block font-medium">First name</span>
            <input v-model="form.holder_first_name" class="field" required />
          </label>
          <label class="block text-sm">
            <span class="mb-1 block font-medium">Last name</span>
            <input v-model="form.holder_last_name" class="field" required />
          </label>
          <label class="block text-sm sm:col-span-2">
            <span class="mb-1 block font-medium">Company name</span>
            <input v-model="form.holder_company" class="field" />
          </label>
          <label class="block text-sm">
            <span class="mb-1 block font-medium">Street number</span>
            <input v-model="form.holder_street_number" class="field" required />
          </label>
          <label class="block text-sm">
            <span class="mb-1 block font-medium">Street name</span>
            <input v-model="form.holder_street_name" class="field" required />
          </label>
          <label class="block text-sm">
            <span class="mb-1 block font-medium">Suburb</span>
            <input v-model="form.holder_suburb" class="field" required />
          </label>
          <label class="block text-sm">
            <span class="mb-1 block font-medium">State</span>
            <select v-model="form.holder_state" class="field" required>
              <option value="">Select</option>
              <option v-for="s in options.states || []" :key="s.value" :value="s.value">{{ s.label }}</option>
            </select>
          </label>
          <label class="block text-sm">
            <span class="mb-1 block font-medium">Postcode</span>
            <input v-model="form.holder_postcode" class="field" required />
          </label>
          <label class="block text-sm">
            <span class="mb-1 block font-medium">Preferred contact</span>
            <select v-model="form.preferred_contact_method" class="field" required>
              <option value="">Select</option>
              <option v-for="m in options.contact_methods || []" :key="m.value" :value="m.value">{{ m.label }}</option>
            </select>
          </label>
          <label class="block text-sm">
            <span class="mb-1 block font-medium">Email</span>
            <input v-model="form.holder_email" type="email" class="field" required />
          </label>
          <label class="block text-sm">
            <span class="mb-1 block font-medium">Phone</span>
            <input v-model="form.holder_phone" class="field" required />
          </label>
          <label class="block text-sm">
            <span class="mb-1 block font-medium">Alternate phone</span>
            <input v-model="form.alternate_phone" class="field" />
          </label>
        </div>
        <div v-if="isProperty" class="mt-4">
          <p class="mb-1 text-sm font-medium">Is your postal address the same as your insured property address?</p>
          <YesNoField v-model="form.postal_same_as_insured" name="postal_same_as_insured" />
        </div>
      </section>

      <section>
        <h2 class="text-base font-bold">4. Policy holder GST details</h2>
        <p class="mb-2 text-sm font-medium">Are you registered for GST?</p>
        <YesNoField v-model="form.gst_registered" name="gst_registered" required />
        <div v-if="showGst" class="mt-3 grid gap-4 sm:grid-cols-2">
          <label class="block text-sm">
            <span class="mb-1 block font-medium">ABN</span>
            <input v-model="form.abn" class="field" required />
          </label>
          <label class="block text-sm">
            <span class="mb-1 block font-medium">GST input tax credit (%)</span>
            <input v-model="form.gst_itc_percent" class="field" required />
          </label>
        </div>
      </section>

      <section>
        <h2 class="text-base font-bold">5. EFT details</h2>
        <p class="text-sm text-slate-500">Optional. Used if a settlement payment is made to you.</p>
        <div class="mt-3 grid gap-4 sm:grid-cols-2">
          <label class="block text-sm sm:col-span-2">
            <span class="mb-1 block font-medium">Account name</span>
            <input v-model="form.eft_account_name" class="field" />
          </label>
          <label class="block text-sm">
            <span class="mb-1 block font-medium">BSB</span>
            <input v-model="form.eft_bsb" class="field" />
          </label>
          <label class="block text-sm">
            <span class="mb-1 block font-medium">Account number</span>
            <input v-model="form.eft_account_number" class="field" />
          </label>
        </div>
      </section>

      <section>
        <h2 class="text-base font-bold">6. Incident details</h2>
        <div class="mt-3 grid gap-4 sm:grid-cols-2">
          <label class="block text-sm">
            <span class="mb-1 block font-medium">Date the incident occurred</span>
            <input v-model="form.incident_date" type="date" class="field" required />
          </label>
          <label class="block text-sm">
            <span class="mb-1 block font-medium">Approximate time</span>
            <input v-model="form.incident_time" type="time" class="field" required />
          </label>
        </div>
        <label v-if="isProperty" class="mt-4 block text-sm">
          <span class="mb-1 block font-medium">What type of claim are you making?</span>
          <select v-model="form.property_claim_type" class="field" required>
            <option value="">Select</option>
            <option v-for="t in options.property_claim_types || []" :key="t.value" :value="t.value">{{ t.label }}</option>
          </select>
        </label>
        <label class="mt-4 block text-sm">
          <span class="mb-1 block font-medium">Incident description</span>
          <textarea v-model="form.incident_description" rows="4" class="field" required placeholder="Provide a clear description of the incident…" />
        </label>
        <div v-if="isProperty" class="mt-3">
          <p class="mb-1 text-sm font-medium">Did the incident occur at the insured property address?</p>
          <YesNoField v-model="form.incident_at_insured_address" name="incident_at_insured_address" />
        </div>
        <div v-if="showIncidentLocation" class="mt-4">
          <h3 class="mb-2 text-sm font-semibold">Where did the incident occur?</h3>
          <div class="grid gap-4 sm:grid-cols-2">
            <label class="block text-sm">
              <span class="mb-1 block font-medium">Street name</span>
              <input v-model="form.incident_street" class="field" :required="isMotor" />
            </label>
            <label v-if="isMotor" class="block text-sm">
              <span class="mb-1 block font-medium">Nearest cross street</span>
              <input v-model="form.incident_cross_street" class="field" />
            </label>
            <label class="block text-sm">
              <span class="mb-1 block font-medium">Suburb</span>
              <input v-model="form.incident_suburb" class="field" :required="isMotor" />
            </label>
            <label class="block text-sm">
              <span class="mb-1 block font-medium">State</span>
              <select v-model="form.incident_state" class="field" :required="isMotor">
                <option value="">Select</option>
                <option v-for="s in options.states || []" :key="s.value" :value="s.value">{{ s.label }}</option>
              </select>
            </label>
            <label class="block text-sm">
              <span class="mb-1 block font-medium">Postcode</span>
              <input v-model="form.incident_postcode" class="field" :required="isMotor" />
            </label>
          </div>
        </div>
      </section>

      <section>
        <h2 class="text-base font-bold">7. Your details</h2>
        <p class="mb-2 text-sm font-medium">Are you our policy holder?</p>
        <YesNoField v-model="form.is_policyholder" name="is_policyholder" required />
        <div v-if="showReporter" class="mt-4 space-y-3">
          <label class="block text-sm">
            <span class="mb-1 block font-medium">Relationship to policy holder</span>
            <select v-model="form.relationship_to_holder" class="field" required>
              <option value="">Select</option>
              <option v-for="r in relationships" :key="r.value" :value="r.value">{{ r.label }}</option>
            </select>
          </label>
          <label v-if="showReporterReason" class="block text-sm">
            <span class="mb-1 block font-medium">Why are you reporting the claim?</span>
            <textarea v-model="form.reporter_reason" rows="2" class="field" />
          </label>
        </div>
      </section>

      <section>
        <h2 class="text-base font-bold">8. Witnesses</h2>
        <p class="mb-2 text-sm font-medium">Were there any witnesses?</p>
        <YesNoField v-model="form.witnesses_present" name="witnesses_present" required />
        <div v-if="showWitnesses" class="mt-4 space-y-6">
          <PersonBlock title="Witness 1" prefix="witness_1" :form="form" :titles="options.titles" :states="options.states" required />
          <PersonBlock title="Witness 2" prefix="witness_2" :form="form" :titles="options.titles" :states="options.states" />
        </div>
        <div v-if="isMotor" class="mt-4">
          <p class="mb-2 text-sm font-medium">Was any person injured?</p>
          <YesNoField v-model="form.person_injured" name="person_injured" />
        </div>
      </section>

      <section>
        <h2 class="text-base font-bold">9. Police</h2>
        <p class="mb-2 text-sm font-medium">Has a police report been made?</p>
        <YesNoField v-model="form.police_involved" name="police_involved" required />
        <div v-if="showPolice" class="mt-3 grid gap-4 sm:grid-cols-2">
          <label class="block text-sm">
            <span class="mb-1 block font-medium">Report number</span>
            <input v-model="form.police_report_number" class="field" />
          </label>
          <label class="block text-sm">
            <span class="mb-1 block font-medium">Date reported</span>
            <input v-model="form.police_reported_date" type="date" class="field" />
          </label>
        </div>
        <div v-if="showMotorCharges" class="mt-3">
          <p class="mb-2 text-sm font-medium">Were any charges laid or further action indicated?</p>
          <YesNoField v-model="form.charges_laid" name="charges_laid" />
          <label v-if="showChargesDetails" class="mt-3 block text-sm">
            <span class="mb-1 block font-medium">Details</span>
            <textarea v-model="form.charges_details" rows="2" class="field" />
          </label>
        </div>
      </section>

      <section v-if="isMotor" class="space-y-6">
        <div>
          <h2 class="text-base font-bold">10. Driver details</h2>
          <p class="mb-2 text-sm font-medium">Was the insured vehicle being driven?</p>
          <YesNoField v-model="form.vehicle_driven" name="vehicle_driven" />
          <div v-if="showDriver" class="mt-4 grid gap-4 sm:grid-cols-2">
            <div class="sm:col-span-2">
              <p class="mb-2 text-sm font-medium">Was the policy holder driving?</p>
              <YesNoField v-model="form.policyholder_was_driver" name="policyholder_was_driver" />
            </div>
            <label class="block text-sm"><span class="mb-1 block font-medium">Driver first name</span><input v-model="form.driver_first_name" class="field" /></label>
            <label class="block text-sm"><span class="mb-1 block font-medium">Driver last name</span><input v-model="form.driver_last_name" class="field" /></label>
            <label class="block text-sm"><span class="mb-1 block font-medium">Licence number</span><input v-model="form.driver_licence_number" class="field" /></label>
            <label class="block text-sm"><span class="mb-1 block font-medium">Years held</span><input v-model="form.driver_licence_years" class="field" /></label>
            <div class="sm:col-span-2">
              <p class="mb-2 text-sm font-medium">Alcohol or drugs involved?</p>
              <YesNoField v-model="form.alcohol_or_drugs" name="alcohol_or_drugs" />
              <textarea v-if="showAlcohol" v-model="form.alcohol_details" rows="2" class="field mt-2" placeholder="Details..." />
            </div>
          </div>
        </div>
        <div>
          <h2 class="text-base font-bold">11. Vehicle details</h2>
          <div class="mt-3 grid gap-4 sm:grid-cols-2">
            <label class="block text-sm"><span class="mb-1 block font-medium">Registration</span><input v-model="form.vehicle_registration" class="field" required /></label>
            <label class="block text-sm">
              <span class="mb-1 block font-medium">Vehicle type</span>
              <select v-model="form.vehicle_type" class="field" required>
                <option value="">Select</option>
                <option v-for="t in options.vehicle_types || []" :key="t.value" :value="t.value">{{ t.label }}</option>
              </select>
            </label>
            <label class="block text-sm"><span class="mb-1 block font-medium">Year</span><input v-model="form.vehicle_year" class="field" required /></label>
            <label class="block text-sm"><span class="mb-1 block font-medium">Make</span><input v-model="form.vehicle_make" class="field" required /></label>
            <label class="block text-sm sm:col-span-2"><span class="mb-1 block font-medium">Model</span><input v-model="form.vehicle_model" class="field" /></label>
          </div>
          <div class="mt-3">
            <p class="mb-2 text-sm font-medium">Vehicle damage areas</p>
            <div class="grid gap-2 sm:grid-cols-2">
              <label v-for="area in options.vehicle_damage_areas || []" :key="area.value" class="flex items-center gap-2 text-sm">
                <input type="checkbox" :checked="(form.vehicle_damage || []).includes(area.value)" @change="toggleArray('vehicle_damage', area.value, $event.target.checked)" />
                {{ area.label }}
              </label>
            </div>
          </div>
          <div class="mt-3 space-y-3">
            <div><p class="mb-2 text-sm font-medium">Vehicle towed?</p><YesNoField v-model="form.vehicle_towed" name="vehicle_towed" /></div>
            <label v-if="showTowed" class="block text-sm"><span class="mb-1 block font-medium">Where is the vehicle now?</span><input v-model="form.vehicle_now_location" class="field" /></label>
            <div><p class="mb-2 text-sm font-medium">Airbags deployed?</p><YesNoField v-model="form.airbags_deployed" name="airbags_deployed" /></div>
            <div><p class="mb-2 text-sm font-medium">Travelling over 40 km/h?</p><YesNoField v-model="form.speed_over_40" name="speed_over_40" /></div>
          </div>
        </div>
        <div>
          <h2 class="text-base font-bold">12. Other persons</h2>
          <div class="space-y-2">
            <div><p class="mb-2 text-sm font-medium">Another vehicle involved?</p><YesNoField v-model="form.other_vehicle_involved" name="other_vehicle_involved" /></div>
            <div><p class="mb-2 text-sm font-medium">Other property damaged?</p><YesNoField v-model="form.other_property_damaged" name="other_property_damaged" /></div>
          </div>
          <div v-if="showMotorOther" class="mt-4 space-y-4">
            <OtherPartyBlock :index="1" :form="form" include-vehicle :titles="options.titles" :states="options.states" :vehicle-types="options.vehicle_types" :damage-areas="options.vehicle_damage_areas" />
            <OtherPartyBlock :index="2" :form="form" include-vehicle :titles="options.titles" :states="options.states" :vehicle-types="options.vehicle_types" :damage-areas="options.vehicle_damage_areas" />
          </div>
        </div>
        <div>
          <h2 class="text-base font-bold">13. Disclosure</h2>
          <div class="space-y-3">
            <div><p class="mb-2 text-sm font-medium">Licence cancelled in past 3 years?</p><YesNoField v-model="form.licence_cancelled_3yrs" name="licence_cancelled_3yrs" /></div>
            <div v-if="showFineDefaults"><p class="mb-2 text-sm font-medium">Due to fine defaults?</p><YesNoField v-model="form.cancelled_fine_defaults" name="cancelled_fine_defaults" /></div>
            <div><p class="mb-2 text-sm font-medium">Convicted alcohol/drug or dishonesty offences (3 years)?</p><YesNoField v-model="form.convicted_alcohol_crime_3yrs" name="convicted_alcohol_crime_3yrs" /></div>
            <div><p class="mb-2 text-sm font-medium">Insurance declined (5 years)?</p><YesNoField v-model="form.insurance_declined_5yrs" name="insurance_declined_5yrs" /></div>
          </div>
        </div>
      </section>

      <section v-if="isProperty" class="space-y-6">
        <div>
          <h2 class="text-base font-bold">10. Building damage</h2>
          <p class="mb-2 text-sm font-medium">Does the claim include building damage?</p>
          <YesNoField v-model="form.building_damaged" name="building_damaged" />
          <div v-if="showBuilding" class="mt-4 space-y-3">
            <div>
              <p class="mb-2 text-sm font-medium">Damage areas</p>
              <div class="grid gap-2 sm:grid-cols-2">
                <label v-for="area in options.building_areas || []" :key="area.value" class="flex items-center gap-2 text-sm">
                  <input type="checkbox" :checked="(form.building_area || []).includes(area.value)" @change="toggleArray('building_area', area.value, $event.target.checked)" />
                  {{ area.label }}
                </label>
              </div>
            </div>
            <label class="block text-sm"><span class="mb-1 block font-medium">Carpet damage</span><textarea v-model="form.damage_carpet" rows="2" class="field" /></label>
            <label class="block text-sm"><span class="mb-1 block font-medium">Ceiling damage</span><textarea v-model="form.damage_ceiling" rows="2" class="field" /></label>
            <label class="block text-sm"><span class="mb-1 block font-medium">Floor damage</span><textarea v-model="form.damage_floor" rows="2" class="field" /></label>
            <label class="block text-sm"><span class="mb-1 block font-medium">Wall damage</span><textarea v-model="form.damage_wall" rows="2" class="field" /></label>
            <label class="block text-sm"><span class="mb-1 block font-medium">Windows damage</span><textarea v-model="form.damage_windows" rows="2" class="field" /></label>
            <label class="block text-sm"><span class="mb-1 block font-medium">Other damage</span><textarea v-model="form.damage_other" rows="2" class="field" /></label>
            <div><p class="mb-2 text-sm font-medium">Property secure?</p><YesNoField v-model="form.property_secure" name="property_secure" /></div>
            <div><p class="mb-2 text-sm font-medium">Repairs done?</p><YesNoField v-model="form.repairs_done" name="repairs_done" /></div>
            <div><p class="mb-2 text-sm font-medium">Property habitable?</p><YesNoField v-model="form.property_habitable" name="property_habitable" /></div>
          </div>
        </div>
        <div>
          <h2 class="text-base font-bold">11. Contents</h2>
          <p class="mb-2 text-sm font-medium">Contents affected?</p>
          <YesNoField v-model="form.contents_affected" name="contents_affected" />
          <div v-if="showContents" class="mt-4 overflow-x-auto">
            <table class="w-full min-w-[520px] text-left text-sm">
              <thead><tr class="border-b text-slate-500"><th class="py-2">Item</th><th>Description</th><th>Value</th></tr></thead>
              <tbody>
                <tr v-for="cat in options.contents_categories || []" :key="cat.value" class="border-b border-slate-100">
                  <td class="py-2 pr-2">{{ cat.label }}</td>
                  <td class="py-2 pr-2"><input v-model="form[`contents_${cat.value}_description`]" class="field" /></td>
                  <td class="py-2"><input v-model="form[`contents_${cat.value}_value`]" class="field" placeholder="$0.00" /></td>
                </tr>
              </tbody>
            </table>
            <label class="mt-3 block text-sm">
              <span class="mb-1 block font-medium">Total estimated replacement value</span>
              <input v-model="form.contents_total_value" class="field max-w-xs" />
            </label>
          </div>
        </div>
        <div>
          <h2 class="text-base font-bold">12. Other persons</h2>
          <p class="mb-2 text-sm font-medium">Was another person responsible?</p>
          <YesNoField v-model="form.other_person_responsible" name="other_person_responsible" />
          <div v-if="showPropertyOther" class="mt-4 space-y-4">
            <OtherPartyBlock :index="1" :form="form" :titles="options.titles" :states="options.states" />
            <OtherPartyBlock :index="2" :form="form" :titles="options.titles" :states="options.states" />
          </div>
        </div>
        <div>
          <h2 class="text-base font-bold">13. Disclosure</h2>
          <div class="space-y-3">
            <div><p class="mb-2 text-sm font-medium">Convicted of crime (5 years)?</p><YesNoField v-model="form.convicted_crime_5yrs" name="convicted_crime_5yrs" /></div>
            <div><p class="mb-2 text-sm font-medium">Insurance declined (5 years)?</p><YesNoField v-model="form.insurance_declined_5yrs" name="insurance_declined_5yrs" required /></div>
          </div>
        </div>
      </section>

      <section>
        <h2 class="text-base font-bold">14. Supporting documents</h2>
        <label class="mt-3 grid cursor-pointer place-items-center rounded-xl border border-dashed border-slate-300 bg-slate-50 px-4 py-8 text-center">
          <input class="hidden" type="file" multiple accept="image/jpeg,image/png,application/pdf" @change="onFiles($event.target.files)" />
          <span class="text-sm text-slate-600">Drag and drop files here, or browse to select</span>
          <span class="text-xs text-slate-400">JPEG, PNG or PDF. Max 25 MB per file.</span>
        </label>
        <ul v-if="files.length" class="mt-2 space-y-1 text-sm text-slate-600">
          <li v-for="(file, i) in files" :key="`${file.name}-${i}`">{{ file.name }}</li>
        </ul>
        <label class="mt-4 block text-sm">
          <span class="mb-1 block font-medium">Additional comments</span>
          <textarea v-model="form.additional_comments" rows="3" class="field" />
        </label>
      </section>

      <section>
        <h2 class="text-base font-bold">15. Declaration</h2>
        <p class="mt-1 text-sm text-slate-500">I certify that the information given is truthful, accurate and complete.</p>
        <label class="mt-3 flex items-start gap-2 text-sm">
          <input v-model="form.declaration_accepted" type="checkbox" required />
          <span>I confirm the declaration above.</span>
        </label>
        <div class="mt-3 grid gap-4 sm:grid-cols-2">
          <label class="block text-sm">
            <span class="mb-1 block font-medium">Signature / name</span>
            <input v-model="form.declaration_name" class="field" @input="form._declarationTouched = true" />
          </label>
          <label class="block text-sm">
            <span class="mb-1 block font-medium">Position held (if signing for someone else)</span>
            <input v-model="form.declaration_position" class="field" />
          </label>
          <label class="block text-sm">
            <span class="mb-1 block font-medium">Date</span>
            <input v-model="form.declaration_date" type="date" class="field" />
          </label>
        </div>
      </section>
    </template>
  </div>
</template>
