import { createRouter, createWebHistory } from 'vue-router'
import { useAuth } from '../stores/auth'

const routes = [
  { path: '/login', name: 'login', component: () => import('../views/LoginView.vue'), meta: { public: true } },

  // Assessor
  {
    path: '/assessor',
    name: 'assessor-queue',
    component: () => import('../views/assessor/QueueView.vue'),
    meta: { role: 'assessor' },
  },
  {
    path: '/assessor/claims/:id',
    name: 'assessor-claim-detail',
    component: () => import('../views/assessor/ClaimDetailView.vue'),
    meta: { role: 'assessor' },
    props: true,
  },

  // Claimant
  {
    path: '/my-claims',
    name: 'my-claims',
    component: () => import('../views/customer/MyClaimsView.vue'),
    meta: { role: 'claimant' },
  },
  {
    path: '/my-claims/new',
    name: 'my-claims-new',
    component: () => import('../views/customer/ClaimFormView.vue'),
    meta: { role: 'claimant' },
  },
  {
    path: '/my-claims/draft/:draftId',
    name: 'my-claims-draft',
    component: () => import('../views/customer/ClaimFormView.vue'),
    meta: { role: 'claimant' },
    props: true,
  },
  {
    path: '/my-claims/:id',
    name: 'my-claim-status',
    component: () => import('../views/customer/ClaimStatusView.vue'),
    meta: { role: 'claimant' },
    props: true,
  },

  { path: '/', redirect: () => '/login' },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  const { state, restoreSession } = useAuth()
  if (!state.ready) await restoreSession()

  if (to.meta.public) return true

  if (!state.user) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  if (to.meta.role && to.meta.role !== state.user.role) {
    // Logged in, wrong role — send them to their own home instead of a dead end.
    return state.user.role === 'assessor' ? { name: 'assessor-queue' } : { name: 'my-claims' }
  }

  return true
})
