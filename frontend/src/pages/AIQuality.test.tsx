import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { AIQuality } from './AIQuality'
import { renderWithProviders } from '../test/renderWithProviders'
import { EXPERIMENT_ID, GENERIC_AI_QUALITY_FIXTURE, apiGetMockImpl } from '../test/fixtures'

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client')
  return { ...actual, apiGet: vi.fn() }
})

function renderAIQuality() {
  return renderWithProviders(<AIQuality />, { route: `/experiments/${EXPERIMENT_ID}/ai-quality`, path: '/experiments/:experimentId/ai-quality' })
}

describe('AIQuality page — Stage 19 human review quality', () => {
  beforeEach(async () => {
    const client = await import('../api/client')
    vi.mocked(client.apiGet).mockImplementation(apiGetMockImpl)
  })

  it('shows the overall confirmation rate with a sample-size warning and the per-mechanism breakdown', async () => {
    renderAIQuality()

    await waitFor(() => expect(screen.getByText('Human review quality')).toBeInTheDocument())
    // 0.75 appears both as the overall confirmation rate and, separately,
    // as one confidence bucket's rate -- both are real, distinct numbers
    // in the fixture, so this only checks the value renders at all.
    expect(screen.getAllByText('75.0%').length).toBeGreaterThan(0)
    // (n=12) renders next to BOTH the confirmation and correction rate --
    // same overall counts, two cards.
    expect(screen.getAllByText('(n=12)').length).toBeGreaterThan(0)

    // Per-mechanism table: retrieval_failure has only 2 reviews -- flagged
    // (the same mechanism name also appears in the pre-existing failure
    // -mechanism-prevalence table above, hence getAllByText).
    expect(screen.getAllByText('retrieval failure').length).toBeGreaterThan(0)
    expect(screen.getAllByText('low sample').length).toBeGreaterThan(0)
  })

  it('shows the deterministic vs LLM-based detector-source comparison', async () => {
    renderAIQuality()
    await waitFor(() => expect(screen.getByText('Deterministic vs. LLM-based detectors')).toBeInTheDocument())
    expect(screen.getAllByText('mock llm').length).toBeGreaterThan(0)
    expect(screen.getAllByText('deterministic').length).toBeGreaterThan(0)
  })

  it('shows quality-over-time grouped by detector version, chronologically', async () => {
    renderAIQuality()
    await waitFor(() => expect(screen.getByText('Quality over time, by detector version')).toBeInTheDocument())
    expect(screen.getAllByText('rule_based_mock-v1').length).toBeGreaterThan(0)
    expect(screen.getByText('rule_based_mock-v2')).toBeInTheDocument()
  })

  it('shows the most common corrections (confusion pairs)', async () => {
    renderAIQuality()
    await waitFor(() => expect(screen.getByText('Most common corrections')).toBeInTheDocument())
    expect(screen.getAllByText('unnecessary clarification').length).toBeGreaterThan(0)
    expect(screen.getByText('wrong tool selection')).toBeInTheDocument()
  })

  it('distinguishes the offline benchmark section from the human-review section', async () => {
    renderAIQuality()
    await waitFor(() => expect(screen.getByText('Human review quality')).toBeInTheDocument())
    // hybrid_evaluation is null in this fixture (no real benchmark run
    // recorded), so the legacy classifier-evaluation section is the one
    // that renders -- still a clearly separate, offline-labeled card.
    expect(screen.getByText('Classifier evaluation (legacy exclusive-classifier shape)')).toBeInTheDocument()
  })

  it('shows an empty state instead of any rate when nothing has been reviewed yet', async () => {
    const client = await import('../api/client')
    vi.mocked(client.apiGet).mockImplementation(async (path: string, params?: Record<string, string | number | undefined>) => {
      if (path === `/api/v1/domains/commerce/experiments/${EXPERIMENT_ID}/ai-quality`) {
        return {
          ...GENERIC_AI_QUALITY_FIXTURE,
          human_review_quality: { ...GENERIC_AI_QUALITY_FIXTURE.human_review_quality, overall: { ...GENERIC_AI_QUALITY_FIXTURE.human_review_quality.overall, reviewed_count: 0 } },
        }
      }
      return apiGetMockImpl(path, params)
    })
    renderAIQuality()
    await waitFor(() => expect(screen.getByText(/No attributions have been reviewed yet/)).toBeInTheDocument())
  })
})
