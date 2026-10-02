<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../../api/client'

const claims = ref([])
const loading = ref(true)
const error = ref('')

onMounted(async () => {
  try {
    claims.value = await api.myClaims()
  } catch {
    error.value = 'Could not load your claims.'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div>
    <h1 class="mb-6 text-lg font-semibold">My claims</h1>
    <p v-if="loading" class="text-slate-500">Loading…</p>
    <p v-else-if="error" class="text-red-600">{{ error }}</p>
    <p v-else-if="!claims.length" class="text-slate-500">You haven't submitted any claims yet.</p>
    <ul v-else class="divide-y divide-slate-200 rounded border border-slate-200 bg-white">
      <li v-for="claim in claims" :key="claim.claim_id">
        <RouterLink
          :to="{ name: 'my-claim-status', params: { id: claim.claim_id } }"
          class="flex items-center justify-between px-4 py-3 hover:bg-slate-50"
        >
          <div>
            <p class="font-medium">{{ claim.claim_reference }}</p>
            <p class="text-sm text-slate-500">Submitted {{ claim.submission_date }}</p>
          </div>
          <span class="rounded-full bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700">{{ claim.status }}</span>
        </RouterLink>
      </li>
    </ul>
  </div>
</template>
