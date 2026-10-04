<script setup>
import { ref } from 'vue'
import { formatDate, formatMoney } from '../../utils/claim'

defineProps({
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
</script>

<template>
  <section class="rounded-xl border border-slate-200">
    <button type="button" class="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-semibold" @click="open = !open">
      Full claim record
      <span class="text-slate-400">{{ open ? '−' : '+' }}</span>
    </button>
    <div v-if="open" class="space-y-4 border-t border-slate-100 px-4 py-4 text-sm">
      <div>
        <h3 class="mb-2 font-semibold text-slate-800">Policy and claimant</h3>
        <dl class="grid gap-2 sm:grid-cols-2">
          <template v-for="item in [
            row('Customer', `${claim.customer_name} (${claim.customer_email})`),
            row('Phone', claim.customer_phone),
            row('Policy', `${claim.policy_number} — ${claim.coverage_type}`),
            row('Submitted', formatDate(claim.submission_date)),
            row('Priority', claim.priority_level ?? 0),
            row('Fraud score', claim.fraud_risk_score ?? 0),
            row('Estimated value', formatMoney(claim.estimated_value ?? claim.cost)),
          ]" :key="item.label">
            <dt class="text-slate-500">{{ item.label }}</dt>
            <dd class="font-medium text-slate-800">{{ item.value }}</dd>
          </template>
        </dl>
      </div>
      <div v-if="claim.insurance_type === 'motor'">
        <h3 class="mb-2 font-semibold">Vehicle and driver</h3>
        <dl class="grid gap-2 sm:grid-cols-2">
          <template v-for="item in [
            row('Registration', claim.vehicle_registration),
            row('Year / make / model', [claim.vehicle_year, claim.vehicle_make, claim.vehicle_model].filter(Boolean).join(' ')),
            row('Damage areas', claim.vehicle_damage_areas),
            row('Vehicle driven', yesNo(claim.vehicle_driven)),
            row('Licence', claim.driver_licence_number),
          ]" :key="item.label">
            <dt class="text-slate-500">{{ item.label }}</dt>
            <dd>{{ item.value }}</dd>
          </template>
        </dl>
      </div>
      <div v-if="claim.reviews?.length">
        <h3 class="mb-2 font-semibold">Review history</h3>
        <ul class="space-y-2">
          <li v-for="(r, i) in claim.reviews" :key="i">
            <strong>{{ r.name || r.email }}</strong> — {{ r.outcome }}
            <span v-if="r.override_reason" class="text-slate-600"> · {{ r.override_reason }}</span>
          </li>
        </ul>
      </div>
    </div>
  </section>
</template>
