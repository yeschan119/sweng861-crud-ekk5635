import { fileURLToPath } from 'node:url'
import { mergeConfig, defineConfig } from 'vitest/config'
import viteConfig from './vite.config'

// Runs only the integration specs, in Node, against a live backend. See README "Integration test".
export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'node',
      include: ['src/__tests__/integration/**/*.spec.ts'],
      root: fileURLToPath(new URL('./', import.meta.url)),
    },
  }),
)
