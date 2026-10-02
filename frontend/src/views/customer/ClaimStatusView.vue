<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../../api/client'

const props = defineProps({ id: { type: [String, Number], required: true } })
const router = useRouter()

const claim = ref(null)
const loading = ref(true)
const error = ref('')

onMounted(async () => {
  try {
    claim.value = await api.myClaimDetail(props.id)
  } catch {
    error.value = 'Could not load this claim.'
  } finally {
    loading.value = false
  }
})

// Derived stage timeline from claim.status + submission_date/outcome_date.
// TODO(backend): there's no real milestone-timestamp tracking yet
// (e.g. "AI review started", "sent to assessor") — only submission_date
// and outcome_date exist on the claim row. This is a reasonable
// approximation for the MVP demo, but matching the step list's
// "milestone timeline, estimated resolution" properly needs a backend
// addition (a claim_status_history table or similar) before this can
// show real per-stage timestamps.
const steps = computed(() => {
  if (!claim.value) return []
  const status = claim.value.status
  const terminal = ['approved', 'rejected', 'closed'].includes(status)
  return [
    { label: 'Submitted', done: true, date: claim.value.submission_date },
    { label: 'Under review', done: status !== 'submitted', date: null },
    {
      label: terminal ? status.charAt(0).toUpperCase() + status.slice(1) : 'Decision',
      done: terminal,
      date: claim.value.outcome_date,
    },
  ]
})
</script>

<template>
  <div>
    <button class="mb-4 text-sm text-slate-500 hover:text-slate-900" @click="router.push({ name: 'my-claims' })">
      ← Back to my claims
    </button>

    <p v-if="loading" class="text-slate-500">Loading…</p>
    <p v-else-if="error" class="text-red-600">{{ error }}</p>

    <div v-else-if="claim" class="max-w-xl space-y-6">
      <div>
        <h1 class="text-lg font-semibold">{{ claim.claim_reference }}</h1>
        <p class="text-sm text-slate-500">{{ claim.coverage_type }} · {{ claim.policy_number }}</p>
      </div>

      <ol class="space-y-4">
        <li v-for="(step, i) in steps" :key="i" class="flex items-start gap-3">
          <span
            class="mt-0.5 flex h-5 w-5 flex-none items-center justify-center rounded-full text-xs"
            :class="step.done ? 'bg-emerald-600 text-white' : 'bg-slate-200 text-slate-500'"
          >
            {{ step.done ? '✓' : i + 1 }}
          </span>
          <div>
            <p :class="step.done ? 'font-medium text-slate-900' : 'text-slate-500'">{{ step.label }}</p>
            <p v-if="step.date" class="text-xs text-slate-400">{{ step.date }}</p>
          </div>
        </li>
      </ol>

      <section v-if="claim.documents?.length" class="rounded border border-slate-200 bg-white p-4">
        <h2 class="mb-2 text-sm font-medium">Your uploaded evidence</h2>
        <ul class="space-y-1 text-sm text-slate-600">
          <li v-for="doc in claim.documents" :key="doc.doc_id">{{ doc.file_type }} — {{ doc.upload_date }}</li>
        </ul>
      </section>
    </div>
  </div>
</template>
