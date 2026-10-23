<script setup>
import { computed, ref } from 'vue'
import { ChevronDown, ChevronUp, ListChecks } from 'lucide-vue-next'
import AiStepDetails from './AiStepDetails.vue'
import AiStepRow from './AiStepRow.vue'
import { orderSteps } from '../../utils/aiSteps'

const props = defineProps({
  assessment: { type: Object, default: null },
  similarMatch: { type: Object, default: null },
  inProgress: { type: Boolean, default: false },
})

const open = ref(false)
const steps = computed(() => orderSteps(props.assessment?.steps))
const summary = computed(() => {
  if (!steps.value.length) return props.inProgress ? 'In progress' : 'No steps recorded'
  const flagged = steps.value.filter((s) => s.status === 'flag' || s.status === 'fail').length
  return `${steps.value.length} steps${flagged ? ` · ${flagged} flagged` : ' · all passed'}`
})
</script>

<template>
  <section class="overflow-hidden rounded-xl border border-gray-200 bg-white">
    <button
      type="button"
      class="flex w-full items-center gap-3 px-5 py-4 text-left transition-colors hover:bg-gray-50"
      :aria-expanded="open"
      @click="open = !open"
    >
      <ListChecks class="h-4 w-4 shrink-0 text-gray-500" />
      <div class="min-w-0 flex-1">
        <h2 class="text-sm font-semibold tracking-wide text-gray-900 uppercase">AI assessment steps</h2>
        <p class="mt-0.5 text-xs text-gray-400">{{ summary }}</p>
      </div>
      <ChevronUp v-if="open" class="h-4 w-4 text-gray-400" />
      <ChevronDown v-else class="h-4 w-4 text-gray-400" />
    </button>
    <div v-if="open" class="border-t border-gray-100 p-3">
      <template v-if="steps.length">
        <p class="mb-2 px-1 text-xs text-gray-400">Expand a step to see its evidence.</p>
        <AiStepRow v-for="(step, i) in steps" :key="step.key || i" :step="step" compact>
          <AiStepDetails :step="step" :assessment="assessment" :similar-match="similarMatch" />
        </AiStepRow>
      </template>
      <p v-else class="px-2 py-2 text-sm text-gray-500">
        {{ inProgress ? 'AI assessment in progress — steps will appear here as they complete.' : 'No AI pipeline steps have been recorded for this claim.' }}
      </p>
    </div>
  </section>
</template>
