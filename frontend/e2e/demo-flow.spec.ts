import { test, expect, type Page } from '@playwright/test'

// Stage 17 task 8: rewrite of the single monolithic Stage 6/16 happy-path
// test into focused specs covering the flows Stage 17 explicitly calls
// out -- login/explicit project selection, project switching, the
// commerce flow, the support flow, release evaluation, investigation,
// sessions/session detail, onboarding/config, and monitoring/release
// summary. Every wait below is either a URL match, a role/text/testid
// locator's own `.waitFor`/auto-waiting assertion, or an explicit
// `.waitFor({ state: 'visible' })` on a locator that may or may not
// exist yet (the project picker) -- no arbitrary `page.waitForTimeout`
// anywhere in this file.
//
// Requires `uvicorn backend.app.main:app --port 8123` already running
// against the demo-loaded database (see README "Running locally"), with
// a `demo@example.com` account that belongs to both the commerce demo
// project ("Demo Commerce") and a support project ("Support
// Walkthrough") -- the same two-project fixture Stage 16/17's manual
// walkthroughs used, needed here to exercise the project picker and
// project-switching flows for real (a single-project account never
// shows either).

const DEMO_EMAIL = 'demo@example.com'
const DEMO_PASSWORD = 'DevWalkthrough123!'
const COMMERCE_PROJECT_NAME = 'Demo Commerce'
const SUPPORT_PROJECT_NAME = 'Support Walkthrough'

async function login(page: Page) {
  await page.goto('/login')
  await page.getByLabel('Email').fill(DEMO_EMAIL)
  await page.getByLabel('Password').fill(DEMO_PASSWORD)
  await page.getByRole('button', { name: 'Sign in' }).click()
  // Stage 17 task 9: this dev environment is severely memory-constrained
  // (observed as low as several hundred MB free system-wide) -- under
  // load the login POST itself has been observed taking well over 15s
  // even though it resolves in under 1s at rest, because the backend,
  // Vite dev server, and Chromium are all competing for the same tight
  // memory budget for the run's duration. 45s gives real, if slow,
  // completion room without weakening what's actually asserted (still
  // exactly one navigation to "/", nothing about the wait itself is a
  // test assertion).
  await page.waitForURL('/', { timeout: 45_000 })
}

// The explicit project picker (`.selectable-card`, one per project) only
// renders when this account belongs to more than one project and none is
// yet active for this browser context; a returning session with a
// project already persisted in localStorage goes straight to Overview
// instead. Both are legitimate post-login states, so this is polled
// rather than assumed.
async function selectProjectIfPickerShown(page: Page, projectName: string) {
  const card = page.locator('.selectable-card', { hasText: projectName })
  const pickerShown = await card
    .waitFor({ state: 'visible', timeout: 8_000 })
    .then(() => true)
    .catch(() => false)
  if (pickerShown) await card.click()
}

async function switchActiveProject(page: Page, projectName: string) {
  const switcher = page.getByLabel('Switch active project')
  await expect(switcher).toBeVisible({ timeout: 10_000 })
  // Playwright's selectOption({ label }) requires an exact string, not a
  // RegExp (the label here is "{name} ({domain})", so an exact string
  // match would also work, but resolving the <option>'s own `value`
  // this way is more robust to that format changing).
  const optionValue = await switcher.locator('option', { hasText: projectName }).getAttribute('value')
  if (!optionValue) throw new Error(`No project switcher option found for "${projectName}"`)
  await switcher.selectOption(optionValue)
}

test.describe('auth and project selection', () => {
  test('login requires explicit project selection when the account belongs to more than one project', async ({ page }) => {
    await login(page)
    await expect(page.getByRole('heading', { name: 'Select a project' })).toBeVisible({ timeout: 10_000 })
    await expect(page.locator('.selectable-card', { hasText: COMMERCE_PROJECT_NAME })).toBeVisible({ timeout: 15_000 })
    await expect(page.locator('.selectable-card', { hasText: SUPPORT_PROJECT_NAME })).toBeVisible({ timeout: 15_000 })

    await page.locator('.selectable-card', { hasText: COMMERCE_PROJECT_NAME }).click()
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15_000 })
    await expect(page).not.toHaveURL(/\/login/)
  })

  test('an unauthenticated visit to a protected route redirects to login', async ({ page }) => {
    await page.goto('/sessions')
    await expect(page).toHaveURL(/\/login/, { timeout: 10_000 })
  })
})

