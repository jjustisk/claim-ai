<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuth } from '../../stores/auth'
import { api, ApiError } from '../../api/client'
import ClaimFormFields from '../../components/claim-form/ClaimFormFields.vue'
import { appendClaimFormData, claimToForm, createEmptyForm } from '../../utils/claimFormData'
import { errorText } from '../../utils/claim'

const props = defineProps({
  draftId: { type: [String, Number], default: null },
})

const { state } = useAuth()
const route = useRoute()
const router = useRouter()

const form = reactive(createEmptyForm(state.user))
const policies = ref([])
const options = ref({})
const files = ref([])
const loading = ref(true)
const submitting = ref(false)
const error = ref('')
const success = ref(null)

const effectiveDraftId = () => props.draftId || route.params.draftId || null

onMounted(async () => {
  try {
    const [policyRows, opts] = await Promise.all([api.policies(), api.formOptions()])
    policies.value = policyRows
    options.value = opts
    const id = effectiveDraftId()
    if (id) {
      const draft = await api.myClaimDetail(id)
      if (draft.status !== 'draft') {
        error.value = 'Only draft claims can be edited from this page.'
      } else {
        Object.assign(form, claimToForm(draft))
      }
    }
  } catch {
    error.value = 'The claim form could not be loaded. Please try again.'
  } finally {
    loading.value = false
  }
})

async function submit(intent) {
  error.value = ''
  submitting.value = true
  const fd = new FormData()
  appendClaimFormData(form, fd, {
    intent,
    claimId: effectiveDraftId(),
    files: files.value,
    contentsCategories: options.value.contents_categories || [],
  })
  try {
    success.value = await api.submitClaim(fd)
    if (intent === 'submit') {
      router.push({ name: 'my-claims', query: { submitted: success.value.claim_reference } })
    } else if (success.value?.claim_id && !effectiveDraftId()) {
      router.replace({ name: 'my-claims-draft', params: { draftId: success.value.claim_id } })
    }
  } catch (err) {
    error.value = err instanceof ApiError ? errorText(err, 'The claim could not be saved.') : 'The claim could not be saved.'
  } finally {
    submitting.value = false
  }
}

async function deleteDraft() {
  const id = effectiveDraftId()
  if (!id || !confirm('Delete this draft claim? This action cannot be undone.')) return
  try {
    await api.deleteDraft(id)
    router.push({ name: 'my-claims', query: { deleted: '1' } })
  } catch (err) {
    error.value = err instanceof ApiError ? errorText(err, 'The draft claim could not be deleted.') : 'The draft claim could not be deleted.'
  }
}
</script>

<template>
  <div>
    <div class="mb-6 flex flex-wrap items-start justify-between gap-3">
      <div>
        <button class="text-sm font-medium text-slate-500 hover:text-slate-900" @click="router.push({ name: 'my-claims' })">← Back to claims</button>
        <h1 class="mt-2 text-lg font-bold text-slate-900">Lodge a claim</h1>
        <p class="text-sm text-slate-500">Complete the motor or property claim form. You may save a draft and submit when ready.</p>
      </div>
      <div class="flex flex-wrap gap-2">
        <button v-if="effectiveDraftId()" type="button" class="rounded-lg border border-red-200 px-3 py-2 text-sm text-red-600 hover:bg-red-50" @click="deleteDraft">
          Delete draft
        </button>
        <RouterLink :to="{ name: 'my-claims-new' }" class="btn-primary">New claim</RouterLink>
      </div>
    </div>

    <p v-if="loading" class="text-sm text-slate-500">Loading form…</p>
    <p v-else-if="error && !form.insurance_type && effectiveDraftId()" class="text-sm text-red-600">{{ error }}</p>

    <template v-else>
      <div v-if="success && success.status === 'draft'" class="mb-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
        Your draft has been saved. Reference: {{ success.claim_reference }}
      </div>
      <ClaimFormFields v-model:files="files" :form="form" :policies="policies" :options="options" :disabled="submitting" />
      <p v-if="error" class="mt-4 text-sm text-red-600">{{ error }}</p>
      <div class="mt-6 flex flex-wrap gap-3">
        <button type="button" class="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium" :disabled="submitting" @click="submit('draft')">
          Save draft
        </button>
        <button type="button" class="btn-primary" :disabled="submitting" @click="submit('submit')">
          {{ submitting ? 'Submitting…' : 'Submit claim' }}
        </button>
      </div>
    </template>
  </div>
</template>
