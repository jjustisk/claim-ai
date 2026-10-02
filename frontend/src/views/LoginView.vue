<script setup>
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuth, ApiError } from '../stores/auth'

const email = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

const router = useRouter()
const route = useRoute()
const { login } = useAuth()

async function handleSubmit() {
  error.value = ''
  loading.value = true
  try {
    const user = await login(email.value, password.value)
    const redirect = route.query.redirect
    if (redirect) router.push(redirect)
    else router.push(user.role === 'assessor' ? { name: 'assessor-queue' } : { name: 'my-claims' })
  } catch (err) {
    error.value = err instanceof ApiError ? err.detail : 'Something went wrong. Try again.'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="mx-auto mt-24 max-w-sm">
    <h1 class="mb-6 text-xl font-semibold">Sign in to Claim AI</h1>
    <form class="space-y-4" @submit.prevent="handleSubmit">
      <div>
        <label class="mb-1 block text-sm text-slate-600" for="email">Email</label>
        <input
          id="email"
          v-model="email"
          type="email"
          required
          class="w-full rounded border border-slate-300 px-3 py-2 text-sm"
        />
      </div>
      <div>
        <label class="mb-1 block text-sm text-slate-600" for="password">Password</label>
        <input
          id="password"
          v-model="password"
          type="password"
          required
          class="w-full rounded border border-slate-300 px-3 py-2 text-sm"
        />
      </div>
      <p v-if="error" class="text-sm text-red-600">{{ error }}</p>
      <button
        type="submit"
        :disabled="loading"
        class="w-full rounded bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
      >
        {{ loading ? 'Signing in…' : 'Sign in' }}
      </button>
    </form>
  </div>
</template>
