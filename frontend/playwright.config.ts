import { defineConfig } from '@playwright/test'

// The e2e suite exercises the real stack end-to-end (Stage 6 SS16/17): it
// needs the FastAPI backend already running against the demo dataset on
// http://127.0.0.1:8123 (see README for the exact commands) — this config
// only starts the frontend dev server, since the backend's Postgres
// dependency and demo-scale warm-up are out of scope for Playwright to
// manage.
export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  retries: 0,
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
