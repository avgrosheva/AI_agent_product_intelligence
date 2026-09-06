import { test, expect } from '@playwright/test'

// Stage 6 SS16/17: one end-to-end happy-path test covering the primary
// demo flow (SS14, steps 1-12) against the real backend + demo dataset —
// requires `uvicorn backend.app.main:app --port 8123` already running
// against the demo-loaded database (see README "Running locally").
test('primary demo flow: overview -> investigate -> finding -> session -> android -> AI quality -> HOLD', async ({ page }) => {
  // 1-2. Overview: ambiguous experiment, abandonment/latency issue visible.
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15_000 })
  await expect(page.getByText('Requires investigation')).toBeVisible()
  await expect(page.getByText('Breach detected')).toBeVisible()

  // 3-4. Click Investigate, land on abandonment lens (default).
  await page.getByRole('link', { name: /Investigate/i }).click()
  await expect(page).toHaveURL(/\/investigation/)
  await expect(page.getByRole('button', { name: 'Abandonment' })).toHaveClass(/active/)

  // 5-6. Open the top constraint-heavy finding, see unnecessary-clarification evidence.
  const topFinding = page.getByText('constraint count bucket: 3+').first()
  await expect(topFinding).toBeVisible({ timeout: 30_000 })
  await topFinding.click()
  await expect(page.getByText(/Mechanism: constraint count bucket: 3\+/)).toBeVisible()
  await expect(page.getByText('unnecessary clarification').first()).toBeVisible()

  // 7-8. Open affected sessions, inspect one session's timeline.
  await page.getByRole('link', { name: /View sessions/i }).first().click()
  await expect(page).toHaveURL(/\/sessions\?/)
  const firstRow = page.locator('table.data-table tbody tr').first()
  await expect(firstRow).toBeVisible({ timeout: 15_000 })
  await firstRow.click()
  await expect(page).toHaveURL(/\/sessions\/[0-9a-f-]+/)
  await expect(page.getByText('Timeline')).toBeVisible()

  // 9-10. Return to Investigation, inspect the Android finding's latency mechanism.
  await page.goBack()
  await page.goBack()
  await expect(page).toHaveURL(/\/investigation/)
  const androidFinding = page.getByText('platform: android').first()
  await expect(androidFinding).toBeVisible({ timeout: 30_000 })
  await androidFinding.click()
  await expect(page.getByText(/Non-conversational mechanism: elevated Android latency/)).toBeVisible()

  // 11. View AI Quality, confirm the mock-classifier disclaimer is visible.
  await page.getByRole('link', { name: 'AI Quality' }).click()
  await expect(page).toHaveURL(/\/ai-quality/)
  await expect(page.getByText(/Deterministic mock classifier/i)).toBeVisible({ timeout: 15_000 })

  // 12. Recommendation: HOLD, visible on the Investigation screen.
  await page.getByRole('link', { name: 'Investigation' }).click()
  await expect(page.getByText('HOLD')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByText('Decision rule result')).toBeVisible()
})
