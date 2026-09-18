import { fileURLToPath } from 'node:url'
import { mergeConfig, defineConfig, configDefaults } from 'vitest/config'
import viteConfig from './vite.config'

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      // Integration specs need the backend running; `npm run test:integration` opts in.
      exclude: [...configDefaults.exclude, 'e2e/**', 'src/__tests__/integration/**'],
      root: fileURLToPath(new URL('./', import.meta.url)),
      coverage: {
        provider: 'v8',
        // Application code only: main.ts is wiring with no branches, and specs are not the product.
        include: ['src/**/*.{ts,vue}'],
        exclude: ['src/main.ts', 'src/__tests__/**'],
        reporter: ['text', 'html'],
        // The grading gate; the run fails below any of these.
        thresholds: { lines: 80, statements: 80, branches: 80, functions: 80 },
      },
    },
  }),
)
