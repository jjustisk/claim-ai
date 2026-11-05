<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { ArrowLeft } from 'lucide-vue-next'
import { api } from '../../api/client'
import { damageLabel, formatDate, formatMoney, statusMeta } from '../../utils/claim'
import { humanise } from '../../utils/aiSteps'

const props = defineProps({ id: { type: [String, Number], required: true } })

const claim = ref(null)
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    claim.value = await api.claimDetail(props.id)
  } catch {
    claim.value = null
    error.value = 'This claim could not be loaded. Please try again.'
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => props.id, load)

function show(value, kind) {
  if (value == null || value === '') return null
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (Array.isArray(value)) return value.length ? value.join(', ') : null
  if (kind === 'date') return formatDate(value)
  if (kind === 'money') return formatMoney(value)
  if (kind === 'word') return humanise(value)
  return String(value)
}

function join(...parts) {
  const text = parts.filter((part) => part != null && part !== '').join(' ').trim()
  return text || null
}

function address(c, prefix) {
  const street = join(c[`${prefix}unit`] && `Unit ${c[`${prefix}unit`]},`, c[`${prefix}street_number`], c[`${prefix}street_name`])
  const place = join(c[`${prefix}suburb`], c[`${prefix}state`], c[`${prefix}postcode`])
  return [street, place].filter(Boolean).join(', ') || null
}

function maskedAccount(value) {
  const text = String(value || '')
  return text ? `••• ${text.slice(-3)}` : null
}

