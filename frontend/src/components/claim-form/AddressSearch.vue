<script setup>
import { onBeforeUnmount, ref } from 'vue'
import { MapPin, Search } from 'lucide-vue-next'
import { api } from '../../api/client'

defineProps({
  label: { type: String, default: 'Search for an address' },
})
const emit = defineEmits(['select'])

const query = ref('')
const results = ref([])
const open = ref(false)
const loading = ref(false)
const searched = ref(false)
let timer = null
let generation = 0

function onInput() {
  clearTimeout(timer)
  const q = query.value.trim()
  if (q.length < 3) {
    results.value = []
    open.value = false
    return
  }
  timer = setTimeout(() => search(q), 300)
}

async function search(q) {
  const current = ++generation
  loading.value = true
  try {
    const rows = await api.searchAddresses(q)
    if (current !== generation) return
    results.value = Array.isArray(rows) ? rows : []
  } catch {
    if (current === generation) results.value = []
  } finally {
    if (current === generation) {
      loading.value = false
      searched.value = true
      open.value = true
    }
  }
}

function choose(address) {
  emit('select', address)
  query.value = address.label
  open.value = false
}

function close() {
  setTimeout(() => (open.value = false), 150)
}

onBeforeUnmount(() => clearTimeout(timer))
</script>

<template>
  <div class="relative text-sm">
    <span class="mb-1 block font-medium">{{ label }}</span>
    <div class="relative">
      <Search class="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-gray-400" />
      <input
        v-model="query"
        type="search"
        autocomplete="off"
        class="field pl-9"
        placeholder="Start typing a street address…"
        @input="onInput"
        @focus="open = results.length > 0"
        @blur="close"
        @keydown.esc="open = false"
      />
    </div>
    <ul
      v-if="open"
      class="absolute z-20 mt-1 max-h-64 w-full overflow-y-auto rounded-lg border border-gray-200 bg-white py-1 shadow-lg"
    >
      <li v-if="loading" class="px-3 py-2 text-gray-400">Searching…</li>
      <template v-else-if="results.length">
        <li v-for="address in results" :key="address.label">
          <button
            type="button"
            class="flex w-full items-start gap-2 px-3 py-2 text-left hover:bg-gray-50"
            @mousedown.prevent="choose(address)"
          >
            <MapPin class="mt-0.5 h-4 w-4 shrink-0 text-gray-400" />
            <span>{{ address.label }}</span>
          </button>
        </li>
      </template>
      <li v-else-if="searched" class="px-3 py-2 text-gray-500">No matches — enter the address manually below.</li>
    </ul>
    <p class="mt-1 text-xs text-gray-400">Pick a match to fill the fields below, or type them in yourself.</p>
  </div>
</template>
