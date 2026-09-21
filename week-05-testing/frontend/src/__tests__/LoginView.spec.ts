import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, type EffectScope } from 'vue'
import { createMemoryHistory, type Router } from 'vue-router'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'

import { isSignedIn, session, signOut } from '@/auth/session'
import { createAppRouter } from '@/router'
import LoginView from '@/views/LoginView.vue'

// Any string is a token to signIn; the page never inspects it.
const TOKEN = 'header.payload.signature'

describe('LoginView', () => {
  let scope: EffectScope
  let router: Router
  let wrapper: VueWrapper | undefined

  beforeEach(async () => {
    signOut()
    scope = effectScope()
    router = scope.run(() => createAppRouter(createMemoryHistory()))!
    await router.push('/login')
  })

  afterEach(() => {
    wrapper?.unmount()
    scope.stop()
    window.location.hash = ''
    vi.restoreAllMocks()
  })

  async function mountWithFragment(fragment: string): Promise<VueWrapper> {
    window.location.hash = fragment
    wrapper = mount(LoginView, { global: { plugins: [router] } })
    await flushPromises()
    return wrapper
  }

  it('offers the Google login link and no message on a plain visit', async () => {
    const page = await mountWithFragment('')

    expect(page.find('a').attributes('href')).toBe('/auth/login')
    expect(page.find('[role="alert"]').exists()).toBe(false)
    expect(isSignedIn.value).toBe(false)
  })

  it('signs in from the callback fragment and moves to the coverages page', async () => {
    await mountWithFragment(`#access_token=${TOKEN}`)

    expect(session.token).toBe(TOKEN)
    // The coverages view is lazy-loaded, so the navigation settles after flushPromises.
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('coverages'))
  })

  it('removes the token from the address bar without disturbing the router state', async () => {
    // As in a browser, the router has already stored its state on the entry the callback lands on.
    // Set after the hash: changing the hash creates a fresh entry whose state is null in jsdom too.
    window.location.hash = `#access_token=${TOKEN}`
    window.history.replaceState({ position: 3 }, '', `${window.location.pathname}${window.location.hash}`)
    const replaceState = vi.spyOn(window.history, 'replaceState')
    const stateBefore = window.history.state
    const pathBefore = window.location.pathname

    wrapper = mount(LoginView, { global: { plugins: [router] } })
    await flushPromises()

    expect(window.location.hash).toBe('')
    expect(replaceState).toHaveBeenCalledWith(stateBefore, '', pathBefore)
  })

  it('shows one failure message when the callback reports an error', async () => {
    const page = await mountWithFragment('#error=login_failed')

    expect(page.find('[role="alert"]').text()).toBe('Login failed. Please try again.')
    expect(isSignedIn.value).toBe(false)
    expect(window.location.hash).toBe('')
    expect(router.currentRoute.value.name).toBe('login')
  })

  it('treats a fragment without a token as a failure', async () => {
    const page = await mountWithFragment('#unexpected=1')

    expect(page.find('[role="alert"]').exists()).toBe(true)
    expect(isSignedIn.value).toBe(false)
  })
})
