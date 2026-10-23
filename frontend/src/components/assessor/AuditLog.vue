<script setup>
import { ref } from 'vue'
import { ChevronDown, ChevronUp } from 'lucide-vue-next'
import { auditActionLabel, formatDateTime } from '../../utils/aiSteps'

defineProps({
  entries: { type: Array, default: () => [] },
})

const open = ref(false)
</script>

<template>
  <section class="overflow-hidden rounded-xl border border-gray-200 bg-white">
    <button
      type="button"
      class="flex w-full items-center justify-between px-6 py-4 text-left transition-colors hover:bg-gray-50"
      :aria-expanded="open"
      @click="open = !open"
    >
      <span class="text-sm font-semibold tracking-wide text-gray-900 uppercase">Full audit log</span>
      <span class="flex items-center gap-2 text-xs text-gray-400">
        {{ entries.length }} {{ entries.length === 1 ? 'entry' : 'entries' }}
        <ChevronUp v-if="open" class="h-4 w-4" />
        <ChevronDown v-else class="h-4 w-4" />
      </span>
    </button>
    <div v-if="open" class="border-t border-gray-100 px-6 py-4">
      <p v-if="!entries.length" class="text-sm text-gray-500">No audit entries have been recorded for this claim.</p>
      <ol v-else class="space-y-3">
        <li v-for="(entry, i) in entries" :key="entry.log_id ?? i" class="border-l-2 border-gray-200 pl-3">
          <div class="flex flex-wrap items-baseline justify-between gap-x-3">
            <p class="text-sm font-medium text-gray-800">{{ auditActionLabel(entry.action_type) }}</p>
            <p class="text-xs text-gray-400">{{ formatDateTime(entry.timestamp) }}</p>
          </div>
          <p v-if="entry.description" class="mt-0.5 text-sm leading-relaxed break-words text-gray-500">{{ entry.description }}</p>
        </li>
      </ol>
    </div>
  </section>
</template>
