<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import { isSignedIn, session, signOut } from '@/auth/session'
import { clearFlash, flash } from '@/notices/flash'

const route = useRoute()

// Focus directly: a plain #main fragment would reach the router and remount the page.
function skipToContent(): void {
  document.getElementById('main')?.focus()
}

// A malformed token signs in without an email (see session.ts), so the label must not depend on it.
const userLabel = computed(() =>
  session.email === null ? 'Logged in' : `Logged in as ${session.email}`,
)
</script>

<template>
  <!-- First tab stop: keyboard users jump past the header straight to the page. -->
  <a class="skip-link" href="#main" @click.prevent="skipToContent">Skip to content</a>
  <header class="shell-header">
    <span class="app-name">SWENG 861 Coverages</span>
    <nav aria-label="Main">
      <RouterLink :to="{ name: 'coverages' }">My Coverages</RouterLink>
    </nav>
    <div class="user-area">
      <template v-if="isSignedIn">
        <span>{{ userLabel }}</span>
        <!-- Only clears the session: the router's watcher moves to /login, so navigation lives in one place. -->
        <button type="button" @click="signOut">Sign out</button>
      </template>
      <RouterLink v-else :to="{ name: 'login' }">Log in</RouterLink>
    </div>
  </header>
  <main id="main" tabindex="-1">
    <!-- Set by a page before it navigates away; the router clears it on the navigation after that. -->
    <p v-if="flash.message !== null" role="status" class="flash">
      {{ flash.message }}
      <button type="button" @click="clearFlash">Dismiss</button>
    </p>
    <!-- Keyed by path so a route change is a fresh page, even when two routes share a component. -->
    <RouterView :key="route.fullPath" />
  </main>
</template>
