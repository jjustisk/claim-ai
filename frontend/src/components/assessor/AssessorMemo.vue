<script setup>
import { computed } from 'vue'
import { FileText } from 'lucide-vue-next'
import DetailField from './DetailField.vue'
import PolicyClauseCard from './PolicyClauseCard.vue'
import { mergeClauses } from '../../utils/aiSteps'

const props = defineProps({
  assessment: { type: Object, default: null },
  fallbackText: { type: String, default: '' },
  inProgress: { type: Boolean, default: false },
})

const memo = computed(() => {
  const value = props.assessment?.memo
  return value && typeof value === 'object' && (value.summary || value.explanation) ? value : null
})
const referenceClauses = computed(() => (Array.isArray(props.assessment?.clauses) ? props.assessment.clauses : []))
const clauses = computed(() => {
  const cited = Array.isArray(memo.value?.clauses) ? memo.value.clauses : []
  return cited.length ? mergeClauses(cited, referenceClauses.value) : referenceClauses.value
})
const memoText = computed(() => props.assessment?.memo_text || props.fallbackText || '')
const referred = computed(() => props.assessment?.status === 'referred')
</script>

<template>
  <div class="overflow-hidden rounded-xl border border-gray-200 bg-white">
    <div class="flex items-center gap-2 border-b border-gray-100 bg-gray-50 px-6 py-4">
      <FileText class="h-4 w-4 text-gray-500" />
      <h2 class="text-sm font-semibold text-gray-900">Summary</h2>
      <span class="ml-2 rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600">Prepared automatically</span>
    </div>
    <div class="space-y-5 p-6">
      <template v-if="memo">
        <DetailField v-if="memo.summary" label="Summary" :value="memo.summary" />
        <DetailField v-if="memo.explanation" label="Why this decision" :value="memo.explanation" />
      </template>
      <p v-else-if="memoText" class="text-sm leading-relaxed whitespace-pre-wrap text-gray-700">{{ memoText }}</p>
      <p v-else-if="inProgress || assessment?.status === 'pending'" class="text-sm text-gray-500">
        The checks are still running. Check back shortly.
      </p>
      <p v-else-if="referred" class="text-sm text-gray-500">
        This claim was sent for review before a summary could be written. See “What we checked” to find out why.
      </p>
      <p v-else class="text-sm text-gray-500">No summary is available for this claim.</p>

      <div v-if="clauses.length" class="space-y-3">
        <p class="text-xs font-semibold tracking-wide text-gray-400 uppercase">Policy sections</p>
        <PolicyClauseCard v-for="(clause, i) in clauses" :key="`${clause.section_ref}-${i}`" :clause="clause" variant="memo" />
      </div>
      <p v-else-if="memo" class="text-sm text-gray-500">No policy sections were cited.</p>
    </div>
  </div>
</template>
