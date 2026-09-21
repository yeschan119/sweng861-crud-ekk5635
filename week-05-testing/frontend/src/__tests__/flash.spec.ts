import { afterEach, describe, expect, it } from 'vitest'

import { clearFlash, flash, showFlash } from '@/notices/flash'

describe('flash notice', () => {
  afterEach(() => clearFlash())

  it('starts empty', () => {
    expect(flash.message).toBeNull()
  })

  it('holds the latest message only', () => {
    showFlash('Coverage created.')
    showFlash('Changes saved.')
    expect(flash.message).toBe('Changes saved.')
  })

  it('is empty again after clearing', () => {
    showFlash('Coverage created.')
    clearFlash()
    expect(flash.message).toBeNull()
  })

  it('cannot be changed except through showFlash and clearFlash', () => {
    showFlash('Coverage created.')
    // @ts-expect-error readonly: assignment is a compile error, and a no-op at runtime.
    flash.message = 'tampered'
    expect(flash.message).toBe('Coverage created.')
  })
})
