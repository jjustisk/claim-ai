<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import { FileText, X } from 'lucide-vue-next'

const props = defineProps({
  files: { type: Array, default: () => [] },
})
const emit = defineEmits(['remove'])

// Object URLs per File, created once and revoked when the file leaves the list.
const urls = new Map()
const items = ref([])

function sizeLabel(bytes) {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${Math.max(1, Math.round(bytes / 1024))} KB`
}

watch(
  () => props.files,
  (files) => {
    const current = new Set(files)
    for (const [file, url] of urls) {
      if (!current.has(file)) {
        URL.revokeObjectURL(url)
        urls.delete(file)
      }
    }
    items.value = files.map((file) => {
      if (!urls.has(file)) urls.set(file, URL.createObjectURL(file))
      return {
        file,
        url: urls.get(file),
        isImage: String(file.type).startsWith('image/'),
        size: sizeLabel(file.size || 0),
      }
    })
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  urls.forEach((url) => URL.revokeObjectURL(url))
  urls.clear()
})
</script>

<template>
  <ul v-if="items.length" class="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
    <li v-for="(item, i) in items" :key="item.url" class="group relative overflow-hidden rounded-lg border border-gray-200 bg-white">
      <a :href="item.url" target="_blank" rel="noopener" class="block" :title="`Open ${item.file.name} in a new tab`">
        <img v-if="item.isImage" :src="item.url" :alt="item.file.name" class="h-24 w-full object-cover" />
        <div v-else class="flex h-24 w-full items-center justify-center bg-gray-50">
          <FileText class="h-8 w-8 text-gray-400" />
        </div>
        <div class="px-2 py-1.5">
          <p class="truncate text-xs font-medium text-gray-700">{{ item.file.name }}</p>
          <p class="text-xs text-gray-400">{{ item.size }}</p>
        </div>
      </a>
      <button
        type="button"
        class="absolute top-1 right-1 flex h-6 w-6 items-center justify-center rounded-full bg-black/55 text-white hover:bg-black/75"
        :aria-label="`Remove ${item.file.name}`"
        @click="emit('remove', i)"
      >
        <X class="h-3.5 w-3.5" />
      </button>
    </li>
  </ul>
</template>
