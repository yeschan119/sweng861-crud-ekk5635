import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { createCoverage, getCoverage, listCoverages, updateCoverage } from '@/api/coverages'
import { signIn, signOut } from '@/auth/session'

// The wrappers are one line each; what matters is the verb, the path and the body each one sends.
describe('api/coverages', () => {
  const fetchMock = vi.fn<typeof fetch>()

  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockResolvedValue(new Response('{"id": 7}', { status: 200 }))
    signIn('header.payload.signature')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    signOut()
  })

  function lastCall(): { path: string; init: RequestInit } {
    const [path, init] = fetchMock.mock.lastCall as [string, RequestInit]
    return { path, init }
  }

  it('lists with GET /api/coverages', async () => {
    await listCoverages()
    expect(lastCall()).toMatchObject({ path: '/api/coverages', init: { method: 'GET' } })
  })

  it('reads one by id, URL-encoding the id', async () => {
    await getCoverage('a/b')
    expect(lastCall().path).toBe('/api/coverages/a%2Fb')
  })

  it('creates with POST and the full input as JSON', async () => {
    const input = { title: 'Apple', description: null, status: 'draft' as const, ticker: null, cik: '0000320193' }
    await createCoverage(input)
    const { path, init } = lastCall()
    expect(path).toBe('/api/coverages')
    expect(init.method).toBe('POST')
    expect(JSON.parse(String(init.body))).toEqual(input)
  })

  it('updates with PATCH to the id and never sends a cik', async () => {
    await updateCoverage('7', { title: 'Apple', description: null, status: 'active', ticker: 'AAPL' })
    const { path, init } = lastCall()
    expect(path).toBe('/api/coverages/7')
    expect(init.method).toBe('PATCH')
    expect(JSON.parse(String(init.body))).not.toHaveProperty('cik')
  })
})
