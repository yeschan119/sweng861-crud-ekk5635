import { describe, expect, it } from 'vitest'

import {
  fromCoverage,
  TICKER_MAX_LENGTH,
  TITLE_MAX_LENGTH,
  toCreateInput,
  toUpdateInput,
  validateCoverageForm,
  type CoverageFormValues,
} from '@/validation/coverageForm'

const VALID: CoverageFormValues = {
  title: 'Apple Inc.',
  description: '',
  status: 'draft',
  ticker: 'AAPL',
  cik: '0000320193',
}

describe('validateCoverageForm', () => {
  it('accepts a valid form in both modes', () => {
    expect(validateCoverageForm(VALID, 'create')).toEqual({})
    expect(validateCoverageForm(VALID, 'edit')).toEqual({})
  })

  it('requires a title that is not only whitespace', () => {
    expect(validateCoverageForm({ ...VALID, title: '   ' }, 'create')).toEqual({
      title: 'Title is required.',
    })
  })

  it('caps the title at the backend limit', () => {
    const atLimit = 'a'.repeat(TITLE_MAX_LENGTH)
    expect(validateCoverageForm({ ...VALID, title: atLimit }, 'create')).toEqual({})
    expect(validateCoverageForm({ ...VALID, title: atLimit + 'a' }, 'create')).toEqual({
      title: `Title must be ${TITLE_MAX_LENGTH} characters or fewer.`,
    })
  })

  it('caps the ticker at the backend limit but allows it to be empty', () => {
    expect(validateCoverageForm({ ...VALID, ticker: '' }, 'create')).toEqual({})
    expect(
      validateCoverageForm({ ...VALID, ticker: 'x'.repeat(TICKER_MAX_LENGTH) }, 'create'),
    ).toEqual({})
    expect(
      validateCoverageForm({ ...VALID, ticker: 'x'.repeat(TICKER_MAX_LENGTH + 1) }, 'create'),
    ).toEqual({ ticker: `Ticker must be ${TICKER_MAX_LENGTH} characters or fewer.` })
  })

  it.each(['', '320193', '00003201930', '000032019x'])('rejects the cik %j on create', (cik) => {
    expect(validateCoverageForm({ ...VALID, cik }, 'create')).toEqual({
      cik: 'CIK must be exactly 10 digits, e.g. 0000320193.',
    })
  })

  it('accepts a cik with surrounding whitespace, which is trimmed before sending', () => {
    expect(validateCoverageForm({ ...VALID, cik: ' 0000320193 ' }, 'create')).toEqual({})
  })

  it('ignores the cik on edit, where it cannot be changed', () => {
    expect(validateCoverageForm({ ...VALID, cik: '' }, 'edit')).toEqual({})
  })

  it('reports every failing field at once', () => {
    const errors = validateCoverageForm({ ...VALID, title: '', cik: 'nope' }, 'create')
    expect(Object.keys(errors).sort()).toEqual(['cik', 'title'])
  })
})

describe('toCreateInput and toUpdateInput', () => {
  it('trims text and turns blank optional fields into null', () => {
    const values: CoverageFormValues = {
      title: '  Apple Inc. ',
      description: '   ',
      status: 'active',
      ticker: ' AAPL ',
      cik: ' 0000320193 ',
    }
    expect(toCreateInput(values)).toEqual({
      title: 'Apple Inc.',
      description: null,
      status: 'active',
      ticker: 'AAPL',
      cik: '0000320193',
    })
  })

  it('keeps a description that has content', () => {
    expect(toUpdateInput({ ...VALID, description: ' Follows the 10-K. ' }).description).toBe(
      'Follows the 10-K.',
    )
  })

  it('never puts cik into an update', () => {
    expect(toUpdateInput(VALID)).not.toHaveProperty('cik')
  })
})

describe('fromCoverage', () => {
  it('turns stored nulls into empty inputs and keeps everything else', () => {
    expect(
      fromCoverage({
        id: 7,
        title: 'Apple Inc.',
        description: null,
        status: 'active',
        ticker: null,
        cik: '0000320193',
        created_at: '2026-09-18T00:00:00Z',
        updated_at: '2026-09-18T01:02:03Z',
      }),
    ).toEqual({ title: 'Apple Inc.', description: '', status: 'active', ticker: '', cik: '0000320193' })
  })
})
