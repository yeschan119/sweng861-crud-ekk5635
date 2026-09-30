import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, type EffectScope } from 'vue'
import { createMemoryHistory, type Router } from 'vue-router'
import { flushPromises } from '@vue/test-utils'

import { signIn, signOut } from '@/auth/session'
import { createAppRouter } from '@/router'

// signIn accepts any string; the token's payload only matters for the displayed email.
const TOKEN = 'header.payload.signature'

describe('router', () => {
  let scope: EffectScope
  let router: Router

  beforeEach(() => {
    signOut()
    // The scope stops this router's session watcher, so routers from earlier tests do not react.
    scope = effectScope()
    router = scope.run(() => createAppRouter(createMemoryHistory()))!
  })

  afterEach(() => {
    scope.stop()
  })

  it('sends a signed-out user from a protected page to /login', async () => {
    await router.push('/coverages')
    expect(router.currentRoute.value.name).toBe('login')
  })

  it('lets a signed-in user open a protected page', async () => {
    signIn(TOKEN)
    await router.push('/coverages')
    expect(router.currentRoute.value.name).toBe('coverages')
  })

  it('sends a signed-in user away from /login', async () => {
    signIn(TOKEN)
    await router.push('/login')
    expect(router.currentRoute.value.name).toBe('coverages')
  })

  it('guards the redirect target of / and unknown paths', async () => {
    await router.push('/')
    expect(router.currentRoute.value.name).toBe('login')

    signIn(TOKEN)
    await router.push('/no-such-page')
    expect(router.currentRoute.value.name).toBe('coverages')
  })

  it('moves to /login when the session is cleared on a protected page', async () => {
    signIn(TOKEN)
    await router.push('/coverages')

    signOut()

    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('login'))
  })

  it('stays on /login when the session is cleared there', async () => {
    await router.push('/login')
    // Signing in on /login, as the callback page will, so the sign-out below is a real change.
    signIn(TOKEN)
    await flushPromises()

    signOut()
    await flushPromises()

    expect(router.currentRoute.value.fullPath).toBe('/login')
  })
})
