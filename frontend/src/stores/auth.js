import { reactive } from 'vue'
import { api, setToken, ApiError } from '../api/client'

const state = reactive({
  user: null, // { id, role, email, name, phone }
  ready: false, // true once we've checked for an existing session
})

async function restoreSession() {
  const token = localStorage.getItem('claim_ai_token')
  if (!token) {
    state.ready = true
    return
  }
  try {
    state.user = await api.me()
  } catch {
    setToken(null)
    state.user = null
  } finally {
    state.ready = true
  }
}

async function login(email, password) {
  const { access_token } = await api.login(email, password)
  setToken(access_token)
  state.user = await api.me()
  return state.user
}

function logout() {
  setToken(null)
  state.user = null
}

export function useAuth() {
  return { state, login, logout, restoreSession }
}

export { ApiError }
