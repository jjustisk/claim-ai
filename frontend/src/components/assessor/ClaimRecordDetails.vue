<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ChevronDown, ChevronUp, ExternalLink } from 'lucide-vue-next'
import { formatDate, formatMoney, statusMeta } from '../../utils/claim'

const props = defineProps({
  claim: { type: Object, required: true },
})

const router = useRouter()
const open = ref(false)

const formHref = computed(() =>
  props.claim.claim_id == null
    ? null
    : router.resolve({ name: 'assessor-claim-form', params: { id: String(props.claim.claim_id) } }).href,
)

// Matches the 0.35 threshold the checks use to flag a claim; the raw score is never shown.
const warningSigns = computed(() => {
  const score = Number(props.claim.fraud_risk_score)
  if (!Number.isFinite(score) || score <= 0) return 'None found'
  return score >= 0.35 ? 'Check closely' : 'Some warning signs'
})

function yesNo(value) {
  if (value === true) return 'Yes'
  if (value === false) return 'No'
  return '—'
}

function row(label, value) {
  const text = value == null || value === '' ? '—' : value
  return { label, value: text }
}

const policyRows = computed(() => {
  const c = props.claim
  return [
    row('Customer', [c.customer_name, c.customer_email && `(${c.customer_email})`].filter(Boolean).join(' ')),
    row('Phone', c.customer_phone),
    row('Policy', [c.policy_number, c.coverage_type].filter(Boolean).join(' — ')),
    row('Submitted', formatDate(c.submission_date)),
    row('Warning signs', warningSigns.value),
    row('Estimated value', formatMoney(c.estimated_value ?? c.cost)),
  ]
})

const vehicleRows = computed(() => {
  const c = props.claim
  return [
    row('Registration', c.vehicle_registration),
    row('Year / make / model', [c.vehicle_year, c.vehicle_make, c.vehicle_model].filter(Boolean).join(' ')),
    row('Damage areas', c.vehicle_damage_areas),
    row('Vehicle driven', yesNo(c.vehicle_driven)),
    row('Licence', c.driver_licence_number),
  ]
})
</script>

<template>
  <section class="overflow-hidden rounded-xl border border-gray-200 bg-white">
    <div class="flex items-center gap-3 pr-6 transition-colors hover:bg-gray-50">
      <button
        type="button"
        class="flex flex-1 items-center justify-between px-6 py-4 text-left"
        :aria-expanded="open"
        @click="open = !open"
      >
        <span class="text-sm font-semibold tracking-wide text-gray-900 uppercase">Full claim record</span>
        <ChevronUp v-if="open" class="h-4 w-4 text-gray-400" />
        <ChevronDown v-else class="h-4 w-4 text-gray-400" />
      </button>
      <a
        v-if="formHref"
        :href="formHref"
        target="_blank"
        rel="noopener"
        class="inline-flex shrink-0 items-center gap-1 text-sm font-medium text-blue-700 hover:text-blue-900 hover:underline"
      >
        Open full form
        <ExternalLink class="h-3.5 w-3.5" />
      </a>
    </div>
    <div v-if="open" class="space-y-6 border-t border-gray-100 px-6 py-5 text-sm">
      <div>
        <h3 class="mb-3 text-xs font-bold tracking-widest text-gray-400 uppercase">Policy and claimant</h3>
        <dl class="grid gap-4 sm:grid-cols-2">
          <div v-for="item in policyRows" :key="item.label">
            <dt class="text-xs tracking-wide text-gray-400 uppercase">{{ item.label }}</dt>
            <dd class="mt-0.5 font-medium break-words text-gray-800">{{ item.value }}</dd>
          </div>
        </dl>
      </div>
      <div v-if="claim.insurance_type === 'motor'">
        <h3 class="mb-3 text-xs font-bold tracking-widest text-gray-400 uppercase">Vehicle and driver</h3>
        <dl class="grid gap-4 sm:grid-cols-2">
          <div v-for="item in vehicleRows" :key="item.label">
            <dt class="text-xs tracking-wide text-gray-400 uppercase">{{ item.label }}</dt>
            <dd class="mt-0.5 font-medium break-words text-gray-800">{{ item.value }}</dd>
          </div>
        </dl>
      </div>
      <div v-if="claim.reviews?.length">
        <h3 class="mb-3 text-xs font-bold tracking-widest text-gray-400 uppercase">Review history</h3>
        <ul class="space-y-2">
          <li v-for="(r, i) in claim.reviews" :key="i" class="border-l-2 border-gray-200 pl-3">
            <p class="text-gray-800">
              <span class="font-medium">{{ r.name || r.email }}</span>
              <span class="text-gray-500"> — {{ statusMeta(r.outcome).label }}</span>
              <span v-if="r.review_date" class="text-xs text-gray-400"> · {{ formatDate(r.review_date) }}</span>
            </p>
            <p v-if="r.override_reason" class="mt-0.5 text-gray-600">{{ r.override_reason }}</p>
          </li>
        </ul>
      </div>
    </div>
  </section>
</template>
