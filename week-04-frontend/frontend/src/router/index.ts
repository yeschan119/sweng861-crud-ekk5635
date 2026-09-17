import { watch } from 'vue'
import { createRouter, type RouteRecordRaw, type RouterHistory } from 'vue-router'

import { isSignedIn } from '@/auth/session'

// Protected unless marked public, so a route added later cannot become public by omission.
const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { public: true },
  },
  {
    path: '/coverages',
    name: 'coverages',
    component: () => import('@/views/CoveragesView.vue'),
  },
  { path: '/', redirect: { name: 'coverages' } },
  { path: '/:unknownPath(.*)*', redirect: { name: 'coverages' } },
]

// History is a parameter so tests can pass memory history instead of the browser's.
export function createAppRouter(history: RouterHistory) {
  const router = createRouter({ history, routes })

  router.beforeEach((to) => {
    if (to.meta.public !== true && !isSignedIn.value) return { name: 'login' }
    if (to.name === 'login' && isSignedIn.value) return { name: 'coverages' }
    return true
  })

  // Guards run only on navigation; this catches a session cleared while staying on a page (e.g. a 401).
  watch(isSignedIn, (signedIn) => {
    if (!signedIn && router.currentRoute.value.meta.public !== true) {
      void router.replace({ name: 'login' })
    }
  })

  return router
}
