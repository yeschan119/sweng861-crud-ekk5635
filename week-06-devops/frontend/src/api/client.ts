import { session, signOut } from '@/auth/session'

// One entry of the backend's 422 `details` array.
export interface FieldError {
  field: string
  message: string
}

export class ApiError extends Error {
  readonly status: number
  readonly details: FieldError[]

  constructor(status: number, message: string, details: FieldError[] = []) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.details = details
  }
}

// Not an HTTP status: the request never got an answer.
export const NETWORK_ERROR_STATUS = 0

const NO_CONTENT = 204
const UNAUTHORIZED = 401

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'
  body?: unknown
}

interface ErrorBody {
  message: string
  details?: unknown
}

// Every backend call goes through here, so the token and error handling live in one place.
export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (session.token !== null) headers.Authorization = `Bearer ${session.token}`
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'

  let response: Response
  try {
    response = await fetch(path, {
      method: options.method ?? 'GET',
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    })
  } catch {
    // The browser hides why a fetch failed ("Failed to fetch"); the Network tab shows the reason.
    throw new ApiError(NETWORK_ERROR_STATUS, 'Could not reach the server.')
  }

  if (response.ok) return readSuccess<T>(response)

  // Only 401 means the token is stale; 403 is a valid token without permission, so the session stays.
  if (response.status === UNAUTHORIZED) signOut()
  throw await readError(response)
}

async function readSuccess<T>(response: Response): Promise<T> {
  if (response.status === NO_CONTENT) return undefined as T

  const data = await readJson(response)
  if (data === undefined) {
    throw new ApiError(response.status, 'The server sent a response this app could not read.')
  }
  return data as T
}

async function readError(response: Response): Promise<ApiError> {
  const body = await readJson(response)
  if (!isErrorBody(body)) {
    return new ApiError(response.status, `Request failed with status ${response.status}.`)
  }
  const details = Array.isArray(body.details) ? (body.details as FieldError[]) : []
  return new ApiError(response.status, body.message, details)
}

// Undefined when the body is not JSON, e.g. an HTML error page from the gateway.
async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json()
  } catch {
    return undefined
  }
}

function isErrorBody(body: unknown): body is ErrorBody {
  return (
    typeof body === 'object' && body !== null && 'message' in body && typeof body.message === 'string'
  )
}
