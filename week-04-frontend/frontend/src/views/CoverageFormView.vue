<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api/client'
import { createCoverage, getCoverage, updateCoverage, type CoverageStatus } from '@/api/coverages'
import { useRequest, type RequestState } from '@/composables/useRequest'
import { showFlash } from '@/notices/flash'
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
// Visual order of the inputs; the first invalid one receives focus after a failed submit.
const FIELD_ORDER: (keyof CoverageFormValues)[] = ['title', 'cik', 'ticker', 'status', 'description']

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
  if (Object.keys(fieldErrors.value).length > 0) {
    // Screen-reader users hear the error with the field; sighted users see where to type.
    const firstInvalid = FIELD_ORDER.find((field) => fieldErrors.value[field] !== undefined)
    await nextTick()
    if (firstInvalid !== undefined) document.getElementById(firstInvalid)?.focus()
    return
  }

  isSaving.value = true
  try {
    const saved =
      mode === 'edit'
        ? await updateCoverage(id, toUpdateInput(values))
        : await createCoverage(toCreateInput(values))
    await router.push({ name: 'coverage-detail', params: { id: saved.id } })
    // After the push, so the router's afterEach for this navigation has already run and cannot clear it.
    showFlash(mode === 'edit' ? 'Changes saved.' : 'Coverage created.')
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

// Screen readers announce the error (and the cik hint) with the input, not just the banner.
function describedBy(field: keyof CoverageFormValues): string | undefined {
  const ids: string[] = []
  if (field === 'cik' && mode === 'edit') ids.push('cik-hint')
  if (fieldErrors.value[field]) ids.push(`${field}-error`)
  return ids.length > 0 ? ids.join(' ') : undefined
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
      <input
        id="title"
        v-model="values.title"
        type="text"
        required
        :aria-invalid="fieldErrors.title ? 'true' : undefined"
        :aria-describedby="describedBy('title')"
      />
      <p v-if="fieldErrors.title" id="title-error" class="field-error">{{ fieldErrors.title }}</p>
    </div>

    <div>
      <label for="cik">CIK</label>
      <!-- The backend refuses a changed cik, so the input says so up front instead of after a 422. -->
      <input
        id="cik"
        v-model="values.cik"
        type="text"
        inputmode="numeric"
        :required="mode === 'create'"
        :readonly="mode === 'edit'"
        :aria-invalid="fieldErrors.cik ? 'true' : undefined"
        :aria-describedby="describedBy('cik')"
      />
      <p v-if="mode === 'edit'" id="cik-hint" class="field-hint">The CIK cannot be changed after creation.</p>
      <p v-if="fieldErrors.cik" id="cik-error" class="field-error">{{ fieldErrors.cik }}</p>
    </div>

    <div>
      <label for="ticker">Ticker</label>
      <input
        id="ticker"
        v-model="values.ticker"
        type="text"
        :aria-invalid="fieldErrors.ticker ? 'true' : undefined"
        :aria-describedby="describedBy('ticker')"
      />
      <p v-if="fieldErrors.ticker" id="ticker-error" class="field-error">{{ fieldErrors.ticker }}</p>
    </div>

    <div>
      <label for="status">Status</label>
      <select
        id="status"
        v-model="values.status"
        :aria-invalid="fieldErrors.status ? 'true' : undefined"
        :aria-describedby="describedBy('status')"
      >
        <option v-for="status in STATUSES" :key="status" :value="status">{{ status }}</option>
      </select>
      <p v-if="fieldErrors.status" id="status-error" class="field-error">{{ fieldErrors.status }}</p>
    </div>

    <div>
      <label for="description">Description</label>
      <textarea
        id="description"
        v-model="values.description"
        rows="4"
        :aria-invalid="fieldErrors.description ? 'true' : undefined"
        :aria-describedby="describedBy('description')"
      ></textarea>
      <p v-if="fieldErrors.description" id="description-error" class="field-error">{{ fieldErrors.description }}</p>
    </div>

    <button type="submit" :disabled="isSaving">{{ isSaving ? 'Saving…' : 'Save' }}</button>
  </form>
</template>
