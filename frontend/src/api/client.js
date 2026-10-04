const BASE = import.meta.env.VITE_API_BASE_URL || '/api'

function getToken() {
  return localStorage.getItem('claim_ai_token')
}

export function setToken(token) {
  if (token) localStorage.setItem('claim_ai_token', token)
  else localStorage.removeItem('claim_ai_token')
}

class ApiError extends Error {
  constructor(status, detail) {
    super(typeof detail === 'string' ? detail : 'Request failed')
    this.status = status
    this.detail = detail
  }
}

async function request(path, { method = 'GET', body, form, formData, headers = {} } = {}) {
  const token = getToken()
  const opts = { method, headers: { ...headers } }

  if (token) opts.headers.Authorization = `Bearer ${token}`

  if (formData) {
    opts.body = formData
  } else if (form) {
    // OAuth2PasswordRequestForm on the backend expects x-www-form-urlencoded, not JSON.
    opts.headers['Content-Type'] = 'application/x-www-form-urlencoded'
    opts.body = new URLSearchParams(form).toString()
  } else if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }

  const res = await fetch(`${BASE}${path}`, opts)

  if (res.status === 204) return null

  const contentType = res.headers.get('content-type') || ''
  const data = contentType.includes('application/json') ? await res.json() : await res.text()

  if (!res.ok) {
    const detail = data && typeof data === 'object' ? data.detail : data
    throw new ApiError(res.status, detail || `Request failed (${res.status})`)
  }
  return data
}

export const api = {
  // auth
  login: (email, password) =>
    request('/auth/login', { method: 'POST', form: { username: email, password } }),
  me: () => request('/auth/me'),

  // assessor
  claimCounts: () => request('/claims/counts'),
  claimsList: (status) => request(`/claims/${status ? `?status=${encodeURIComponent(status)}` : ''}`),
  claimDetail: (id) => request(`/claims/${id}`),
  claimDecisionBrief: (id) => request(`/claims/${id}/decision-brief`),
  reviewClaim: (id, payload) => request(`/claims/${id}/review`, { method: 'POST', body: payload }),

  // claimant
  myClaims: () => request('/claims/mine'),
  myClaimDetail: (id) => request(`/claims/mine/${id}`),
  policies: () => request('/policies/'),
  formOptions: () => request('/claims/form-options'),
  submitClaim: (formData) => request('/claims/', { method: 'POST', formData }),
  deleteDraft: (claimId) => request(`/claims/${claimId}`, { method: 'DELETE' }),

  // shared
  documentUrl: (docId) => `${BASE}/claims/documents/${docId}`,
  async documentBlob(docId) {
    const token = getToken()
    const res = await fetch(`${BASE}/claims/documents/${docId}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!res.ok) throw new ApiError(res.status, 'Could not open this file.')
    const blob = await res.blob()
    return { url: URL.createObjectURL(blob), type: blob.type || res.headers.get('content-type') || '' }
  },
}

export { ApiError }
