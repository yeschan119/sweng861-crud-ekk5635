<script setup lang="ts">
import { useRoute } from 'vue-router'

import { getCoverage } from '@/api/coverages'
import { useRequest } from '@/composables/useRequest'

const NOT_FOUND = 404
const FORBIDDEN = 403

const route = useRoute()
// Passed through as text: the API validates the id, so a malformed one fails like any other request.
// Read once: App.vue keys the RouterView by path, so another id means a fresh instance of this page.
const id = String(route.params.id)

const { state, data: coverage, error, reload } = useRequest(() => getCoverage(id))
</script>

<template>
  <p><RouterLink :to="{ name: 'coverages' }">Back to My Coverages</RouterLink></p>
  <h1>{{ coverage?.title ?? 'Coverage' }}</h1>

  <p v-if="state === 'loading'" role="status">Loading…</p>

  <div v-else-if="state === 'error'" role="alert">
    <p v-if="error?.status === NOT_FOUND">This item does not exist or has been deleted.</p>
    <p v-else-if="error?.status === FORBIDDEN">You are not authorized to view this item.</p>
    <!-- Retry only where it can change anything: a 404 or 403 answers the same way again. -->
    <template v-else>
      <p>Could not load this coverage.</p>
      <button type="button" @click="reload">Retry</button>
    </template>
  </div>

  <template v-else-if="coverage">
    <dl>
      <dt>Status</dt>
      <dd>{{ coverage.status }}</dd>
      <dt>Ticker</dt>
      <dd>{{ coverage.ticker ?? '—' }}</dd>
      <dt>CIK</dt>
      <dd>{{ coverage.cik }}</dd>
      <dt>Description</dt>
      <dd>{{ coverage.description ?? '—' }}</dd>
      <dt>Created</dt>
      <dd>{{ coverage.created_at }}</dd>
      <dt>Updated</dt>
      <dd>{{ coverage.updated_at }}</dd>
    </dl>
    <p><RouterLink class="button secondary" :to="{ name: 'coverage-edit', params: { id: coverage.id } }">Edit</RouterLink></p>
  </template>
</template>
