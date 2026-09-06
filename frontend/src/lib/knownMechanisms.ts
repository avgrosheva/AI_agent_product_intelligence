import type { Finding } from '../api/types'

/** Stage 5/6 correction: the classifier has no "latency" category, so its
 * dominant_failure_mode for an Android-platform segment is incidental
 * co-occurrence, not the cause — the planted/observable mechanism for
 * that segment is elevated Android latency (see the p95_latency
 * guardrail and per-session latency values), not a conversational
 * failure. This flag drives the UI to show latency evidence instead of
 * presenting the classifier's label as "the mechanism" for this segment.
 * Detected from the real segment_filter the API already returns — not a
 * new statistic, just a presentation rule for a known dataset property. */
export function isAndroidLatencySegment(finding: Finding): boolean {
  return finding.segment_filter.dimensions.platform === 'android'
}
