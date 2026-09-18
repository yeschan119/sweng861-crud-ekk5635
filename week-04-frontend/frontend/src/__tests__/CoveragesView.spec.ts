import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { RouterLinkStub, flushPromises, mount, type VueWrapper } from '@vue/test-utils'

import { ApiError } from '@/api/client'
import { listCoverages, type Coverage } from '@/api/coverages'
import CoveragesView from '@/views/CoveragesView.vue'

vi.mock('@/api/coverages')

const APPLE: Coverage = {
  id: 1,
  title: 'Apple Inc.',
  description: null,
  status: 'active',
  ticker: 'AAPL',
  cik: '0000320193',
  created_at: '2026-09-18T00:00:00Z',
  updated_at: '2026-09-18T01:02:03Z',
}
const MICROSOFT: Coverage = { ...APPLE, id: 2, title: 'Microsoft Corporation', ticker: null, status: 'draft' }

describe('CoveragesView', () => {
  let wrapper: VueWrapper | undefined

  beforeEach(() => {
    vi.mocked(listCoverages).mockReset()
  })

  afterEach(() => {
    wrapper?.unmount()
  })

  function mountList(): VueWrapper {
    wrapper = mount(CoveragesView, { global: { stubs: { RouterLink: RouterLinkStub } } })
    return wrapper
  }

  it('shows a loading state until the list arrives', () => {
    vi.mocked(listCoverages).mockReturnValue(new Promise(() => {}))
    const page = mountList()

    expect(page.find('[role="status"]').text()).toBe('Loading…')
    expect(page.find('table').exists()).toBe(false)
  })

  it('lists each coverage with a link to its detail page', async () => {
    vi.mocked(listCoverages).mockResolvedValue([APPLE, MICROSOFT])
    const page = mountList()
    await flushPromises()

    const rows = page.findAll('tbody tr')
    expect(rows).toHaveLength(2)
    expect(rows[0]!.text()).toContain('Apple Inc.')
    expect(rows[0]!.text()).toContain('AAPL')
    expect(rows[0]!.text()).toContain('2026-09-18')
    expect(rows[1]!.text()).toContain('—')

    const links = page.findAllComponents(RouterLinkStub)
    expect(links[0]!.props('to')).toEqual({ name: 'coverage-detail', params: { id: 1 } })
    expect(links[1]!.props('to')).toEqual({ name: 'coverage-detail', params: { id: 2 } })
    expect(page.find('[role="status"]').exists()).toBe(false)
  })

  it('offers a link to create a coverage, even when the list is empty', async () => {
    vi.mocked(listCoverages).mockResolvedValue([])
    const page = mountList()
    await flushPromises()

    const links = page.findAllComponents(RouterLinkStub)
    expect(links).toHaveLength(1)
    expect(links[0]!.props('to')).toEqual({ name: 'coverage-new' })
    expect(links[0]!.text()).toBe('New coverage')
  })

  it('says so when the list is empty', async () => {
    vi.mocked(listCoverages).mockResolvedValue([])
    const page = mountList()
    await flushPromises()

    expect(page.text()).toContain('No coverages yet.')
    expect(page.find('table').exists()).toBe(false)
  })

  it('shows an error with a retry that loads again', async () => {
    vi.mocked(listCoverages)
      .mockRejectedValueOnce(new ApiError(0, 'Could not reach the server.'))
      .mockResolvedValueOnce([APPLE])
    const page = mountList()
    await flushPromises()

    expect(page.find('[role="alert"]').text()).toContain('Could not load your coverages.')
    expect(page.find('table').exists()).toBe(false)

    await page.find('button').trigger('click')
    await flushPromises()

    expect(listCoverages).toHaveBeenCalledTimes(2)
    expect(page.find('[role="alert"]').exists()).toBe(false)
    expect(page.findAll('tbody tr')).toHaveLength(1)
  })
})
