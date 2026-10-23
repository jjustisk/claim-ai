<script setup>
import { computed, ref } from 'vue'
import { ChevronDown, ChevronUp, Clock } from 'lucide-vue-next'
import { formatStepTime, stepMeta, stepStatusMeta } from '../../utils/aiSteps'

const props = defineProps({
  step: { type: Object, required: true },
  compact: { type: Boolean, default: false },
})

const open = ref(false)
const meta = computed(() => stepMeta(props.step.key, props.step.label))
const status = computed(() => stepStatusMeta(props.step.status))
const time = computed(() => formatStepTime(props.step.timestamp))
</script>

<template>
  <div class="mb-2 overflow-hidden rounded-xl border border-gray-200 bg-white">
    <button
      type="button"
      class="flex w-full items-center gap-3 text-left transition-colors hover:bg-gray-50"
      :class="compact ? 'px-3 py-3' : 'px-5 py-4'"
      :aria-expanded="open"
      @click="open = !open"
    >
      <div class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full" :class="meta.iconBg">
        <component :is="meta.icon" class="h-4 w-4" :class="meta.iconColor" />
      </div>
      <div class="min-w-0 flex-1">
        <p class="text-sm font-semibold text-gray-800">{{ meta.label }}</p>
        <p class="mt-0.5 text-xs font-medium" :class="status.subtitleClass">
          <component :is="status.subtitleIcon" v-if="status.subtitleIcon" class="mr-1 -mt-0.5 inline h-3 w-3" />{{ step.summary || status.label }}
        </p>
      </div>
      <div class="flex shrink-0 items-center gap-3">
        <span v-if="time && !compact" class="hidden items-center gap-1 text-xs text-gray-400 sm:flex">
          <Clock class="h-3 w-3" />
          {{ time }}
        </span>
        <div class="flex h-5 w-5 shrink-0 items-center justify-center rounded-full" :class="status.dotBg">
          <component :is="status.icon" class="h-3 w-3" :class="status.iconColor" />
        </div>
        <ChevronUp v-if="open" class="h-4 w-4 text-gray-400" />
        <ChevronDown v-else class="h-4 w-4 text-gray-400" />
      </div>
    </button>
    <div v-if="open" class="border-t border-gray-100 bg-gray-50 pt-1" :class="compact ? 'px-3 pb-4' : 'px-5 pb-5'">
      <p v-if="time && compact" class="flex items-center gap-1 pt-2 text-xs text-gray-400"><Clock class="h-3 w-3" />{{ time }}</p>
      <div class="pt-3">
        <slot />
      </div>
    </div>
  </div>
</template>
