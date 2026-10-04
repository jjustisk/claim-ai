<script setup>
defineProps({
  name: { type: String, required: true },
  modelValue: { type: String, default: '' },
  required: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
})
defineEmits(['update:modelValue'])
</script>

<template>
  <div class="flex flex-wrap gap-4 text-sm">
    <label class="inline-flex items-center gap-2">
      <input
        type="radio"
        :name="name"
        value="yes"
        :checked="modelValue === 'yes'"
        :required="required && !modelValue"
        :disabled="disabled"
        @change="$emit('update:modelValue', 'yes')"
      />
      Yes
    </label>
    <label class="inline-flex items-center gap-2">
      <input
        type="radio"
        :name="name"
        value="no"
        :checked="modelValue === 'no'"
        :disabled="disabled"
        @change="$emit('update:modelValue', 'no')"
      />
      No
    </label>
  </div>
</template>
