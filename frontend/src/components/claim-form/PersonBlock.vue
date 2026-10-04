<script setup>
defineProps({
  title: { type: String, required: true },
  prefix: { type: String, required: true },
  form: { type: Object, required: true },
  titles: { type: Array, default: () => [] },
  states: { type: Array, default: () => [] },
  required: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
})
</script>

<template>
  <div class="space-y-3">
    <h3 class="text-sm font-semibold text-slate-800">{{ title }}</h3>
    <div class="grid gap-4 sm:grid-cols-2">
      <label class="block text-sm">
        <span class="mb-1 block font-medium text-slate-700">Title</span>
        <select v-model="form[`${prefix}_title`]" class="field" :required="required" :disabled="disabled">
          <option value="">Select</option>
          <option v-for="t in titles" :key="t.value" :value="t.value">{{ t.label }}</option>
        </select>
      </label>
      <label class="block text-sm">
        <span class="mb-1 block font-medium text-slate-700">First name</span>
        <input v-model="form[`${prefix}_first_name`]" class="field" :required="required" :disabled="disabled" />
      </label>
      <label class="block text-sm">
        <span class="mb-1 block font-medium text-slate-700">Last name</span>
        <input v-model="form[`${prefix}_last_name`]" class="field" :required="required" :disabled="disabled" />
      </label>
      <label class="block text-sm">
        <span class="mb-1 block font-medium text-slate-700">Phone</span>
        <input v-model="form[`${prefix}_phone`]" class="field" :required="required" :disabled="disabled" />
      </label>
      <label class="block text-sm sm:col-span-2">
        <span class="mb-1 block font-medium text-slate-700">Email</span>
        <input v-model="form[`${prefix}_email`]" type="email" class="field" :disabled="disabled" />
      </label>
      <label class="block text-sm">
        <span class="mb-1 block font-medium text-slate-700">Street number</span>
        <input v-model="form[`${prefix}_street_number`]" class="field" :disabled="disabled" />
      </label>
      <label class="block text-sm">
        <span class="mb-1 block font-medium text-slate-700">Street name</span>
        <input v-model="form[`${prefix}_street_name`]" class="field" :disabled="disabled" />
      </label>
      <label class="block text-sm">
        <span class="mb-1 block font-medium text-slate-700">Suburb</span>
        <input v-model="form[`${prefix}_suburb`]" class="field" :disabled="disabled" />
      </label>
      <label class="block text-sm">
        <span class="mb-1 block font-medium text-slate-700">State</span>
        <select v-model="form[`${prefix}_state`]" class="field" :disabled="disabled">
          <option value="">Select</option>
          <option v-for="s in states" :key="s.value" :value="s.value">{{ s.label }}</option>
        </select>
      </label>
      <label class="block text-sm">
        <span class="mb-1 block font-medium text-slate-700">Postcode</span>
        <input v-model="form[`${prefix}_postcode`]" class="field" :disabled="disabled" />
      </label>
    </div>
  </div>
</template>
