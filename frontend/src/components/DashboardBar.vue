<script setup>
import { useRouter } from 'vue-router'
import { useAuth } from '../stores/auth'

defineProps({
  subtitle: { type: String, default: 'Dashboard' },
})

const { logout } = useAuth()
const router = useRouter()

function handleLogout() {
  logout()
  router.push({ name: 'login' })
}
</script>

<template>
  <div class="mb-5 flex items-center justify-between border-b border-slate-100 pb-4">
    <div class="flex items-center gap-3">
      <span class="flex h-9 w-9 items-center justify-center rounded-full bg-blue-600 text-white">
        <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="1.8">
          <path d="M12 3 5 6v6c0 4.2 2.8 7.4 7 9 4.2-1.6 7-4.8 7-9V6l-7-3Z" stroke-linejoin="round" />
          <path d="m9 12 2 2 4-4" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </span>
      <div>
        <p class="text-sm font-semibold leading-tight text-slate-900">Claim-AI</p>
        <p class="text-xs text-slate-500">{{ subtitle }}</p>
      </div>
    </div>
    <button class="inline-flex items-center gap-1.5 text-sm font-medium text-slate-500 hover:text-slate-900" @click="handleLogout">
      <svg viewBox="0 0 24 24" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.8">
        <path d="M10 7V5a2 2 0 0 1 2-2h7v18h-7a2 2 0 0 1-2-2v-2" stroke-linecap="round" />
        <path d="M4 12h10M11 8l4 4-4 4" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
      Sign out
    </button>
  </div>
</template>
