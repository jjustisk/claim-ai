<script setup>
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuth, ApiError } from '../stores/auth'
import { errorText } from '../utils/claim'

const email = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)
const portal = ref('assessor')

const router = useRouter()
const route = useRoute()
const { login } = useAuth()

async function handleSubmit() {
  error.value = ''
  loading.value = true
  try {
    const user = await login(email.value, password.value)
    const redirect = route.query.redirect
    if (typeof redirect === 'string' && redirect.startsWith('/')) router.push(redirect)
    else router.push(user.role === 'assessor' ? { name: 'assessor-queue' } : { name: 'my-claims' })
  } catch (err) {
    error.value = err instanceof ApiError ? errorText(err, 'The email or password is incorrect.') : 'Sign-in could not be completed. Please try again.'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="grid min-h-screen place-items-center bg-white px-4 py-10">
    <div class="w-full max-w-md text-center">
      <div class="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-blue-600 text-white shadow-lg shadow-blue-600/30">
        <svg viewBox="0 0 24 24" class="h-7 w-7" fill="none" stroke="currentColor" stroke-width="1.8">
          <path d="M12 3 5 6v6c0 4.2 2.8 7.4 7 9 4.2-1.6 7-4.8 7-9V6l-7-3Z" stroke-linejoin="round" />
          <path d="m9 12 2 2 4-4" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </div>
      <h1 class="text-3xl font-extrabold tracking-tight text-slate-900">Claim-AI</h1>
      <p class="mt-1 text-sm text-slate-500">Enterprise claims assessment platform</p>

      <form class="mt-8 rounded-2xl bg-white px-8 py-7 text-left shadow-xl shadow-slate-200/80" @submit.prevent="handleSubmit">
        <h2 class="mb-5 text-lg font-bold text-slate-900">
          {{ portal === 'assessor' ? 'Assessor sign in' : 'Customer sign in' }}
        </h2>
        <label class="mb-1.5 block text-sm font-medium text-slate-700" for="email">Email Address</label>
        <input
          id="email"
          v-model="email"
          type="email"
          required
          :placeholder="portal === 'assessor' ? 'assessor@insurance.com' : 'customer@email.com'"
          class="field mb-4"
        />
        <label class="mb-1.5 block text-sm font-medium text-slate-700" for="password">Password</label>
        <input id="password" v-model="password" type="password" required placeholder="••••••••" class="field" />
        <p v-if="error" class="mt-3 text-sm text-red-600">{{ error }}</p>
        <button type="submit" class="btn-primary mt-5 w-full" :disabled="loading">
          {{ loading ? 'Signing in…' : 'Sign in' }}
        </button>
        <button
          type="button"
          class="mt-4 w-full text-sm font-medium text-blue-600 hover:text-blue-700"
          @click="portal = portal === 'assessor' ? 'customer' : 'assessor'"
        >
          {{ portal === 'assessor' ? 'Switch to customer portal' : 'Switch to assessor portal' }}
        </button>
      </form>

      <p class="mx-auto mt-8 max-w-sm text-xs leading-relaxed text-slate-400">
        Secure access for authorised claimants and claims assessors.
      </p>
    </div>
  </div>
</template>
