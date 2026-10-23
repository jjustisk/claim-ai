<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { LogOut, Shield, User } from 'lucide-vue-next'
import { useAuth } from '../stores/auth'

defineProps({
  subtitle: { type: String, default: 'Dashboard' },
  widthClass: { type: String, default: 'max-w-7xl' },
})

const { state, logout } = useAuth()
const router = useRouter()

const isAssessor = computed(() => state.user?.role === 'assessor')
const home = computed(() => ({ name: isAssessor.value ? 'assessor-queue' : 'my-claims' }))

function handleLogout() {
  logout()
  router.push({ name: 'login' })
}
</script>

<template>
  <header class="border-b border-gray-200 bg-white">
    <div class="mx-auto px-4 py-4 sm:px-6 lg:px-8" :class="widthClass">
      <div class="flex items-center justify-between gap-4">
        <RouterLink :to="home" class="flex min-w-0 items-center gap-2">
          <Shield class="h-8 w-8 shrink-0 text-blue-600" />
          <div class="min-w-0">
            <p class="text-xl font-semibold leading-tight text-gray-900">Claim-AI</p>
            <p class="text-sm text-gray-500">{{ subtitle }}</p>
          </div>
        </RouterLink>
        <div class="flex items-center gap-2 sm:gap-4">
          <div
            v-if="!isAssessor && state.user?.email"
            class="hidden items-center gap-2 rounded-lg bg-gray-100 px-3 py-1.5 sm:flex"
          >
            <User class="h-4 w-4 text-gray-600" />
            <span class="max-w-[16rem] truncate text-sm text-gray-700">{{ state.user.email }}</span>
          </div>
          <button
            type="button"
            class="inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-gray-600 transition-colors hover:text-gray-900"
            @click="handleLogout"
          >
            <LogOut class="h-4 w-4" />
            Logout
          </button>
        </div>
      </div>
    </div>
  </header>
</template>
