<script setup>
import { computed, ref, watch } from 'vue'
import { X } from 'lucide-vue-next'

const props = defineProps({
  outcome: { type: String, required: true },
  submitting: { type: Boolean, default: false },
  error: { type: String, default: '' },
})
const emit = defineEmits(['close', 'confirm'])

const ACTIONS = {
  approved: {
    title: 'Approve Claim',
    body: 'You are approving this claim. Add any notes for the claim record.',
    button: 'bg-emerald-600 hover:bg-emerald-700',
  },
  rejected: {
    title: 'Reject Claim',
    body: 'You are rejecting this claim. Provide a clear explanation for the record.',
    button: 'bg-red-600 hover:bg-red-700',
  },
  under_review: {
    title: 'Escalate Claim',
    body: 'You are escalating this claim for senior assessor review. Explain why.',
    button: 'bg-amber-500 hover:bg-amber-600',
  },
}

const notes = ref('')
const config = computed(() => ACTIONS[props.outcome] || ACTIONS.under_review)
const notesRequired = computed(() => props.outcome === 'rejected')

watch(() => props.outcome, () => {
  notes.value = ''
})

function close() {
  if (!props.submitting) emit('close')
}
</script>

<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" @click.self="close">
    <div class="w-full max-w-md rounded-xl bg-white p-6 shadow-xl" role="dialog" aria-modal="true" :aria-label="config.title">
      <div class="mb-4 flex items-center justify-between">
        <h3 class="text-xl font-semibold text-gray-900">{{ config.title }}</h3>
        <button type="button" class="text-gray-400 hover:text-gray-600" aria-label="Close" @click="close">
          <X class="h-5 w-5" />
        </button>
      </div>
      <p class="mb-6 text-gray-600">{{ config.body }}</p>
      <form @submit.prevent="emit('confirm', notes)">
        <div class="mb-6">
          <label for="review-notes" class="mb-2 block text-sm font-medium text-gray-700">
            Notes <span v-if="notesRequired" class="text-red-600">(required)</span>
          </label>
          <textarea
            id="review-notes"
            v-model="notes"
            rows="4"
            class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-transparent focus:ring-2 focus:ring-violet-300 focus:outline-none"
            placeholder="Add any additional notes or comments…"
          />
          <p v-if="error" class="mt-2 text-sm text-red-600">{{ error }}</p>
        </div>
        <div class="flex gap-3">
          <button
            type="button"
            class="flex-1 rounded-lg border border-gray-300 px-4 py-2 text-gray-700 hover:bg-gray-50"
            :disabled="submitting"
            @click="close"
          >
            Cancel
          </button>
          <button
            type="submit"
            class="flex-1 rounded-lg px-4 py-2 font-medium text-white disabled:opacity-50"
            :class="config.button"
            :disabled="submitting"
          >
            {{ submitting ? 'Saving…' : 'Confirm' }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>
