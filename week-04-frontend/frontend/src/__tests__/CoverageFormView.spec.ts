import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, type EffectScope } from 'vue'
import { createMemoryHistory, type Router } from 'vue-router'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'

import { ApiError } from '@/api/client'
import { createCoverage, getCoverage, updateCoverage, type Coverage } from '@/api/coverages'
import { signIn, signOut } from '@/auth/session'
import { clearFlash, flash } from '@/notices/flash'
import { createAppRouter } from '@/router'
import CoverageFormView from '@/views/CoverageFormView.vue'

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

describe('CoverageFormView', () => {
  let scope: EffectScope
  let router: Router
  let wrapper: VueWrapper | undefined

  beforeEach(() => {
    vi.mocked(createCoverage).mockReset()
    vi.mocked(updateCoverage).mockReset()
    vi.mocked(getCoverage).mockReset()
    signIn('header.payload.signature')
    scope = effectScope()
    router = scope.run(() => createAppRouter(createMemoryHistory()))!
  })

  afterEach(() => {
    wrapper?.unmount()
    scope.stop()
    signOut()
    clearFlash()
  })

  async function mountAt(path: string): Promise<VueWrapper> {
    await router.push(path)
    wrapper = mount(CoverageFormView, { global: { plugins: [router] } })
    return wrapper
  }

  async function fillValidCoverage(page: VueWrapper): Promise<void> {
    await page.find('#title').setValue('  Apple Inc. ')
    await page.find('#cik').setValue('0000320193')
    await page.find('#ticker').setValue('AAPL')
    await page.find('#status').setValue('active')
  }

  // The detail page is lazy-loaded, so the navigation finishes only once its module has loaded.
  function expectNavigationTo(path: string): Promise<void> {
    return vi.waitFor(() => expect(router.currentRoute.value.path).toBe(path))
  }

  describe('creating', () => {
    it('sends nothing and marks the fields when the input is invalid', async () => {
      const page = await mountAt('/coverages/new')

      await page.find('form').trigger('submit')
      await flushPromises()

      expect(createCoverage).not.toHaveBeenCalled()
      const errors = page.findAll('.field-error').map((node) => node.text())
      expect(errors).toEqual([
        'Title is required.',
        'CIK must be exactly 10 digits, e.g. 0000320193.',
      ])
      expect(router.currentRoute.value.path).toBe('/coverages/new')
    })

    it('sends the cleaned input, shows Saving…, then goes to the new coverage', async () => {
      let finish!: (coverage: Coverage) => void
      vi.mocked(createCoverage).mockReturnValue(new Promise((resolve) => (finish = resolve)))
      const page = await mountAt('/coverages/new')
      await fillValidCoverage(page)

      await page.find('form').trigger('submit')

      expect(createCoverage).toHaveBeenCalledWith({
        title: 'Apple Inc.',
        description: null,
        status: 'active',
        ticker: 'AAPL',
        cik: '0000320193',
      })
      const button = page.find('button[type="submit"]')
      expect(button.text()).toBe('Saving…')
      expect(button.attributes('disabled')).toBeDefined()

      finish(APPLE)
      await expectNavigationTo('/coverages/7')
      // Set after the navigation, so it is still there for the page the user lands on.
      expect(flash.message).toBe('Coverage created.')
    })

    it('sends one request when the form is submitted twice while saving', async () => {
      vi.mocked(createCoverage).mockReturnValue(new Promise(() => {}))
      const page = await mountAt('/coverages/new')
      await fillValidCoverage(page)

      await page.find('form').trigger('submit')
      await page.find('form').trigger('submit')

      expect(createCoverage).toHaveBeenCalledTimes(1)
    })

    it('puts a 422 message under the field the backend named', async () => {
      vi.mocked(createCoverage).mockRejectedValue(
        new ApiError(422, 'Request validation failed', [
          { field: 'body.title', message: 'String should have at most 200 characters' },
          { field: 'body.status', message: "Input should be 'draft', 'active' or 'archived'" },
          { field: 'body.owner_id', message: 'Extra inputs are not permitted' },
        ]),
      )
      const page = await mountAt('/coverages/new')
      await fillValidCoverage(page)

      await page.find('form').trigger('submit')
      await flushPromises()

      expect(page.find('[role="alert"]').text()).toBe('Could not save. Please try again.')
      expect(page.findAll('.field-error').map((node) => node.text())).toEqual([
        'String should have at most 200 characters',
        "Input should be 'draft', 'active' or 'archived'",
      ])
      expect(router.currentRoute.value.path).toBe('/coverages/new')
    })

    it('shows the backend message for a duplicate filer', async () => {
      vi.mocked(createCoverage).mockRejectedValue(new ApiError(409, 'You already cover this filer'))
      const page = await mountAt('/coverages/new')
      await fillValidCoverage(page)

      await page.find('form').trigger('submit')
      await flushPromises()

      expect(page.find('[role="alert"]').text()).toBe('You already cover this filer')
      expect(flash.message).toBeNull()
    })

    it('shows a plain failure message and lets the user try again', async () => {
      vi.mocked(createCoverage).mockRejectedValue(new ApiError(500, 'An unexpected error occurred'))
      const page = await mountAt('/coverages/new')
      await fillValidCoverage(page)

      await page.find('form').trigger('submit')
      await flushPromises()

      expect(page.find('[role="alert"]').text()).toBe('Could not save. Please try again.')
      const button = page.find('button[type="submit"]')
      expect(button.text()).toBe('Save')
      expect(button.attributes('disabled')).toBeUndefined()
    })
  })

  describe('editing', () => {
    it('shows a loading state and no form until the coverage arrives', async () => {
      vi.mocked(getCoverage).mockReturnValue(new Promise(() => {}))
      const page = await mountAt('/coverages/7/edit')

      expect(getCoverage).toHaveBeenCalledWith('7')
      expect(page.find('[role="status"]').text()).toBe('Loading…')
      expect(page.find('form').exists()).toBe(false)
    })

    it('fills the form from the coverage and keeps the cik read-only', async () => {
      vi.mocked(getCoverage).mockResolvedValue(APPLE)
      const page = await mountAt('/coverages/7/edit')
      await flushPromises()

      expect(page.find('h1').text()).toBe('Edit Coverage')
      expect((page.find('#title').element as HTMLInputElement).value).toBe('Apple Inc.')
      expect((page.find('#description').element as HTMLTextAreaElement).value).toBe('')
      expect((page.find('#status').element as HTMLSelectElement).value).toBe('active')
      expect((page.find('#cik').element as HTMLInputElement).value).toBe('0000320193')
      expect(page.find('#cik').attributes('readonly')).toBeDefined()
    })

    it('patches the editable fields only, then goes back to the detail page', async () => {
      vi.mocked(getCoverage).mockResolvedValue(APPLE)
      vi.mocked(updateCoverage).mockResolvedValue({ ...APPLE, title: 'Apple' })
      const page = await mountAt('/coverages/7/edit')
      await flushPromises()

      await page.find('#title').setValue('Apple')
      await page.find('#ticker').setValue('')
      await page.find('form').trigger('submit')
      await expectNavigationTo('/coverages/7')

      expect(updateCoverage).toHaveBeenCalledWith('7', {
        title: 'Apple',
        description: null,
        status: 'active',
        ticker: null,
      })
      expect(createCoverage).not.toHaveBeenCalled()
      expect(flash.message).toBe('Changes saved.')
    })

    it('offers a retry when the coverage cannot be loaded', async () => {
      vi.mocked(getCoverage)
        .mockRejectedValueOnce(new ApiError(0, 'Could not reach the server.'))
        .mockResolvedValueOnce(APPLE)
      const page = await mountAt('/coverages/7/edit')
      await flushPromises()

      expect(page.find('[role="alert"]').text()).toContain('Could not load this coverage.')
      expect(page.find('form').exists()).toBe(false)

      await page.find('button').trigger('click')
      await flushPromises()

      expect(getCoverage).toHaveBeenCalledTimes(2)
      expect((page.find('#title').element as HTMLInputElement).value).toBe('Apple Inc.')
    })
  })
})
