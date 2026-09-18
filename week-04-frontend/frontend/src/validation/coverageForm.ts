import type {
  Coverage,
  CoverageCreateInput,
  CoverageStatus,
  CoverageUpdateInput,
} from '@/api/coverages'

// What the inputs hold: strings only, because that is what <input> and <select> give back.
export interface CoverageFormValues {
  title: string
  description: string
  status: CoverageStatus
  ticker: string
  cik: string
}

export type CoverageFormMode = 'create' | 'edit'

export type CoverageFormErrors = Partial<Record<keyof CoverageFormValues, string>>

// The same limits the backend enforces (CoverageCreate), so a valid form is not refused with a 422.
export const TITLE_MAX_LENGTH = 200
export const TICKER_MAX_LENGTH = 10
const CIK_PATTERN = /^\d{10}$/

// Only the rules that decide whether a request is sent; the backend stays the authority.
export function validateCoverageForm(
  values: CoverageFormValues,
  mode: CoverageFormMode,
): CoverageFormErrors {
  const errors: CoverageFormErrors = {}

  const title = values.title.trim()
  if (title === '') errors.title = 'Title is required.'
  else if (title.length > TITLE_MAX_LENGTH) {
    errors.title = `Title must be ${TITLE_MAX_LENGTH} characters or fewer.`
  }

  if (values.ticker.trim().length > TICKER_MAX_LENGTH) {
    errors.ticker = `Ticker must be ${TICKER_MAX_LENGTH} characters or fewer.`
  }

  // cik is read-only once created, so an edit form has nothing to check here.
  if (mode === 'create' && !CIK_PATTERN.test(values.cik.trim())) {
    errors.cik = 'CIK must be exactly 10 digits, e.g. 0000320193.'
  }

  return errors
}

export function toCreateInput(values: CoverageFormValues): CoverageCreateInput {
  return { ...toUpdateInput(values), cik: values.cik.trim() }
}

export function toUpdateInput(values: CoverageFormValues): CoverageUpdateInput {
  return {
    title: values.title.trim(),
    description: blankToNull(values.description),
    status: values.status,
    ticker: blankToNull(values.ticker),
  }
}

// The inverse of toUpdateInput: a stored null shows as an empty input.
export function fromCoverage(coverage: Coverage): CoverageFormValues {
  return {
    title: coverage.title,
    description: coverage.description ?? '',
    status: coverage.status,
    ticker: coverage.ticker ?? '',
    cik: coverage.cik,
  }
}

// An empty input means "no value"; the API and the read pages both treat that as null, not "".
function blankToNull(value: string): string | null {
  const trimmed = value.trim()
  return trimmed === '' ? null : trimmed
}