test.describe('project switching', () => {
  test('switching the active project updates the sidebar and never pairs the new project with the old experiment', async ({ page }) => {
    await login(page)
    await selectProjectIfPickerShown(page, COMMERCE_PROJECT_NAME)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15_000 })
    await expect(page.locator('.sidebar-brand-sub')).toContainText('commerce')

    // Capture the commerce project's active experiment id from the
    // Investigation nav link's own href (`/experiments/{id}/investigation`)
    // -- this is the id Stage 17 task 1's race condition would leak into a
    // request for the NEW (support) project for one render.
    const investigationHref = await page.getByRole('link', { name: 'Investigation' }).getAttribute('href')
    const oldCommerceExperimentId = investigationHref?.match(/\/experiments\/([0-9a-f-]+)\//)?.[1]
    expect(oldCommerceExperimentId).toBeTruthy()

    // Regression coverage for the Stage 17 task 1 fix (stale
    // activeExperimentId surviving a project switch for one render,
    // producing a request that pairs the NEW project's domain with the
    // OLD project's experiment id): watch every network request issued
    // from the moment of the switch onward and fail if any support-domain
    // request names the old commerce experiment id.
    const mismatchedRequests: string[] = []
    page.on('request', (req) => {
      const url = req.url()
      if (url.includes('/domains/support/') && oldCommerceExperimentId && url.includes(oldCommerceExperimentId)) {
        mismatchedRequests.push(url)
      }
    })

    await switchActiveProject(page, SUPPORT_PROJECT_NAME)
    await expect(page.locator('.sidebar-brand-sub')).toContainText('support', { timeout: 15_000 })
    await expect(page.locator('.sidebar-brand-sub')).toContainText(SUPPORT_PROJECT_NAME)

    // Let the switch's own requests (experiments list, guardrails, etc.
    // for the newly-active support project) land, then assert none of
    // them leaked the stale commerce experiment id.
    await expect(page.locator('.sidebar-nav')).toBeVisible({ timeout: 15_000 })
    expect(mismatchedRequests).toEqual([])
  })
})

