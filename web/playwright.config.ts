import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright E2E test configuration for melosviz-web.
 *
 * Uses Chromium + WebKit in matrix mode. Auto-starts the Vite preview
 * server on port 4173 before running tests.
 *
 * @see https://playwright.dev/docs/test-configuration
 */
export default defineConfig({
  /* Directory containing E2E test files. */
  testDir: "./e2e",

  /* Run tests in files in parallel. */
  fullyParallel: true,

  /* Fail the build on CI if any test is left focused (test.only). */
  forbidOnly: !!process.env.CI,

  /* Retry on CI only. */
  retries: process.env.CI ? 2 : 0,

  /* Opt out of parallel on CI (single worker). */
  workers: process.env.CI ? 1 : undefined,

  /* Shared reporter. */
  reporter: "html",

  /* Shared settings for all projects. */
  use: {
    /* Base URL to use in actions like `await page.goto("/")`. */
    baseURL: "http://localhost:4173",

    /* Collect trace when retrying a failed test. */
    trace: "on-first-retry",
  },

  /* Browser project matrix. */
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "webkit",
      use: { ...devices["Desktop Safari"] },
    },
  ],

  /* Auto-start Vite preview server before tests. */
  webServer: {
    command: "npx vite preview --port 4173",
    port: 4173,
    reuseExistingServer: !process.env.CI,
  },
});
