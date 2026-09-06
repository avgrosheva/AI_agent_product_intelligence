import type { SegmentFilter } from '../api/types'

/** Builds the exact Sessions-screen query string for a finding's segment,
 * so "View sessions" reproduces the same population the finding was
 * computed over (Stage 6 SS6: "must open this screen with the relevant
 * filters already applied"). */
export function sessionsUrlForSegment(experimentId: string, segment: SegmentFilter, extra?: Record<string, string>): string {
  const params = new URLSearchParams({ experiment_id: experimentId, ...segment.dimensions, ...extra })
  return `/sessions?${params.toString()}`
}
