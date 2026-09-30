import { readonly, ref, shallowRef, type DeepReadonly, type Ref } from 'vue'

import { ApiError } from '@/api/client'

export type RequestState = 'loading' | 'success' | 'error'

export interface UseRequest<T> {
  state: DeepReadonly<Ref<RequestState>>
  data: DeepReadonly<Ref<T | null>>
  error: DeepReadonly<Ref<ApiError | null>>
  reload: () => Promise<void>
}

// One loading/success/error cycle for every page, so no page invents its own flags.
export function useRequest<T>(load: () => Promise<T>): UseRequest<T> {
  const state = ref<RequestState>('loading')
  const data = shallowRef<T | null>(null)
  const error = shallowRef<ApiError | null>(null)
  let latestRun = 0

  async function reload(): Promise<void> {
    // A reload that overtakes an earlier call wins; the earlier result is dropped when it lands.
    const run = ++latestRun
    state.value = 'loading'
    error.value = null
    try {
      const result = await load()
      if (run !== latestRun) return
      data.value = result
      state.value = 'success'
    } catch (caught) {
      if (run !== latestRun) return
      // Only the API's failures are a page state; anything else is a bug and must surface.
      if (!(caught instanceof ApiError)) throw caught
      error.value = caught
      state.value = 'error'
    }
  }

  void reload()

  return { state: readonly(state), data: readonly(data), error: readonly(error), reload }
}
