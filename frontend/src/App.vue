<script setup>
import { useAuth } from './stores/auth'
import { useRouter, useRoute } from 'vue-router'

const { state, logout } = useAuth()
const router = useRouter()
const route = useRoute()

function handleLogout() {
  logout()
  router.push({ name: 'login' })
}
</script>

<template>
  <div class="min-h-screen bg-slate-50 text-slate-900">
    <header v-if="state.user" class="border-b border-slate-200 bg-white">
      <div class="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
        <div class="flex items-center gap-6">
          <span class="font-semibold">Claim AI</span>
          <nav v-if="state.user.role === 'assessor'" class="flex gap-4 text-sm">
            <RouterLink
              :to="{ name: 'assessor-queue' }"
              class="text-slate-600 hover:text-slate-900"
              :class="{ 'font-medium text-slate-900': route.name?.startsWith('assessor') }"
            >
              Claim queue
            </RouterLink>
          </nav>
          <nav v-else class="flex gap-4 text-sm">
            <RouterLink
              :to="{ name: 'my-claims' }"
              class="text-slate-600 hover:text-slate-900"
              :class="{ 'font-medium text-slate-900': route.name?.startsWith('my-claim') }"
            >
              My claims
            </RouterLink>
          </nav>
        </div>
        <div class="flex items-center gap-3 text-sm text-slate-600">
          <span>{{ state.user.name || state.user.email }}</span>
          <button class="rounded border border-slate-300 px-3 py-1 hover:bg-slate-100" @click="handleLogout">
            Log out
          </button>
        </div>
      </div>
    </header>

    <main class="mx-auto max-w-6xl px-6 py-8">
      <RouterView v-if="state.ready" />
      <p v-else class="text-slate-500">Loading…</p>
    </main>
  </div>
</template>
