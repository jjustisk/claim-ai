<script setup>
import { computed, ref } from 'vue'
import { ChevronDown, ChevronUp } from 'lucide-vue-next'
import { formatDate, formatMoney, statusMeta } from '../../utils/claim'

const props = defineProps({
  claim: { type: Object, required: true },
})

const open = ref(false)

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
    row('Priority', c.priority_level ?? 0),
    row('Fraud score', c.fraud_risk_score ?? 0),
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
    <button
      type="button"
      class="flex w-full items-center justify-between px-6 py-4 text-left transition-colors hover:bg-gray-50"
      :aria-expanded="open"
      @click="open = !open"
    >
      <span class="text-sm font-semibold tracking-wide text-gray-900 uppercase">Full claim record</span>
      <ChevronUp v-if="open" class="h-4 w-4 text-gray-400" />
      <ChevronDown v-else class="h-4 w-4 text-gray-400" />
    </button>
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
