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
    <caption class="visually-hidden">Your coverages</caption>
    <thead>
      <tr>
        <th scope="col">Title</th>
        <th scope="col">Ticker</th>
        <th scope="col">Status</th>
        <th scope="col">Updated</th>
        <th scope="col"><span class="visually-hidden">Actions</span></th>
      </tr>
    </thead>
    <tbody>
      <!-- data-label repeats the header for the phone layout, where rows become cards (see main.css). -->
      <tr v-for="coverage in coverages" :key="coverage.id">
        <td data-label="Title">{{ coverage.title }}</td>
        <td data-label="Ticker">{{ coverage.ticker ?? '—' }}</td>
        <td data-label="Status">{{ coverage.status }}</td>
        <td data-label="Updated">{{ dayOf(coverage.updated_at) }}</td>
        <td class="row-action">
          <RouterLink :to="{ name: 'coverage-detail', params: { id: coverage.id } }">
            View Details
          </RouterLink>
        </td>
      </tr>
    </tbody>
  </table>

  <p><RouterLink class="button secondary" :to="{ name: 'coverage-new' }">New coverage</RouterLink></p>
</template>
