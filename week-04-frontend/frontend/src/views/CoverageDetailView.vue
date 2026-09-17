<script setup lang="ts">
import { watch } from 'vue'
import { useRoute } from 'vue-router'

import { getCoverage } from '@/api/coverages'
import { useRequest } from '@/composables/useRequest'

const NOT_FOUND = 404
const FORBIDDEN = 403

const route = useRoute()
// Passed through as text: the API validates the id, so a malformed one fails like any other request.
const idInRoute = () => String(route.params.id)

const { state, data: coverage, error, reload } = useRequest(() => getCoverage(idInRoute()))

// The router reuses this component between two detail URLs, so a new id must load on its own.
watch(idInRoute, () => void reload())
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

  <dl v-else-if="coverage">
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
</template>
