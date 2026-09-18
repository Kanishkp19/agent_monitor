import { defineConfig, mergeConfig } from 'vitest/config'

import viteConfig from './vite.config'

/**
 * Vitest config is kept out of `vite.config.ts` deliberately.
 *
 * The pinned vitest (2.1) bundles its own Vite 5 for the test runner while the
 * app builds on Vite 6.4. Importing `vitest/config` into the build config
 * would pull both sets of types into one file and produce a skew error that
 * has nothing to do with either tool being wrong. See DEVIATIONS.md D-08.
 */
export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: './src/test/setup.ts',
      include: ['src/**/*.{test,spec}.{ts,tsx}'],
    },
  }),
)
