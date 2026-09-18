import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest'

import { ApiError, apiRequest } from '@/api/client'
import { createCoverage, getCoverage, listCoverages, type Coverage } from '@/api/coverages'
import { session, signIn, signOut } from '@/auth/session'

// The app calls relative paths behind the Vite proxy; here they go straight to the gateway.
const API_BASE_URL = process.env.API_BASE_URL ?? 'http://localhost:8000'
// Minted by the backend for an existing user (README); never committed.
const TOKEN = process.env.TEST_SESSION_TOKEN

const realFetch = globalThis.fetch
vi.stubGlobal('fetch', (input: string, init?: RequestInit) => realFetch(new URL(input, API_BASE_URL), init))

// A cik that no real filer has, so the run cannot collide with a coverage the user keeps.
const testCik = `99${String(Date.now()).slice(-8)}`
let created: Coverage | null = null

describe.skipIf(!TOKEN)('api client against the running backend', () => {
  beforeAll(async () => {
    const health = await realFetch(new URL('/health', API_BASE_URL)).catch(() => null)
    if (!health?.ok) throw new Error(`Backend not reachable at ${API_BASE_URL}; start the Week 4 stack first.`)
  })

  // Removes this run's row and any left by a run that died before its afterAll (same 99… cik shape).
  afterAll(async () => {
    signIn(TOKEN!)
    const leftovers = (await listCoverages()).filter((c) => c.cik.startsWith('99'))
    for (const row of leftovers) await apiRequest(`/api/coverages/${row.id}`, { method: 'DELETE' })
    signOut()
  })

  it('answers 401 when signed out, and the client clears the session', async () => {
    signOut()
    await expect(listCoverages()).rejects.toMatchObject({ status: 401 })
    await expect(listCoverages()).rejects.toBeInstanceOf(ApiError)
    expect(session.token).toBeNull()
  })

  it('creates, reads and lists a coverage with a valid session', async () => {
    signIn(TOKEN!)

    created = await createCoverage({
      title: 'Integration test filer',
      description: 'Created by client.integration.spec.ts; deleted at the end of the run.',
      status: 'draft',
      ticker: null,
      cik: testCik,
    })
    expect(created.id).toBeGreaterThan(0)
    expect(created.cik).toBe(testCik)

    const read = await getCoverage(String(created.id))
    expect(read).toMatchObject({ id: created.id, title: 'Integration test filer', status: 'draft' })

    const all = await listCoverages()
    expect(all.map((c) => c.id)).toContain(created.id)
  })

  it('refuses a second coverage for the same filer with 409', async () => {
    signIn(TOKEN!)
    await expect(
      createCoverage({ title: 'Duplicate', description: null, status: 'draft', ticker: null, cik: testCik }),
    ).rejects.toMatchObject({ status: 409, message: 'You already cover this filer' })
  })
})
