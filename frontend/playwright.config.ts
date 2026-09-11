import { defineConfig } from '@playwright/test'

// The e2e suite exercises the real stack end-to-end (Stage 6 SS16/17): it
// needs the FastAPI backend already running against the demo dataset on
// http://127.0.0.1:8123 (see README for the exact commands) — this config
// only starts the frontend dev server, since the backend's Postgres
// dependency and demo-scale warm-up are out of scope for Playwright to
// manage.
export default defineConfig({
  testDir: './e2e',
  // Stage 17 task 9: raised from 60s -- the login step alone has been
  // observed taking up to ~45s under this environment's memory pressure
  // (see the comment in e2e/demo-flow.spec.ts's login() helper); a
  // multi-step test that logs in and then navigates further needs
  // headroom beyond that single wait.
  timeout: 120_000,
  retries: 0,
  // Stage 17 task 9: this dev environment is memory-constrained (see
  // README/dev notes) -- one worker avoids running several Chromium
  // instances plus the backend plus the Vite dev server concurrently,
  // which was observed to trigger OS-level out-of-memory kills. This
  // does not weaken coverage (every spec still runs, just serially).
  workers: 1,
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'npm run dev -- --port 5173 --strictPort',
    url: 'http://localhost:5173',
    reuseExistingServer: true,
    timeout: 30_000,
  },
})
