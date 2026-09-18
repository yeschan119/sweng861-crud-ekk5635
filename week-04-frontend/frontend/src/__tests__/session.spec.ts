import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { isSignedIn, session, signIn, signOut } from '@/auth/session'

// Encoded independently of the module under test, the way the backend's PyJWT does: base64url, unpadded.
function makeToken(claims: object): string {
  const payload = Buffer.from(JSON.stringify(claims)).toString('base64url')
  return `header.${payload}.signature`
}

function payloadOf(token: string): string {
  return token.split('.')[1] ?? ''
}

describe('session', () => {
  beforeEach(() => {
    signOut()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('starts signed out', () => {
    expect(isSignedIn.value).toBe(false)
    expect(session.token).toBeNull()
    expect(session.email).toBeNull()
  })

  it('stores the token and reads the email claim on sign-in', () => {
    const token = makeToken({ sub: '1', email: 'analyst@example.com' })

    signIn(token)

    expect(isSignedIn.value).toBe(true)
    expect(session.token).toBe(token)
    expect(session.email).toBe('analyst@example.com')
  })

  it('keeps the token out of web storage and the console', () => {
    const log = vi.spyOn(console, 'log').mockImplementation(() => {})
    const info = vi.spyOn(console, 'info').mockImplementation(() => {})
    const token = makeToken({ sub: '1', email: 'analyst@example.com' })

    signIn(token)

    // Memory only (D-4): a token in storage would survive the tab and be readable by any script.
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
    expect(log).not.toHaveBeenCalled()
    expect(info).not.toHaveBeenCalled()
  })

  it('clears both values on sign-out', () => {
    signIn(makeToken({ sub: '1', email: 'analyst@example.com' }))

    signOut()

    expect(isSignedIn.value).toBe(false)
    expect(session.token).toBeNull()
    expect(session.email).toBeNull()
  })

  it('drops the previous email when a later token carries none', () => {
    signIn(makeToken({ sub: '1', email: 'analyst@example.com' }))

    signIn(makeToken({ sub: '2' }))

    expect(session.email).toBeNull()
  })

  it('decodes base64url characters and a payload that would need padding', () => {
    const token = makeToken({ sub: '1', email: '~~~?@example.com' })
    expect(payloadOf(token)).toMatch(/-/)
    expect(payloadOf(token)).toMatch(/_/)
    expect(payloadOf(token).length % 4).not.toBe(0)

    signIn(token)

    expect(session.email).toBe('~~~?@example.com')
  })

  it('decodes a non-ASCII email as UTF-8', () => {
    signIn(makeToken({ sub: '1', email: '분석가@example.com' }))

    expect(session.email).toBe('분석가@example.com')
  })

  it.each([
    ['no payload segment', 'not-a-jwt'],
    ['a payload that is not base64', 'header.***.signature'],
    ['a payload that is not JSON', `header.${Buffer.from('not json').toString('base64url')}.signature`],
    ['a payload without an email', makeToken({ sub: '1' })],
    ['an email that is not a string', makeToken({ sub: '1', email: 42 })],
  ])('signs in without an email given %s', (_case, token) => {
    signIn(token)

    expect(isSignedIn.value).toBe(true)
    expect(session.token).toBe(token)
    expect(session.email).toBeNull()
  })

  it('cannot be changed except through signIn and signOut', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})

    // @ts-expect-error session is readonly at compile time as well
    session.token = 'forged'

    expect(session.token).toBeNull()
    expect(isSignedIn.value).toBe(false)
    expect(warn).toHaveBeenCalled()
  })
})
