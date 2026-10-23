<script setup>
import { computed, inject, ref } from 'vue'
import { ExternalLink } from 'lucide-vue-next'
import { isExclusion, normaliseSectionRef, sectionLabel, unitToPercent } from '../../utils/aiSteps'
import { POLICY_DOCUMENT_KEY } from './usePolicyDocument'

const props = defineProps({
  clause: { type: Object, required: true },
  // "memo" shows how the clause applies; "evidence" shows the retrieved excerpt.
  variant: { type: String, default: 'memo' },
})

const policyDocument = inject(POLICY_DOCUMENT_KEY, null)
const opening = ref(false)
const error = ref('')

const refLabel = computed(() => sectionLabel(props.clause.section_ref))
const title = computed(() => {
  const text = String(props.clause.title || '').trim()
  if (!text || normaliseSectionRef(text) === normaliseSectionRef(props.clause.section_ref)) return ''
  return text
})
const excerpt = computed(() => props.clause.excerpt || props.clause.text || props.clause.content || '')
const page = computed(() => {
  const value = Number(props.clause.page)
  return Number.isInteger(value) && value > 0 ? value : null
})
const matchPercent = computed(() => unitToPercent(props.clause.similarity ?? props.clause.relevance_score ?? null))

async function openInPds() {
  if (!policyDocument || opening.value) return
  error.value = ''
  opening.value = true
  const ok = await policyDocument.open(page.value)
  opening.value = false
  if (!ok) error.value = 'Policy document unavailable'
}
</script>

<template>
  <div class="rounded-lg border border-gray-200 bg-white p-4">
    <div v-if="refLabel || isExclusion(clause) || matchPercent != null" class="mb-1.5 flex flex-wrap items-center gap-2">
      <span v-if="refLabel" class="rounded border border-violet-100 bg-violet-50 px-2 py-0.5 text-xs font-semibold text-violet-700">
        {{ refLabel }}
      </span>
      <span v-if="isExclusion(clause)" class="rounded-full border border-red-200 bg-red-50 px-2 py-0.5 text-xs font-semibold text-red-700">
        Exclusion
      </span>
      <span v-if="matchPercent != null" class="ml-auto rounded-full bg-gray-100 px-2 py-0.5 text-xs font-bold text-gray-600">
        {{ matchPercent }}% match
      </span>
    </div>
    <p v-if="title" class="text-sm font-semibold text-gray-800">{{ title }}</p>
    <p v-if="variant === 'memo' && clause.how_it_applies" class="mt-1 text-sm leading-relaxed text-gray-600">
      {{ clause.how_it_applies }}
    </p>
    <p v-else-if="excerpt" class="mt-1 line-clamp-5 text-sm leading-relaxed whitespace-pre-line text-gray-600">
      {{ excerpt }}
    </p>
    <div v-if="policyDocument" class="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1">
      <button
        type="button"
        class="inline-flex items-center gap-1 text-xs font-medium text-indigo-600 hover:text-indigo-800 disabled:opacity-50"
        :disabled="opening"
        @click="openInPds"
      >
        {{ opening ? 'Opening…' : 'Open in PDS' }}
        <ExternalLink class="h-3.5 w-3.5" />
      </button>
      <span v-if="page" class="text-xs text-gray-400">Page {{ page }}</span>
      <span v-if="error" class="text-xs text-red-600">{{ error }}</span>
    </div>
  </div>
</template>