// Each entry is [label, value, kind?]. Rows with no value are dropped, and so are sections left empty.
const sections = computed(() => {
  const c = claim.value
  if (!c) return []
  const motor = c.insurance_type === 'motor'
  const list = [
    {
      title: 'Claim',
      rows: [
        ['Reference', c.claim_reference],
        ['Status', statusMeta(c.status).label],
        ['Type of claim', damageLabel(c)],
        ['Submitted', c.submission_date, 'date'],
        ['Policy', join(c.policy_number, c.coverage_type && `— ${c.coverage_type}`)],
        ['Customer’s estimate', c.estimated_value, 'money'],
      ],
    },
    {
      title: 'Claimant',
      rows: [
        ['Name', join(c.holder_title, c.holder_first_name, c.holder_last_name) || c.claimant_name],
        ['Company', c.holder_company],
        ['Email', c.claimant_email],
        ['Phone', c.claimant_phone],
        ['Alternate phone', c.alternate_phone],
        ['Preferred contact', c.preferred_contact_method, 'word'],
        ['Address', address(c, 'holder_')],
        ['Is the policyholder', c.is_policyholder],
        ['Relationship to policyholder', c.relationship_to_holder, 'word'],
        ['Reason for reporting', c.reporter_reason],
      ],
    },
    {
      title: 'What happened',
      rows: [
        ['Date', c.incident_date, 'date'],
        ['Time', c.incident_time],
        ['Location', join(c.incident_street, c.incident_cross_street && `(near ${c.incident_cross_street})`, c.incident_suburb, c.incident_state, c.incident_postcode) || c.incident_location],
        ['At the insured address', c.incident_at_insured_address],
        ['Description', c.incident_description],
        ['Loss description', c.loss_description],
        ['Additional comments', c.additional_comments],
        ['Anyone injured', c.person_injured],
        ['Other parties involved', c.others_involved],
        ['Witnesses present', c.witnesses_present],
        ['Police involved', c.police_involved],
        ['Police report number', c.police_report_number],
        ['Police station', c.police_station],
        ['Reported to police on', c.police_reported_date, 'date'],
        ['Charges laid', c.charges_laid],
        ['Charge details', c.charges_details],
      ],
    },
  ]

  if (motor) {
    list.push(
      {
        title: 'Vehicle',
        rows: [
          ['Registration', c.vehicle_registration],
          ['Year / make / model', join(c.vehicle_year, c.vehicle_make, c.vehicle_model)],
          ['Type', c.vehicle_type],
          ['Damage areas', c.vehicle_damage_areas],
          ['Being driven at the time', c.vehicle_driven],
          ['Towed', c.vehicle_towed],
          ['Now located at', c.vehicle_now_location],
          ['Airbags deployed', c.airbags_deployed],
          ['Over 40 km/h', c.speed_over_40],
          ['Other vehicle involved', c.other_vehicle_involved],
          ['Other property damaged', c.other_property_damaged],
        ],
      },
      {
        title: 'Driver',
        rows: [
          ['Policyholder was driving', c.policyholder_was_driver],
          ['Name', join(c.driver_title, c.driver_first_name, c.driver_last_name)],
          ['Date of birth', c.driver_dob, 'date'],
          ['Phone', c.driver_phone],
          ['Email', c.driver_email],
          ['Licence number', c.driver_licence_number],
          ['Years licensed', c.driver_licence_years],
          ['Address', address(c, 'driver_')],
          ['Alcohol or drugs involved', c.alcohol_or_drugs],
          ['Details', c.alcohol_details],
        ],
      },
    )
  } else if (c.insurance_type === 'property' || c.building_damaged != null || c.contents_affected != null) {
    list.push({
      title: 'Property damage',
      rows: [
        ['Building damaged', c.building_damaged],
        ['Areas', c.building_areas],
        ['Bathrooms affected', c.bathroom_rooms],
        ['Bedrooms affected', c.bedroom_rooms],
        ['Lounge rooms affected', c.lounge_rooms],
        ['Carpet', c.damage_carpet],
        ['Ceiling', c.damage_ceiling],
        ['Floor', c.damage_floor],
        ['Walls', c.damage_wall],
        ['Windows', c.damage_windows],
        ['Other damage', c.damage_other],
        ['Property secured', c.property_secure],
        ['Repairs already done', c.repairs_done],
        ['Still liveable', c.property_habitable],
        ['Contents affected', c.contents_affected],
        ['Contents total value', c.contents_total_value, 'money'],
        ['Another person responsible', c.other_person_responsible],
        ['Broker', join(c.broker_name, c.broker_phone)],
      ],
    })
  }

  list.push(
    {
      title: 'Background questions',
      rows: [
        ['Licence cancelled in last 3 years', c.licence_cancelled_3yrs],
        ['Fines or defaults on a cancelled licence', c.cancelled_fine_defaults],
        ['Alcohol-related conviction in last 3 years', c.convicted_alcohol_crime_3yrs],
        ['Convicted of a crime in last 5 years', c.convicted_crime_5yrs],
        ['Insurance declined in last 5 years', c.insurance_declined_5yrs],
      ],
    },
    {
      title: 'Payment details',
      rows: [
        ['GST registered', c.gst_registered],
        ['ABN', c.abn],
        ['Input tax credit', c.gst_itc_percent && `${c.gst_itc_percent}%`],
        ['Account name', c.eft_account_name],
        ['BSB', c.eft_bsb],
        ['Account number', maskedAccount(c.eft_account_number)],
      ],
    },
    {
      title: 'Declaration',
      rows: [
        ['Accepted', c.declaration_accepted],
        ['Signed by', c.declaration_name],
        ['Position', c.declaration_position],
        ['Date', c.declaration_date, 'date'],
      ],
    },
  )

  return list
    .map((section) => ({
      title: section.title,
      rows: section.rows
        .map(([label, value, kind]) => ({ label, value: show(value, kind) }))
        .filter((row) => row.value != null),
    }))
    .filter((section) => section.rows.length)
})

const contents = computed(() =>
  (claim.value?.contents_items || []).map((item) => ({
    category: humanise(item.category),
    description: item.description,
    value: item.estimated_value,
  })),
)

const otherParties = computed(() =>
  (claim.value?.other_parties || []).map((party) => ({
    name: join(party.title, party.first_name, party.last_name) || party.company_name,
    company: party.first_name || party.last_name ? party.company_name : null,
    phone: party.phone,
    email: party.email,
    address: address(party, ''),
    vehicle: join(party.vehicle_registration, party.vehicle_year, party.vehicle_make, party.vehicle_model),
    insurer: party.insurance_company,
  })),
)

