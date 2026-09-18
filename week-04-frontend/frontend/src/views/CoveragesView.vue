<script setup lang="ts">
import { listCoverages } from '@/api/coverages'
import { useRequest } from '@/composables/useRequest'

const { state, data: coverages, reload } = useRequest(listCoverages)

// Timestamps arrive as ISO strings; the day is enough for a list.
function dayOf(timestamp: string): string {
  return timestamp.slice(0, 10)
}
</script>

<template>
  <h1>My Coverages</h1>

  <p v-if="state === 'loading'" role="status">Loading…</p>

  <div v-else-if="state === 'error'" role="alert">
    <p>Could not load your coverages.</p>
    <button type="button" @click="reload">Retry</button>
  </div>

  <p v-else-if="coverages?.length === 0">No coverages yet.</p>

  <table v-else>
    <thead>
      <tr>
        <th>Title</th>
        <th>Ticker</th>
        <th>Status</th>
        <th>Updated</th>
        <th></th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="coverage in coverages" :key="coverage.id">
        <td>{{ coverage.title }}</td>
        <td>{{ coverage.ticker ?? '—' }}</td>
        <td>{{ coverage.status }}</td>
        <td>{{ dayOf(coverage.updated_at) }}</td>
        <td>
          <RouterLink :to="{ name: 'coverage-detail', params: { id: coverage.id } }">
            View Details
          </RouterLink>
        </td>
      </tr>
    </tbody>
  </table>

  <p><RouterLink :to="{ name: 'coverage-new' }">New coverage</RouterLink></p>
</template>
