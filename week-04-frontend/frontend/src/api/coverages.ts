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