const witnesses = computed(() =>
  (claim.value?.witnesses || []).map((witness) => ({
    name: join(witness.title, witness.first_name, witness.last_name),
    phone: witness.phone,
    email: witness.email,
    address: address(witness, ''),
  })),
)

function details(entries) {
  return Object.entries(entries)
    .filter(([, value]) => value != null && value !== '')
    .map(([label, value]) => `${label}: ${value}`)
    .join(' · ')
}
</script>

<template>
  <div>
    <RouterLink
      :to="{ name: 'assessor-claim-detail', params: { id } }"
      class="mb-6 inline-flex items-center gap-2 text-sm text-gray-500 transition-colors hover:text-gray-900"
    >
      <ArrowLeft class="h-4 w-4" />
      Back to claim
    </RouterLink>

    <p v-if="loading" class="text-sm text-gray-500">Loading the full form…</p>
    <div v-else-if="error" class="rounded-xl border border-red-200 bg-white p-6 text-sm text-red-600">
      {{ error }}
      <button type="button" class="ml-2 font-medium underline" @click="load">Retry</button>
    </div>

    <div v-else-if="claim" class="mx-auto max-w-4xl space-y-5">
      <div>
        <h1 class="text-xl font-semibold tracking-tight text-gray-900">Full form: {{ claim.claim_reference }}</h1>
        <p class="mt-1 text-sm text-gray-500">
          This is a read-only copy of everything the customer submitted. Photos and documents are on the claim page.
        </p>
      </div>

      <section v-for="section in sections" :key="section.title" class="rounded-xl border border-gray-200 bg-white p-6">
        <h2 class="mb-4 text-xs font-bold tracking-widest text-gray-400 uppercase">{{ section.title }}</h2>
        <dl class="grid gap-x-8 gap-y-4 sm:grid-cols-2">
          <div
            v-for="row in section.rows"
            :key="row.label"
            :class="row.value.length > 80 ? 'sm:col-span-2' : ''"
          >
            <dt class="text-xs tracking-wide text-gray-400 uppercase">{{ row.label }}</dt>
            <dd class="mt-0.5 text-sm font-medium break-words whitespace-pre-line text-gray-800">{{ row.value }}</dd>
          </div>
        </dl>
      </section>

      <section v-if="contents.length" class="rounded-xl border border-gray-200 bg-white p-6">
        <h2 class="mb-4 text-xs font-bold tracking-widest text-gray-400 uppercase">Contents</h2>
        <ul class="divide-y divide-gray-100 text-sm">
          <li v-for="(item, i) in contents" :key="i" class="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-2">
            <span class="font-medium text-gray-800">{{ item.category }}<span v-if="item.description" class="font-normal text-gray-600">: {{ item.description }}</span></span>
            <span class="text-gray-800">{{ formatMoney(item.value) }}</span>
          </li>
        </ul>
      </section>

      <section v-if="otherParties.length" class="rounded-xl border border-gray-200 bg-white p-6">
        <h2 class="mb-4 text-xs font-bold tracking-widest text-gray-400 uppercase">Other parties</h2>
        <ul class="space-y-3 text-sm">
          <li v-for="(party, i) in otherParties" :key="i" class="border-l-2 border-gray-200 pl-3">
            <p class="font-medium text-gray-800">{{ party.name || `Other party ${i + 1}` }}</p>
            <p class="text-gray-600">{{ details({ Company: party.company, Phone: party.phone, Email: party.email, Address: party.address, Vehicle: party.vehicle, Insurer: party.insurer }) }}</p>
          </li>
        </ul>
      </section>

      <section v-if="witnesses.length" class="rounded-xl border border-gray-200 bg-white p-6">
        <h2 class="mb-4 text-xs font-bold tracking-widest text-gray-400 uppercase">Witnesses</h2>
        <ul class="space-y-3 text-sm">
          <li v-for="(witness, i) in witnesses" :key="i" class="border-l-2 border-gray-200 pl-3">
            <p class="font-medium text-gray-800">{{ witness.name || `Witness ${i + 1}` }}</p>
            <p class="text-gray-600">{{ details({ Phone: witness.phone, Email: witness.email, Address: witness.address }) }}</p>
          </li>
        </ul>
      </section>
    </div>
  </div>
</template>
