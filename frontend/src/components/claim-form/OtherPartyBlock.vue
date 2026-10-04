<script setup>
const props = defineProps({
  index: { type: Number, required: true },
  form: { type: Object, required: true },
  titles: { type: Array, default: () => [] },
  states: { type: Array, default: () => [] },
  vehicleTypes: { type: Array, default: () => [] },
  damageAreas: { type: Array, default: () => [] },
  includeVehicle: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
})

const prefix = `other_${props.index}`

function toggleDamage(value, checked) {
  const key = `${prefix}_vehicle_damage`
  const list = [...(props.form[key] || [])]
  const i = list.indexOf(value)
  if (checked && i === -1) list.push(value)
  if (!checked && i !== -1) list.splice(i, 1)
  props.form[key] = list
}
</script>

<template>
  <div class="space-y-3 rounded-xl border border-slate-200 p-4">
    <h3 class="text-sm font-semibold">Other person {{ index }}</h3>
    <div class="grid gap-4 sm:grid-cols-2">
      <label class="block text-sm">
        <span class="mb-1 block font-medium">First name</span>
        <input v-model="form[`${prefix}_first_name`]" class="field" :disabled="disabled" />
      </label>
      <label class="block text-sm">
        <span class="mb-1 block font-medium">Last name</span>
        <input v-model="form[`${prefix}_last_name`]" class="field" :disabled="disabled" />
      </label>
      <label class="block text-sm sm:col-span-2">
        <span class="mb-1 block font-medium">Company name</span>
        <input v-model="form[`${prefix}_company_name`]" class="field" :disabled="disabled" />
      </label>
      <label class="block text-sm">
        <span class="mb-1 block font-medium">Phone</span>
        <input v-model="form[`${prefix}_phone`]" class="field" :disabled="disabled" />
      </label>
      <label class="block text-sm">
        <span class="mb-1 block font-medium">Email</span>
        <input v-model="form[`${prefix}_email`]" type="email" class="field" :disabled="disabled" />
      </label>
      <label class="block text-sm sm:col-span-2">
        <span class="mb-1 block font-medium">Insurance company</span>
        <input v-model="form[`${prefix}_insurance_company`]" class="field" :disabled="disabled" />
      </label>
      <label class="block text-sm">
        <span class="mb-1 block font-medium">Policy number</span>
        <input v-model="form[`${prefix}_insurance_policy_number`]" class="field" :disabled="disabled" />
      </label>
      <label class="block text-sm">
        <span class="mb-1 block font-medium">Claim number</span>
        <input v-model="form[`${prefix}_insurance_claim_number`]" class="field" :disabled="disabled" />
      </label>
      <label class="block text-sm sm:col-span-2">
        <span class="mb-1 block font-medium">Licence number</span>
        <input v-model="form[`${prefix}_licence_number`]" class="field" :disabled="disabled" />
      </label>
      <template v-if="includeVehicle">
        <label class="block text-sm">
          <span class="mb-1 block font-medium">Registration</span>
          <input v-model="form[`${prefix}_vehicle_registration`]" class="field" :disabled="disabled" />
        </label>
        <label class="block text-sm">
          <span class="mb-1 block font-medium">Vehicle type</span>
          <select v-model="form[`${prefix}_vehicle_type`]" class="field" :disabled="disabled">
            <option value="">Select</option>
            <option v-for="t in vehicleTypes" :key="t.value" :value="t.value">{{ t.label }}</option>
          </select>
        </label>
        <label class="block text-sm">
          <span class="mb-1 block font-medium">Year</span>
          <input v-model="form[`${prefix}_vehicle_year`]" class="field" :disabled="disabled" />
        </label>
        <label class="block text-sm">
          <span class="mb-1 block font-medium">Make</span>
          <input v-model="form[`${prefix}_vehicle_make`]" class="field" :disabled="disabled" />
        </label>
        <label class="block text-sm sm:col-span-2">
          <span class="mb-1 block font-medium">Model</span>
          <input v-model="form[`${prefix}_vehicle_model`]" class="field" :disabled="disabled" />
        </label>
        <div class="sm:col-span-2">
          <p class="mb-2 text-sm font-medium">Vehicle damage areas</p>
          <div class="grid gap-2 sm:grid-cols-2">
            <label v-for="area in damageAreas" :key="area.value" class="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                :checked="(form[`${prefix}_vehicle_damage`] || []).includes(area.value)"
                :disabled="disabled"
                @change="toggleDamage(area.value, $event.target.checked)"
              />
              {{ area.label }}
            </label>
          </div>
        </div>
      </template>
      <label v-else class="block text-sm sm:col-span-2">
        <span class="mb-1 block font-medium">Other person's vehicle registration</span>
        <input v-model="form[`${prefix}_vehicle_registration`]" class="field" :disabled="disabled" />
      </label>
    </div>
  </div>
</template>
