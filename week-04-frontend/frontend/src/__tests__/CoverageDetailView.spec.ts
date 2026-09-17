import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, type EffectScope } from 'vue'
import { createMemoryHistory, type Router } from 'vue-router'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'

import { ApiError } from '@/api/client'
import { getCoverage, type Coverage } from '@/api/coverages'
import { signIn, signOut } from '@/auth/session'
import { createAppRouter } from '@/router'
import CoverageDetailView from '@/views/CoverageDetailView.vue'

vi.mock('@/api/coverages')

const APPLE: Coverage = {
  id: 7,
  title: 'Apple Inc.',
  description: null,
  status: 'active',
  ticker: 'AAPL',
  cik: '0000320193',
  created_at: '2026-09-18T00:00:00Z',
  updated_at: '2026-09-18T01:02:03Z',
}

describe('CoverageDetailView', () => {
  let scope: EffectScope
  let router: Router
  let wrapper: VueWrapper | undefined

  beforeEach(async () => {
    vi.mocked(getCoverage).mockReset()
    signIn('header.payload.signature')
    scope = effectScope()
    router = scope.run(() => createAppRouter(createMemoryHistory()))!
    // The id comes from the route, so the page is mounted on a real route rather than a mocked one.
    await router.push('/coverages/7')
  })

  afterEach(() => {
    wrapper?.unmount()
    scope.stop()
    signOut()
  })

  function mountDetail(): VueWrapper {
    wrapper = mount(CoverageDetailView, { global: { plugins: [router] } })
    return wrapper
  }

  it('shows a loading state until the coverage arrives', () => {
    vi.mocked(getCoverage).mockReturnValue(new Promise(() => {}))
    const page = mountDetail()

    expect(page.find('[role="status"]').text()).toBe('Loading…')
    expect(page.find('dl').exists()).toBe(false)
  })

  it('asks for the id in the route and shows the coverage', async () => {
    vi.mocked(getCoverage).mockResolvedValue(APPLE)
    const page = mountDetail()
    await flushPromises()

    expect(getCoverage).toHaveBeenCalledWith('7')
    expect(page.find('h1').text()).toBe('Apple Inc.')
    expect(page.find('dl').text()).toContain('AAPL')
    expect(page.find('dl').text()).toContain('0000320193')
    expect(page.find('a').attributes('href')).toBe('/coverages')
  })

  it('tells the user when the item does not exist', async () => {
    vi.mocked(getCoverage).mockRejectedValue(new ApiError(404, 'Coverage not found.'))
    const page = mountDetail()
    await flushPromises()

    expect(page.find('[role="alert"]').text()).toBe('This item does not exist or has been deleted.')
    expect(page.find('button').exists()).toBe(false)
  })

  it('tells the user when the item is not theirs to see', async () => {
    vi.mocked(getCoverage).mockRejectedValue(new ApiError(403, 'Forbidden.'))
    const page = mountDetail()
    await flushPromises()

    expect(page.find('[role="alert"]').text()).toBe('You are not authorized to view this item.')
    expect(page.find('button').exists()).toBe(false)
  })

  it('offers a retry for any other failure', async () => {
    vi.mocked(getCoverage)
      .mockRejectedValueOnce(new ApiError(0, 'Could not reach the server.'))
      .mockResolvedValueOnce(APPLE)
    const page = mountDetail()
    await flushPromises()

    expect(page.find('[role="alert"]').text()).toContain('Could not load this coverage.')

    await page.find('button').trigger('click')
    await flushPromises()

    expect(getCoverage).toHaveBeenCalledTimes(2)
    expect(page.find('h1').text()).toBe('Apple Inc.')
  })

  it('loads the new coverage when the route moves to another id', async () => {
    vi.mocked(getCoverage)
      .mockResolvedValueOnce(APPLE)
      .mockResolvedValueOnce({ ...APPLE, id: 8, title: 'Microsoft Corporation' })
    const page = mountDetail()
    await flushPromises()
    expect(page.find('h1').text()).toBe('Apple Inc.')

    await router.push('/coverages/8')
    await flushPromises()

    expect(getCoverage).toHaveBeenLastCalledWith('8')
    expect(page.find('h1').text()).toBe('Microsoft Corporation')
  })
})
