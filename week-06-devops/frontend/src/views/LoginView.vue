<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { signIn } from '@/auth/session'

// Backend and page agree on one reason; distinguishing failures would describe the defenses.
const LOGIN_FAILED_MESSAGE = 'Login failed. Please try again.'

const errorMessage = ref<string | null>(null)
const router = useRouter()

// The callback lands here with the outcome in the fragment, which no server ever sees.
function readLoginOutcome(): { token: string } | { failed: true } | null {
  const fragment = window.location.hash.slice(1)
  if (fragment === '') return null

  const token = new URLSearchParams(fragment).get('access_token')
  return token ? { token } : { failed: true }
}

// Clear the fragment so the token outlives neither the address bar nor a bookmark of this page.
function clearFragment(): void {
  window.history.replaceState(window.history.state, '', window.location.pathname)
}

onMounted(() => {
  const outcome = readLoginOutcome()
  if (outcome === null) return

  clearFragment()
  if ('token' in outcome) {
    signIn(outcome.token)
    void router.replace({ name: 'coverages' })
  } else {
    errorMessage.value = LOGIN_FAILED_MESSAGE
  }
})
</script>

<template>
  <h1>Sign in</h1>
  <p v-if="errorMessage" role="alert">{{ errorMessage }}</p>
  <!-- A plain link: the backend answers with a redirect to Google, so this must leave the SPA. -->
  <a class="button" href="/auth/login">Login with Google</a>
</template>
