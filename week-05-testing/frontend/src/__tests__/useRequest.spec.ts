import { describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'

import { ApiError } from '@/api/client'
import { useRequest } from '@/composables/useRequest'

// A promise whose settlement the test controls, so the loading state can be observed.
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

describe('useRequest', () => {
  it('starts loading and holds the result on success', async () => {
    const pending = deferred<string[]>()
    const request = useRequest(() => pending.promise)

    expect(request.state.value).toBe('loading')
    expect(request.data.value).toBeNull()

    pending.resolve(['a', 'b'])
    await flushPromises()

    expect(request.state.value).toBe('success')
    expect(request.data.value).toEqual(['a', 'b'])
    expect(request.error.value).toBeNull()
  })

  it('holds the ApiError on failure', async () => {
    const failure = new ApiError(404, 'Coverage not found.')
    const request = useRequest(() => Promise.reject(failure))
    await flushPromises()

    expect(request.state.value).toBe('error')
    expect(request.error.value).toBe(failure)
    expect(request.data.value).toBeNull()
  })

  it('does not treat other exceptions as a page state', async () => {
    const bug = new TypeError('undefined is not a function')
    const unhandled = vi.fn<(reason: unknown, promise: Promise<unknown>) => void>()
    process.once('unhandledRejection', unhandled)

    useRequest(() => Promise.reject(bug))
    await flushPromises()
    await new Promise((resolve) => setImmediate(resolve))

    expect(unhandled).toHaveBeenCalledWith(bug, expect.anything())
  })

  it('reloads, going through loading again and clearing the old error', async () => {
    const load = vi
      .fn<() => Promise<number>>()
      .mockRejectedValueOnce(new ApiError(0, 'Could not reach the server.'))
      .mockResolvedValueOnce(42)
    const request = useRequest(load)
    await flushPromises()
    expect(request.state.value).toBe('error')

    const reloading = request.reload()
    expect(request.state.value).toBe('loading')
    expect(request.error.value).toBeNull()
    await reloading

    expect(request.state.value).toBe('success')
    expect(request.data.value).toBe(42)
    expect(load).toHaveBeenCalledTimes(2)
  })

  it('drops a result that arrives after a newer reload started', async () => {
    const first = deferred<string>()
    const second = deferred<string>()
    const load = vi
      .fn<() => Promise<string>>()
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise)
    const request = useRequest(load)

    void request.reload()
    second.resolve('newer')
    await flushPromises()
    expect(request.data.value).toBe('newer')

    first.resolve('older')
    await flushPromises()
    expect(request.data.value).toBe('newer')
    expect(request.state.value).toBe('success')
  })

  it('drops a failure that arrives after a newer reload started', async () => {
    const first = deferred<string>()
    const second = deferred<string>()
    const load = vi
      .fn<() => Promise<string>>()
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise)
    const request = useRequest(load)

    void request.reload()
    second.resolve('newer')
    await flushPromises()

    first.reject(new ApiError(0, 'Could not reach the server.'))
    await flushPromises()

    // The twin of the case above: the stale guard is in the catch too, so a
    // late failure cannot repaint a page the newer request already filled.
    expect(request.state.value).toBe('success')
    expect(request.data.value).toBe('newer')
    expect(request.error.value).toBeNull()
  })
})
