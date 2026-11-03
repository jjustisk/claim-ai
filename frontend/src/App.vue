<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAuth } from './stores/auth'
import DashboardBar from './components/DashboardBar.vue'

const { state } = useAuth()
const route = useRoute()

const showDashboard = computed(() => state.ready && state.user && !route.meta.public)
const isAssessor = computed(() => state.user?.role === 'assessor')
const subtitle = computed(() => (isAssessor.value ? 'Assessor Dashboard' : 'Customer Portal'))
const widthClass = computed(() => (isAssessor.value ? 'max-w-7xl' : 'max-w-4xl'))
</script>

<template>
  <div v-if="!state.ready" class="grid min-h-screen place-items-center bg-gray-50 text-sm text-gray-500">
    Loading application…
  </div>
  <RouterView v-else-if="!showDashboard" />
  <div v-else class="min-h-screen bg-gray-50">
    <DashboardBar :subtitle="subtitle" :width-class="widthClass" />
    <main class="mx-auto px-4 py-8 sm:px-6 lg:px-8" :class="widthClass">
      <RouterView />
    </main>
  </div>
</template>
