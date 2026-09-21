import { computed, reactive, readonly } from 'vue'

interface SessionState {
  token: string | null
  email: string | null
}

// Memory only, as in Week 3: nothing outlives the tab, and a reload signs the user out.
const state = reactive<SessionState>({ token: null, email: null })

export const session = readonly(state)

export const isSignedIn = computed(() => state.token !== null)

export function signIn(token: string): void {
  state.token = token
  state.email = readEmailClaim(token)
}

export function signOut(): void {
  state.token = null
  state.email = null
}

// For display only: the signature is not checked here, the backend checks it on every request.
// A malformed token yields no email rather than an error; its first API call answers 401.
function readEmailClaim(token: string): string | null {
  const payload = token.split('.')[1]
  if (!payload) return null

  try {
    const base64 = payload.replace(/-/g, '+').replace(/_/g, '/')
    const bytes = Uint8Array.from(atob(base64), (char) => char.charCodeAt(0))
    const claims: unknown = JSON.parse(new TextDecoder().decode(bytes))
    if (typeof claims === 'object' && claims !== null && 'email' in claims) {
      return typeof claims.email === 'string' ? claims.email : null
    }
    return null
  } catch {
    return null
  }
}
