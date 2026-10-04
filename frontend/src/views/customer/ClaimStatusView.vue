<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../../api/client'
import { formatDate, statusMeta } from '../../utils/claim'

const props = defineProps({ id: { type: [String, Number], required: true } })
const router = useRouter()

const claim = ref(null)
const loading = ref(true)
const error = ref('')

onMounted(async () => {
  try {
    claim.value = await api.myClaimDetail(props.id)
  } catch {
    error.value = 'This claim could not be loaded. Please try again.'
  } finally {
    loading.value = false
  }
})

const steps = computed(() => {
  if (!claim.value) return []
  const status = claim.value.status
  const decided = ['approved', 'rejected', 'closed'].includes(status)
  return [
    { title: 'Automated assessment', body: 'Supporting evidence and the incident description are being assessed.', done: status !== 'submitted' && status !== 'draft' },
    { title: 'Assessor review', body: 'A licensed assessor will review the recommendation before a decision is finalised.', done: decided || status === 'under_review' },
    {
      title: 'Decision notification',
      body: decided ? `Outcome: ${statusMeta(status).label}.` : 'You will be notified when a decision is available.',
      done: decided,
    },
  ]
})
</script>

<template>
  <div>
    <button class="mb-4 text-sm font-medium text-slate-500 hover:text-slate-900" @click="router.push({ name: 'my-claims' })">
      ← Back to claims
    </button>
    <p v-if="loading" class="text-sm text-slate-500">Loading claim details…</p>
    <p v-else-if="error" class="text-sm text-red-600">{{ error }}</p>
    <div v-else-if="claim" class="mx-auto max-w-lg">
      <p class="text-center text-xs text-slate-400">Claim reference</p>
      <h2 class="text-center text-2xl font-extrabold text-blue-600">{{ claim.claim_reference }}</h2>
      <p class="mt-1 text-center text-sm text-slate-500">
        {{ statusMeta(claim.status).label }} · submitted {{ formatDate(claim.submission_date) || '—' }}
      </p>
      <ol class="mt-6 space-y-4">
        <li v-for="(step, index) in steps" :key="step.title" class="flex gap-3">
          <span
            class="mt-0.5 flex h-6 w-6 flex-none items-center justify-center rounded-full text-xs font-bold"
            :class="step.done ? 'bg-emerald-500 text-white' : 'bg-blue-50 text-blue-600'"
          >
            {{ step.done ? '✓' : index + 1 }}
          </span>
          <div>
            <p class="text-sm font-semibold">{{ step.title }}</p>
            <p class="text-sm text-slate-500">{{ step.body }}</p>
          </div>
        </li>
      </ol>
    </div>
  </div>
</template>
