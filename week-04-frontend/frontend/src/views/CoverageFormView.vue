<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api/client'
import { createCoverage, getCoverage, updateCoverage, type CoverageStatus } from '@/api/coverages'
import { useRequest, type RequestState } from '@/composables/useRequest'
import {
  fromCoverage,
  toCreateInput,
  toUpdateInput,
  validateCoverageForm,
  type CoverageFormErrors,
  type CoverageFormMode,
  type CoverageFormValues,
} from '@/validation/coverageForm'

const UNPROCESSABLE = 422
const CONFLICT = 409
const STATUSES: CoverageStatus[] = ['draft', 'active', 'archived']

const route = useRoute()
const router = useRouter()
// One component serves both routes; the route name is the only thing that tells them apart.
const mode: CoverageFormMode = route.name === 'coverage-edit' ? 'edit' : 'create'
const id = String(route.params.id)

// Form state is local on purpose: nothing else needs a half-typed coverage.
const values = reactive<CoverageFormValues>({
  title: '',
  description: '',
  status: 'draft',
  ticker: '',
  cik: '',
})
const fieldErrors = ref<CoverageFormErrors>({})
const formError = ref<string | null>(null)
const isSaving = ref(false)

// Only an edit has something to load; a new form starts where an edit ends up after loading.
const existing = mode === 'edit' ? useRequest(() => getCoverage(id)) : null
const loadState = computed<RequestState>(() => existing?.state.value ?? 'success')
if (existing !== null) {
  // Copied once when the coverage arrives; from then on the inputs own the values.
  watch(existing.data, (coverage) => {
    if (coverage !== null) Object.assign(values, fromCoverage(coverage))
  })
}

function retryLoad(): void {
  void existing?.reload()
}

async function submit(): Promise<void> {
  // The button is disabled while saving, but Enter in a field still submits; this catches that.
  if (isSaving.value) return

  formError.value = null
  fieldErrors.value = validateCoverageForm(values, mode)
  if (Object.keys(fieldErrors.value).length > 0) return

  isSaving.value = true
  try {
    const saved =
      mode === 'edit'
        ? await updateCoverage(id, toUpdateInput(values))
        : await createCoverage(toCreateInput(values))
    await router.push({ name: 'coverage-detail', params: { id: saved.id } })
  } catch (caught) {
    // A 401 already cleared the session and the router is leaving; anything else is shown here.
    if (!(caught instanceof ApiError)) throw caught
    showSaveFailure(caught)
  } finally {
    isSaving.value = false
  }
}

function showSaveFailure(error: ApiError): void {
  if (error.status === UNPROCESSABLE) fieldErrors.value = fieldErrorsFrom(error)
  // A 409 message ("You already cover this filer") tells the user what to change; others do not.
  formError.value = error.status === CONFLICT ? error.message : 'Could not save. Please try again.'
}

// The backend names a field as "body.title"; only the last segment matches an input here.
function fieldErrorsFrom(error: ApiError): CoverageFormErrors {
  const errors: CoverageFormErrors = {}
  for (const detail of error.details) {
    const field = detail.field.split('.').pop()
    if (field !== undefined && isFormField(field)) errors[field] = detail.message
  }
  return errors
}

function isFormField(name: string): name is keyof CoverageFormValues {
  return Object.prototype.hasOwnProperty.call(values, name)
}
</script>

<template>
  <p><RouterLink :to="{ name: 'coverages' }">Back to My Coverages</RouterLink></p>
  <h1>{{ mode === 'edit' ? 'Edit Coverage' : 'New Coverage' }}</h1>

  <p v-if="loadState === 'loading'" role="status">Loading…</p>

  <!-- The detail page, where the Edit link lives, already explains a 404 or 403 in full. -->
  <div v-else-if="loadState === 'error'" role="alert">
    <p>Could not load this coverage.</p>
    <button type="button" @click="retryLoad">Retry</button>
  </div>

  <!-- novalidate: the messages come from validateCoverageForm, not the browser's built-in ones. -->
  <form v-else novalidate @submit.prevent="submit">
    <p v-if="formError !== null" role="alert">{{ formError }}</p>

    <div>
      <label for="title">Title</label>
      <input id="title" v-model="values.title" type="text" />
      <p v-if="fieldErrors.title" class="field-error">{{ fieldErrors.title }}</p>
    </div>

    <div>
      <label for="cik">CIK</label>
      <!-- The backend refuses a changed cik, so the input says so up front instead of after a 422. -->
      <input id="cik" v-model="values.cik" type="text" inputmode="numeric" :readonly="mode === 'edit'" />
      <p v-if="mode === 'edit'" class="field-hint">The CIK cannot be changed after creation.</p>
      <p v-if="fieldErrors.cik" class="field-error">{{ fieldErrors.cik }}</p>
    </div>

    <div>
      <label for="ticker">Ticker</label>
      <input id="ticker" v-model="values.ticker" type="text" />
      <p v-if="fieldErrors.ticker" class="field-error">{{ fieldErrors.ticker }}</p>
    </div>

    <div>
      <label for="status">Status</label>
      <select id="status" v-model="values.status">
        <option v-for="status in STATUSES" :key="status" :value="status">{{ status }}</option>
      </select>
      <p v-if="fieldErrors.status" class="field-error">{{ fieldErrors.status }}</p>
    </div>

    <div>
      <label for="description">Description</label>
      <textarea id="description" v-model="values.description" rows="4"></textarea>
      <p v-if="fieldErrors.description" class="field-error">{{ fieldErrors.description }}</p>
    </div>

    <button type="submit" :disabled="isSaving">{{ isSaving ? 'Saving…' : 'Save' }}</button>
  </form>
</template>
