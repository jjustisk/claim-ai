<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { api, ApiError } from '../../api/client'

const props = defineProps({ id: { type: [String, Number], required: true } })
const router = useRouter()

const claim = ref(null)
const loading = ref(true)
const error = ref('')
const submitting = ref(false)
const reviewError = ref('')
const notes = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    claim.value = await api.claimDetail(props.id)
  } catch (err) {
    error.value = 'Could not load this claim.'
  } finally {
    loading.value = false
  }
}

onMounted(load)

const latestDecision = computed(() => claim.value?.ai_decisions?.[0] ?? null)

async function submitReview(outcome) {
  if (outcome === 'rejected' && !notes.value.trim()) {
    reviewError.value = 'Add notes explaining why before rejecting.'
    return
  }
  reviewError.value = ''
  submitting.value = true
  try {
    claim.value = await api.reviewClaim(props.id, outcome, notes.value)
    notes.value = ''
  } catch (err) {
    reviewError.value = err instanceof ApiError ? err.detail : 'Could not save the review.'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div>
    <button class="mb-4 text-sm text-slate-500 hover:text-slate-900" @click="router.push({ name: 'assessor-queue' })">
      ← Back to queue
    </button>

    <p v-if="loading" class="text-slate-500">Loading…</p>
    <p v-else-if="error" class="text-red-600">{{ error }}</p>

    <div v-else-if="claim" class="grid grid-cols-3 gap-6">
      <!-- Claim details -->
      <div class="col-span-2 space-y-6">
        <section class="rounded border border-slate-200 bg-white p-4">
          <div class="mb-3 flex items-center justify-between">
            <h1 class="text-lg font-semibold">{{ claim.claim_reference }}</h1>
            <span class="rounded-full bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700">{{ claim.status }}</span>
          </div>
          <dl class="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
            <div><dt class="text-slate-500">Customer</dt><dd>{{ claim.customer_name }} ({{ claim.customer_email }})</dd></div>
            <div><dt class="text-slate-500">Policy</dt><dd>{{ claim.policy_number }} · {{ claim.coverage_type }}</dd></div>
            <div><dt class="text-slate-500">Incident date</dt><dd>{{ claim.incident_date || '—' }}</dd></div>
            <div><dt class="text-slate-500">Estimated value</dt><dd>{{ claim.estimated_value ?? '—' }}</dd></div>
            <div class="col-span-2"><dt class="text-slate-500">Description</dt><dd>{{ claim.incident_description || claim.loss_description || '—' }}</dd></div>
          </dl>
        </section>

        <section v-if="claim.documents?.length" class="rounded border border-slate-200 bg-white p-4">
          <h2 class="mb-3 font-medium">Evidence</h2>
          <ul class="space-y-1 text-sm">
            <li v-for="doc in claim.documents" :key="doc.doc_id">
              <a class="text-blue-600 hover:underline" :href="api.documentUrl(doc.doc_id)" target="_blank" rel="noopener">
                {{ doc.file_type }} — uploaded {{ doc.upload_date }}
              </a>
            </li>
          </ul>
        </section>

        <section v-if="claim.reviews?.length" class="rounded border border-slate-200 bg-white p-4">
          <h2 class="mb-3 font-medium">Review history</h2>
          <ul class="space-y-2 text-sm">
            <li v-for="(r, i) in claim.reviews" :key="i" class="border-b border-slate-100 pb-2 last:border-0">
              <p><strong>{{ r.name }}</strong> — {{ r.outcome }} <span class="text-slate-400">({{ r.review_date }})</span></p>
              <p v-if="r.override_reason" class="text-slate-600">{{ r.override_reason }}</p>
            </li>
          </ul>
        </section>
      </div>

      <!-- AI recommendation + review actions -->
      <div class="space-y-6">
        <section class="rounded border border-slate-200 bg-white p-4">
          <h2 class="mb-3 font-medium">AI recommendation</h2>
          <div v-if="latestDecision" class="space-y-2 text-sm">
            <p><span class="text-slate-500">Decision:</span> <strong>{{ latestDecision.decision }}</strong></p>
            <p><span class="text-slate-500">Confidence:</span> {{ (latestDecision.confidence_score * 100).toFixed(0) }}%</p>
            <p class="text-slate-600">{{ latestDecision.reason_summary }}</p>
          </div>
          <p v-else class="text-sm text-slate-500">No AI decision recorded yet for this claim.</p>
        </section>

        <section v-if="claim.similar_image_match" class="rounded border border-amber-300 bg-amber-50 p-4">
          <h2 class="mb-2 font-medium text-amber-900">Possible duplicate evidence</h2>
          <p class="text-sm text-amber-800">
            Similar image found on claim {{ claim.similar_image_match.matched_claim_reference }}
            ({{ claim.similar_image_match.matched_customer_name }}).
          </p>
        </section>

        <section class="rounded border border-slate-200 bg-white p-4">
          <h2 class="mb-3 font-medium">Review</h2>
          <textarea
            v-model="notes"
            rows="3"
            placeholder="Notes (required for rejection)"
            class="mb-3 w-full rounded border border-slate-300 px-2 py-1 text-sm"
          />
          <p v-if="reviewError" class="mb-2 text-sm text-red-600">{{ reviewError }}</p>
          <div class="flex flex-wrap gap-2">
            <button
              :disabled="submitting"
              class="rounded bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
              @click="submitReview('approved')"
            >
              Approve
            </button>
            <button
              :disabled="submitting"
              class="rounded bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
              @click="submitReview('rejected')"
            >
              Reject
            </button>
            <button
              :disabled="submitting"
              class="rounded bg-amber-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-amber-600 disabled:opacity-50"
              @click="submitReview('under_review')"
            >
              Escalate
            </button>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>
