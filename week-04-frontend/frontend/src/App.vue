<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import { isSignedIn, session, signOut } from '@/auth/session'

const route = useRoute()

// A malformed token signs in without an email (see session.ts), so the label must not depend on it.
const userLabel = computed(() =>
  session.email === null ? 'Logged in' : `Logged in as ${session.email}`,
)
</script>

<template>
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
  <main>
    <!-- Keyed by path so a route change is a fresh page, even when two routes share a component. -->
    <RouterView :key="route.fullPath" />
  </main>
</template>

<style scoped>
/* Layout only; spacing for small screens comes with the responsive pass. */
.shell-header {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.app-name {
  font-weight: bold;
}

.user-area {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
</style>