test.describe('commerce flow', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
    await selectProjectIfPickerShown(page, COMMERCE_PROJECT_NAME)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15_000 })
  })

  test('overview -> investigate -> finding -> sessions -> session detail -> AI quality -> HOLD', async ({ page }) => {
    // 1-2. Overview: ambiguous experiment, guardrail breach visible.
    await expect(page.getByText('Requires investigation')).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText('Breach detected')).toBeVisible({ timeout: 20_000 })

    // 3-4. Click Investigate, land on the project's configured primary metric.
    await page.getByRole('link', { name: /Investigate/i }).click()
    await expect(page).toHaveURL(/\/investigation/)
    await expect(page.getByRole('button', { name: 'Abandonment rate' })).toHaveClass(/active/, { timeout: 20_000 })

    // 5-6. Open the top constraint-heavy finding, see unnecessary-clarification evidence.
    // Anchored to the START of the finding button's accessible name (which
    // begins with its humanized segment label) rather than a bare
    // getByText substring match -- "constraint count bucket: 3+" is also
    // a substring of two OTHER findings' labels ("...+ platform: android"
    // and "...+ requested category: laptop"), and getByText matches
    // substrings by default, so an unanchored match risks resolving to
    // (and clicking) the wrong finding depending on DOM order.
    const topFinding = page.getByRole('button', { name: /^constraint count bucket: 3\+ v1/ })
    await expect(topFinding).toBeVisible({ timeout: 30_000 })
    await topFinding.click()
    await expect(page.getByText(/Mechanism: constraint count bucket: 3\+/)).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText('unnecessary clarification').first()).toBeVisible({ timeout: 15_000 })

    // 7-8. Open affected sessions, inspect one session's timeline.
    await page.getByRole('link', { name: /View sessions/i }).first().click()
    await expect(page).toHaveURL(/\/sessions\?/)
    const firstRow = page.locator('table.data-table tbody tr').first()
    await expect(firstRow).toBeVisible({ timeout: 15_000 })
    await firstRow.click()
    await expect(page).toHaveURL(/\/sessions\/[0-9a-f-]+/)
    await expect(page.getByText('Timeline')).toBeVisible({ timeout: 15_000 })

    // 9-10. Return to Investigation, inspect the Android finding's latency mechanism.
    await page.goBack()
    await page.goBack()
    await expect(page).toHaveURL(/\/investigation/)
    // Same anchoring rationale as topFinding above: "platform: android" on
    // its own is ALSO a substring of "constraint count bucket: 3+ +
    // platform: android" (a different finding, earlier in DOM order), so
    // an unanchored getByText().first() resolves to the wrong finding.
    const androidFinding = page.getByRole('button', { name: /^platform: android v1/ })
    await expect(androidFinding).toBeVisible({ timeout: 30_000 })
    await androidFinding.click()
    await expect(page.getByText(/Non-conversational mechanism: elevated Android latency/)).toBeVisible({ timeout: 15_000 })

    // 11. AI Quality, mock-classifier disclaimer visible.
    await page.getByRole('link', { name: 'AI Quality' }).click()
    await expect(page).toHaveURL(/\/ai-quality/)
    await expect(page.getByText(/Deterministic mock classifier/i)).toBeVisible({ timeout: 20_000 })

    // 12. Recommendation: HOLD, visible on Investigation.
    await page.getByRole('link', { name: 'Investigation' }).click()
    await expect(page.getByText('HOLD')).toBeVisible({ timeout: 30_000 })
    await expect(page.getByText('Decision rule result')).toBeVisible({ timeout: 15_000 })
  })

  test('sessions page filters are domain-driven, not hardcoded, and paginate with stable ordering', async ({ page }) => {
    await page.getByRole('link', { name: 'Sessions' }).click()
    await expect(page).toHaveURL(/\/sessions/)

    const totalLine = page.getByText(/sessions match · showing/)
    await expect(totalLine).toBeVisible({ timeout: 20_000 })
    const firstPageFirstRow = await page.locator('table.data-table tbody tr').first().locator('td').first().textContent()

    const nextButton = page.getByRole('button', { name: 'Next →' })
    await expect(nextButton).toBeEnabled()
    await nextButton.click()
    await expect(totalLine).toContainText('showing 26', { timeout: 15_000 })
    const secondPageFirstRow = await page.locator('table.data-table tbody tr').first().locator('td').first().textContent()
    expect(secondPageFirstRow).not.toBe(firstPageFirstRow)

    const prevButton = page.getByRole('button', { name: '← Previous' })
    await prevButton.click()
    await expect(totalLine).toContainText('showing 1-', { timeout: 15_000 })
  })
})

test.describe('support flow', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
    await selectProjectIfPickerShown(page, COMMERCE_PROJECT_NAME)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15_000 })
    await switchActiveProject(page, SUPPORT_PROJECT_NAME)
    await expect(page.locator('.sidebar-brand-sub')).toContainText('support', { timeout: 15_000 })
  })

  test('a domain with no primary metric configured shows the configuration prompt, not a broken chart', async ({ page }) => {
    // Stage 17 task 4: this is the "configuration missing" state,
    // distinct from loading/no-data/error -- support's demo project has
    // real ingested sessions but no primary_metric set yet.
    await expect(page.getByText(/primary metric configured yet/i)).toBeVisible({ timeout: 20_000 })
    await expect(page.getByRole('link', { name: /Configure a primary metric/i })).toBeVisible({ timeout: 15_000 })
  })

  test('sessions and session detail render the generic (non-commerce) shape', async ({ page }) => {
    await page.getByRole('link', { name: 'Sessions' }).click()
    await expect(page).toHaveURL(/\/sessions/)
    const firstRow = page.locator('table.data-table tbody tr').first()
    await expect(firstRow).toBeVisible({ timeout: 20_000 })
    await firstRow.click()
    await expect(page).toHaveURL(/\/sessions\/[0-9a-f-]+/)
    await expect(page.getByText('Timeline')).toBeVisible({ timeout: 15_000 })
    // A support session's domain chip reads "support", never a
    // commerce-only label leaking through the generic detail view.
    await expect(page.getByText('support', { exact: true })).toBeVisible({ timeout: 15_000 })
  })
})

