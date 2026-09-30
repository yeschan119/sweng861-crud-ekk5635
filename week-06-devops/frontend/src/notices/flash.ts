import { reactive, readonly } from 'vue'

interface FlashState {
  message: string | null
}

// Global on purpose: a "saved" notice must outlive the page that set it (see App.vue and the router).
const state = reactive<FlashState>({ message: null })

export const flash = readonly(state)

export function showFlash(message: string): void {
  state.message = message
}

export function clearFlash(): void {
  state.message = null
}
