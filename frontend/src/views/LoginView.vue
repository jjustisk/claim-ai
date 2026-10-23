<script setup>
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { AlertCircle, ArrowRight, Shield } from 'lucide-vue-next'
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
    error.value =
      err instanceof ApiError
        ? errorText(err, 'Sign-in could not be completed. Please try again.')
        : 'Sign-in could not be completed. Please try again.'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="flex min-h-screen items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100 p-4">
    <div class="w-full max-w-md">
      <div class="mb-8 text-center">
        <div class="mb-4 inline-flex h-16 w-16 items-center justify-center rounded-full bg-blue-600">
          <Shield class="h-8 w-8 text-white" />
        </div>
        <h1 class="text-3xl font-bold text-gray-900">Claim-AI</h1>
        <p class="mt-2 text-gray-600">Enterprise claims assessment platform</p>
      </div>

      <div class="rounded-lg bg-white p-8 shadow-lg">
        <h2 class="mb-6 text-xl font-semibold text-gray-900">
          {{ portal === 'assessor' ? 'Assessor sign in' : 'Customer sign in' }}
        </h2>
        <form class="space-y-4" @submit.prevent="handleSubmit">
          <div>
            <label class="mb-1 block text-sm font-medium text-gray-700" for="email">Email Address</label>
            <input
              id="email"
              v-model="email"
              type="email"
              required
              autocomplete="username"
              :placeholder="portal === 'assessor' ? 'assessor@insurance.com' : 'customer@email.com'"
              class="field"
            />
          </div>
          <div>
            <label class="mb-1 block text-sm font-medium text-gray-700" for="password">Password</label>
            <input
              id="password"
              v-model="password"
              type="password"
              required
              autocomplete="current-password"
              placeholder="••••••••"
              class="field"
            />
          </div>
          <p v-if="error" class="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            <AlertCircle class="mt-0.5 h-4 w-4 shrink-0" />
            <span>{{ error }}</span>
          </p>
          <button type="submit" class="btn-primary w-full py-3 text-base" :disabled="loading">
            {{ loading ? 'Signing in…' : 'Sign in' }}
            <ArrowRight v-if="!loading" class="h-4 w-4" />
          </button>
        </form>

        <div class="mt-6 border-t border-gray-200 pt-6">
          <button
            type="button"
            class="w-full py-2 text-sm text-blue-600 hover:text-blue-700"
            @click="portal = portal === 'assessor' ? 'customer' : 'assessor'"
          >
            {{ portal === 'assessor' ? 'Switch to customer portal' : 'Switch to assessor portal' }}
          </button>
        </div>
      </div>

      <p class="mt-6 text-center text-sm text-gray-600">
        Secure access for authorised claimants and claims assessors.
      </p>
    </div>
  </div>
</template>
