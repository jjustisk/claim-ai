<script setup>
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight, Camera, ClipboardCheck, FileSearch, Shield, UserCheck } from 'lucide-vue-next'
import { useAuth } from '../stores/auth'

const router = useRouter()
const { state } = useAuth()

// A signed-in user has no use for the welcome page - send them home.
onMounted(() => {
  if (state.user) {
    router.replace(state.user.role === 'assessor' ? { name: 'assessor-queue' } : { name: 'my-claims' })
  }
})

const steps = [
  {
    icon: Camera,
    title: 'Submit your claim',
    body: 'Tell us what happened and upload photos of the damage. You can save a draft and finish later.',
  },
  {
    icon: FileSearch,
    title: 'Automated assessment',
    body: 'Your photos and details are checked against your policy wording and a recommendation is prepared.',
  },
  {
    icon: UserCheck,
    title: 'Assessor review',
    body: 'A licensed assessor reviews the recommendation. A person makes the final decision.',
  },
  {
    icon: ClipboardCheck,
    title: 'Track your outcome',
    body: 'Follow each stage of your claim and see the outcome as soon as it is decided.',
  },
]
</script>

<template>
  <div class="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
    <header class="mx-auto flex max-w-5xl items-center justify-between px-4 py-5">
      <div class="flex items-center gap-2">
        <span class="inline-flex h-9 w-9 items-center justify-center rounded-full bg-blue-600">
          <Shield class="h-5 w-5 text-white" />
        </span>
        <span class="text-lg font-bold text-gray-900">Claim-AI</span>
      </div>
      <router-link :to="{ name: 'login' }" class="text-sm font-medium text-blue-600 hover:text-blue-700">
        Sign in
      </router-link>
    </header>

    <main class="mx-auto max-w-5xl px-4 pb-16">
      <section class="py-12 text-center sm:py-20">
        <h1 class="text-4xl font-bold tracking-tight text-gray-900 sm:text-5xl">
          Welcome to Claim-AI
        </h1>
        <p class="mx-auto mt-4 max-w-2xl text-lg text-gray-600">
          Lodge an insurance claim, see where it is up to, and get a clear outcome. Automated checks help
          assessors work faster, and every decision is made by a person.
        </p>
        <div class="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <router-link :to="{ name: 'login', query: { portal: 'customer' } }" class="btn-primary w-full px-6 py-3 text-base sm:w-auto">
            Customer sign in
            <ArrowRight class="h-4 w-4" />
          </router-link>
          <router-link
            :to="{ name: 'login', query: { portal: 'assessor' } }"
            class="inline-flex w-full items-center justify-center rounded-lg border border-gray-300 bg-white px-6 py-3 sm:w-auto text-base font-medium text-gray-700 transition-colors hover:bg-gray-50"
          >
            Assessor sign in
          </router-link>
        </div>
      </section>

      <section aria-labelledby="how-it-works">
        <h2 id="how-it-works" class="mb-6 text-center text-xl font-semibold text-gray-900">How it works</h2>
        <ol class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <li v-for="(step, index) in steps" :key="step.title" class="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <div class="mb-3 flex items-center gap-3">
              <span class="inline-flex h-10 w-10 items-center justify-center rounded-full bg-blue-50 text-blue-600">
                <component :is="step.icon" class="h-5 w-5" />
              </span>
              <span class="text-xs font-semibold tracking-wide text-gray-400">STEP {{ index + 1 }}</span>
            </div>
            <h3 class="font-semibold text-gray-900">{{ step.title }}</h3>
            <p class="mt-1 text-sm leading-relaxed text-gray-600">{{ step.body }}</p>
          </li>
        </ol>
      </section>

      <p class="mt-12 text-center text-sm text-gray-600">
        Secure access for authorised claimants and claims assessors.
      </p>
    </main>
  </div>
</template>