test.describe('release evaluation and release summary', () => {
  test('commerce: an existing release decision renders its verdict, reasoning, and verdict history', async ({ page }) => {
    await login(page)
    await selectProjectIfPickerShown(page, COMMERCE_PROJECT_NAME)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15_000 })
    await page.getByRole('link', { name: 'Release Decision' }).click()
    await expect(page).toHaveURL(/\/release/)
    await expect(page.getByText('HOLD', { exact: true }).first()).toBeVisible({ timeout: 20_000 })
    await expect(page.getByRole('button', { name: /Evaluate now|Evaluating…/ })).toBeVisible({ timeout: 20_000 })
  })

  test('support: an experiment with no evaluation yet shows the empty state and an explicit way to run one', async ({ page }) => {
    await login(page)
    await selectProjectIfPickerShown(page, COMMERCE_PROJECT_NAME)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15_000 })
    await switchActiveProject(page, SUPPORT_PROJECT_NAME)
    await expect(page.locator('.sidebar-brand-sub')).toContainText('support', { timeout: 15_000 })

    await page.getByRole('link', { name: 'Release Decision' }).click()
    await expect(page).toHaveURL(/\/release/)
    await expect(page.getByText(/No release evaluation has been run yet/i)).toBeVisible({ timeout: 20_000 })
    await expect(page.getByRole('button', { name: /Evaluate now|Evaluating…/ })).toBeVisible({ timeout: 20_000 })
  })
})

test.describe('onboarding and project configuration', () => {
  test('the setup wizard steps through project config sections for the active project', async ({ page }) => {
    await login(page)
    await selectProjectIfPickerShown(page, COMMERCE_PROJECT_NAME)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15_000 })

    await page.getByRole('link', { name: 'Project Setup' }).click()
    await expect(page).toHaveURL(/\/setup/)
    await expect(page.getByRole('heading', { name: 'Project setup' })).toBeVisible({ timeout: 15_000 })

    // The active project (Demo Commerce) already has metrics/guardrails
    // configured, so these steps render real content, not an empty form.
    await page.getByRole('button', { name: 'Metrics' }).click()
    await expect(page.getByText(/primary metric/i).first()).toBeVisible({ timeout: 15_000 })

    await page.getByRole('button', { name: 'Guardrails' }).click()
    await expect(page.getByRole('heading', { name: 'Guardrails', level: 2 })).toBeVisible({ timeout: 15_000 })

    await page.getByRole('button', { name: 'Monitoring & notifications' }).click()
    await expect(page.getByRole('heading', { name: 'Scheduled monitoring' })).toBeVisible({ timeout: 15_000 })
  })
})

test.describe('project overview and monitoring', () => {
  test('project overview shows readiness, data quality, monitoring, and per-experiment release status', async ({ page }) => {
    await login(page)
    await selectProjectIfPickerShown(page, COMMERCE_PROJECT_NAME)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15_000 })

    await page.getByRole('link', { name: 'Project Overview' }).click()
    await expect(page).toHaveURL(/\/project/)
    await expect(page.getByRole('heading', { name: COMMERCE_PROJECT_NAME })).toBeVisible({ timeout: 15_000 })

    await expect(page.getByRole('heading', { name: 'Readiness' })).toBeVisible({ timeout: 15_000 })
    await expect(page.getByRole('heading', { name: 'Data quality' })).toBeVisible({ timeout: 15_000 })
    await expect(page.getByRole('heading', { name: 'Monitoring' })).toBeVisible({ timeout: 15_000 })

    await expect(page.getByRole('heading', { name: 'Latest release status' })).toBeVisible({ timeout: 15_000 })
    const releaseRow = page.locator('table.data-table tbody tr').first()
    await expect(releaseRow).toBeVisible({ timeout: 20_000 })
    await expect(releaseRow.getByText(/HOLD|SHIP|ROLLBACK|Not yet evaluated/)).toBeVisible({ timeout: 15_000 })
  })
})
