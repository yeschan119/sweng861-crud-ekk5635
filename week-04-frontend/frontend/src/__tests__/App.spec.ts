import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, type EffectScope } from 'vue'
import { createMemoryHistory, type Router } from 'vue-router'
import { mount, type VueWrapper } from '@vue/test-utils'

import App from '@/App.vue'
import { isSignedIn, signIn, signOut } from '@/auth/session'
import { createAppRouter } from '@/router'

// Encoded the way the backend's PyJWT does: base64url, unpadded. Only the payload is read.
function makeToken(claims: object): string {
  const payload = Buffer.from(JSON.stringify(claims)).toString('base64url')
  return `header.${payload}.signature`
}

describe('App shell', () => {
  let scope: EffectScope
  let router: Router
  let wrapper: VueWrapper | undefined

  beforeEach(() => {
    signOut()
    // The scope stops this router's session watcher, so routers from earlier tests do not react.
    scope = effectScope()
    router = scope.run(() => createAppRouter(createMemoryHistory()))!
  })

  afterEach(() => {
    wrapper?.unmount()
    scope.stop()
  })

  async function mountAt(path: string): Promise<VueWrapper> {
    await router.push(path)
    wrapper = mount(App, { global: { plugins: [router] } })
    return wrapper
  }

  it('shows the app name, the entity link and a login link when signed out', async () => {
    const shell = await mountAt('/login')

    expect(shell.find('header').exists()).toBe(true)
    expect(shell.text()).toContain('SWENG 861 Coverages')
    expect(shell.find('nav a').text()).toBe('My Coverages')
    expect(shell.find('nav a').attributes('href')).toBe('/coverages')
    expect(shell.find('a[href="/login"]').text()).toBe('Log in')
    expect(shell.text()).not.toContain('Logged in')
    expect(shell.find('button').exists()).toBe(false)
  })

  it('shows the email and a sign-out button when signed in', async () => {
    signIn(makeToken({ email: 'alice@example.com' }))
    const shell = await mountAt('/coverages')

    expect(shell.find('header').exists()).toBe(true)
    expect(shell.text()).toContain('Logged in as alice@example.com')
    expect(shell.find('button').text()).toBe('Sign out')
    expect(shell.find('a[href="/login"]').exists()).toBe(false)
  })

  it('still says logged in when the token carries no email', async () => {
    signIn(makeToken({ sub: 'user-1' }))
    const shell = await mountAt('/coverages')

    expect(shell.text()).toContain('Logged in')
    expect(shell.text()).not.toContain('Logged in as')
  })

  it('renders the current page inside the shell', async () => {
    signIn(makeToken({ email: 'alice@example.com' }))
    const shell = await mountAt('/coverages')

    expect(shell.find('main h1').text()).toBe('My Coverages')
  })

  it('mounts a fresh page when two routes share a component', async () => {
    signIn(makeToken({ email: 'alice@example.com' }))
    // Both form routes render CoverageFormView; without a key the edit instance would be reused.
    const shell = await mountAt('/coverages/7/edit')
    expect(shell.find('main h1').text()).toBe('Edit Coverage')

    await router.push('/coverages/new')
    await vi.waitFor(() => expect(shell.find('main h1').text()).toBe('New Coverage'))
    expect(shell.find('#cik').attributes('readonly')).toBeUndefined()
  })

  it('clears the session on sign out, and the router moves to /login', async () => {
    signIn(makeToken({ email: 'alice@example.com' }))
    const shell = await mountAt('/coverages')

    await shell.find('button').trigger('click')

    expect(isSignedIn.value).toBe(false)
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('login'))
    expect(shell.find('a[href="/login"]').text()).toBe('Log in')
  })
})
