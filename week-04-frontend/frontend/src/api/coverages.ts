import { apiRequest } from '@/api/client'

export type CoverageStatus = 'draft' | 'active' | 'archived'

// The backend's CoverageRead: what any signed-in user gets for their own rows.
export interface Coverage {
  id: number
  title: string
  description: string | null
  status: CoverageStatus
  ticker: string | null
  cik: string
  created_at: string
  updated_at: string
}

export function listCoverages(): Promise<Coverage[]> {
  return apiRequest<Coverage[]>('/api/coverages')
}

export function getCoverage(id: string): Promise<Coverage> {
  return apiRequest<Coverage>(`/api/coverages/${encodeURIComponent(id)}`)
}

// Mirrors the backend's CoverageCreate: cik is fixed at creation and cannot be changed afterwards.
export interface CoverageCreateInput {
  title: string
  description: string | null
  status: CoverageStatus
  ticker: string | null
  cik: string
}

// The backend's CoverageUpdate has no cik: changing the filer means a new coverage.
export type CoverageUpdateInput = Omit<CoverageCreateInput, 'cik'>

export function createCoverage(input: CoverageCreateInput): Promise<Coverage> {
  return apiRequest<Coverage>('/api/coverages', { method: 'POST', body: input })
}

export function updateCoverage(id: string, input: CoverageUpdateInput): Promise<Coverage> {
  return apiRequest<Coverage>(`/api/coverages/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: input,
  })
}
