<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { AlertTriangle, ExternalLink, Image } from 'lucide-vue-next'
import { api } from '../../api/client'
import { imageMatchCloseness } from '../../utils/aiSteps'

const props = defineProps({
  match: { type: Object, required: true },
  // Sidebar summary: no thumbnails.
  compact: { type: Boolean, default: false },
})

const router = useRouter()
const ownThumb = ref('')
const matchedThumb = ref('')
const thumbsLoaded = ref(false)

const reference = computed(() => props.match.matched_claim_reference || `#${props.match.matched_claim_id}`)
const closeness = computed(() => imageMatchCloseness(props.match.hamming_distance))
const href = computed(() =>
  props.match.matched_claim_id == null
    ? null
    : router.resolve({ name: 'assessor-claim-detail', params: { id: String(props.match.matched_claim_id) } }).href,
)

function revoke() {
  if (ownThumb.value) URL.revokeObjectURL(ownThumb.value)
  if (matchedThumb.value) URL.revokeObjectURL(matchedThumb.value)
  ownThumb.value = ''
  matchedThumb.value = ''
}

async function thumbnail(docId) {
  if (docId == null) return ''
  try {
    const blob = await api.documentBlob(docId)
    if (String(blob.type).startsWith('image/')) return blob.url
    URL.revokeObjectURL(blob.url)
  } catch {
    // Preview is optional; the link still works.
  }
  return ''
}

let generation = 0
async function loadThumbs() {
  revoke()
  thumbsLoaded.value = false
  if (props.compact) return
  const current = ++generation
  const [own, matched] = await Promise.all([thumbnail(props.match.own_doc_id), thumbnail(props.match.matched_doc_id)])
  if (current !== generation) {
    if (own) URL.revokeObjectURL(own)
    if (matched) URL.revokeObjectURL(matched)
    return
  }
  ownThumb.value = own
  matchedThumb.value = matched
  thumbsLoaded.value = true
}

watch(() => [props.match.own_doc_id, props.match.matched_doc_id, props.compact], loadThumbs, { immediate: true })
onBeforeUnmount(() => {
  generation += 1
  revoke()
})
</script>

<template>
  <div class="rounded-xl border border-amber-200 bg-amber-50" :class="compact ? 'p-4' : 'p-5'">
    <div class="flex items-start gap-3">
      <AlertTriangle class="mt-0.5 shrink-0 text-amber-600" :class="compact ? 'h-4 w-4' : 'h-5 w-5'" />
      <div class="min-w-0 flex-1">
        <p class="text-sm font-semibold text-amber-900">Similar image found on another claim</p>
        <p class="mt-0.5 text-sm text-amber-800">
          {{ closeness }} — claim {{ reference }}<span v-if="match.matched_customer_name"> ({{ match.matched_customer_name }})</span>
        </p>
        <p class="mt-1 text-xs text-amber-700">Verify before relying on this finding.</p>
      </div>
    </div>

    <div v-if="!compact && (match.own_doc_id != null || match.matched_doc_id != null)" class="mt-4 grid grid-cols-2 gap-3">
      <figure v-if="match.own_doc_id != null">
        <img v-if="ownThumb" :src="ownThumb" alt="Photo on this claim" class="h-32 w-full rounded-lg border border-amber-200 bg-white object-cover" />
        <div v-else class="flex h-32 w-full flex-col items-center justify-center gap-1 rounded-lg border border-amber-200 bg-white text-amber-300">
          <Image class="h-6 w-6" />
          <span v-if="thumbsLoaded" class="text-xs text-amber-700">Preview unavailable</span>
        </div>
        <figcaption class="mt-1 text-xs text-amber-800">This claim</figcaption>
      </figure>
      <figure v-if="match.matched_doc_id != null">
        <img v-if="matchedThumb" :src="matchedThumb" :alt="`Matched photo on claim ${reference}`" class="h-32 w-full rounded-lg border border-amber-200 bg-white object-cover" />
        <div v-else class="flex h-32 w-full flex-col items-center justify-center gap-1 rounded-lg border border-amber-200 bg-white text-amber-300">
          <Image class="h-6 w-6" />
          <span v-if="thumbsLoaded" class="text-xs text-amber-700">Preview unavailable</span>
        </div>
        <figcaption class="mt-1 text-xs text-amber-800">Claim {{ reference }}</figcaption>
      </figure>
    </div>

    <a
      v-if="href"
      :href="href"
      target="_blank"
      rel="noopener"
      class="mt-3 inline-flex items-center gap-1.5 text-sm font-medium text-amber-800 hover:text-amber-950 hover:underline"
    >
      Open claim {{ reference }} in new tab
      <ExternalLink class="h-3.5 w-3.5" />
    </a>
  </div>
</template>
