<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAuth } from './stores/auth'
import DashboardBar from './components/DashboardBar.vue'

const { state } = useAuth()
const route = useRoute()

const showDashboard = computed(() => state.ready && state.user && !route.meta.public)
const subtitle = computed(() => (state.user?.role === 'assessor' ? 'Assessor workspace' : 'Customer portal'))
</script>

<template>
  <div v-if="!state.ready" class="grid min-h-screen place-items-center bg-white text-slate-500">
    Loading application…
  </div>
  <RouterView v-else-if="!showDashboard" />
  <div v-else class="min-h-screen bg-white">
    <div class="mx-auto max-w-6xl px-6 py-8">
      <DashboardBar :subtitle="subtitle" />
      <RouterView />
    </div>
  </div>
</template>
