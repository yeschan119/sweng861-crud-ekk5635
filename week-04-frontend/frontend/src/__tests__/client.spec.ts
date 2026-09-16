import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest'

import { ApiError, apiRequest, NETWORK_ERROR_STATUS } from '@/api/client'
import { isSignedIn, session, signIn, signOut } from '@/auth/session'

const TOKEN = 'header.payload.signature'

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

type FetchMock = Mock<typeof fetch>

function stubFetch(response: Response): FetchMock {
  const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(response)
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function sentInit(fetchMock: FetchMock): RequestInit {
  return fetchMock.mock.calls[0]?.[1] ?? {}
}

function sentHeaders(fetchMock: FetchMock): Record<string, string> {
  return sentInit(fetchMock).headers as Record<string, string>
}

async function captureError(request: Promise<unknown>): Promise<ApiError> {
  const error = await request.catch((caught: unknown) => caught)
  expect(error).toBeInstanceOf(ApiError)
  return error as ApiError
}

describe('apiRequest', () => {
  beforeEach(() => {
    signOut()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('attaches the bearer token when signed in', async () => {
    const fetchMock = stubFetch(jsonResponse(200, []))
    signIn(TOKEN)

    await apiRequest('/api/coverages')

    expect(sentHeaders(fetchMock).Authorization).toBe(`Bearer ${TOKEN}`)
  })

  it('sends no Authorization header when signed out', async () => {
    const fetchMock = stubFetch(jsonResponse(200, []))

    await apiRequest('/api/coverages')

    expect(sentHeaders(fetchMock)).not.toHaveProperty('Authorization')
  })

  it('sends the method and a JSON body', async () => {
    const fetchMock = stubFetch(jsonResponse(201, { id: 1 }))

    await apiRequest('/api/coverages', { method: 'POST', body: { cik: '0000320193' } })

    const init = sentInit(fetchMock)
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/coverages')
    expect(init.method).toBe('POST')
    expect(init.body).toBe('{"cik":"0000320193"}')
    expect(sentHeaders(fetchMock)['Content-Type']).toBe('application/json')
  })

  it('returns the parsed JSON of a successful response', async () => {
    stubFetch(jsonResponse(200, [{ id: 1 }]))

    await expect(apiRequest('/api/coverages')).resolves.toEqual([{ id: 1 }])
  })

  it('returns undefined for 204 No Content', async () => {
    stubFetch(new Response(null, { status: 204 }))

    await expect(apiRequest('/api/coverages/1', { method: 'DELETE' })).resolves.toBeUndefined()
  })

  it('signs out and throws on 401', async () => {
    stubFetch(jsonResponse(401, { error: 'Unauthorized', message: 'Invalid or expired token' }))
    signIn(TOKEN)

    const error = await captureError(apiRequest('/api/coverages'))

    expect(error.status).toBe(401)
    expect(error.message).toBe('Invalid or expired token')
    expect(isSignedIn.value).toBe(false)
  })

  it('keeps the session and throws on 403', async () => {
    stubFetch(jsonResponse(403, { error: 'Forbidden', message: 'Admin role required' }))
    signIn(TOKEN)

    const error = await captureError(apiRequest('/api/admin/coverages'))

    expect(error.status).toBe(403)
    expect(session.token).toBe(TOKEN)
  })

  it('carries the field errors of a 422', async () => {
    const details = [{ field: 'body.cik', message: 'String should have at most 10 characters' }]
    stubFetch(jsonResponse(422, { error: 'Unprocessable Content', message: 'Request validation failed', details }))

    const error = await captureError(apiRequest('/api/coverages', { method: 'POST', body: {} }))

    expect(error.status).toBe(422)
    expect(error.details).toEqual(details)
  })

  it('falls back to a status message when the error body is not JSON', async () => {
    stubFetch(new Response('<html>502 Bad Gateway</html>', { status: 502 }))

    const error = await captureError(apiRequest('/api/coverages'))

    expect(error.status).toBe(502)
    expect(error.message).toBe('Request failed with status 502.')
    expect(error.details).toEqual([])
  })

  it('throws when a successful response is not JSON', async () => {
    stubFetch(new Response('<!doctype html>', { status: 200 }))

    const error = await captureError(apiRequest('/api/coverages'))

    expect(error.status).toBe(200)
    expect(error.message).toBe('The server sent a response this app could not read.')
  })

  it('throws a network error when the server is unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockRejectedValue(new TypeError('Failed to fetch')))
    signIn(TOKEN)

    const error = await captureError(apiRequest('/api/coverages'))

    expect(error.status).toBe(NETWORK_ERROR_STATUS)
    expect(error.message).toBe('Could not reach the server.')
    expect(session.token).toBe(TOKEN)
  })
})
