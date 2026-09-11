"""Stage 19 task 1-4/11: pure-computation tests for
backend.review.quality — no DB, no HTTP, just (ReviewableAttribution,
ReviewResult) pairs in and a report out. Fast and deterministic by
construction, which is exactly what this module promises."""

from __future__ import annotations

from datetime import datetime

from backend.core.attribution import ReviewableAttribution
from backend.review.quality import (
    MIN_REVIEWS_FOR_QUALITY_CLAIM,
    ConfusionPair,
    compute_attribution_quality,
    compute_disagreement_analysis,
    compute_quality_by_version,
    newest_version_per_mechanism,
)
from backend.review.service import ReviewResult


def _attribution(sid: str, mode: str, source="semantic", confidence=0.8, version="v1", provider="openrouter", model="m1", prompt="p1", created="2026-01-01T00:00:00") -> ReviewableAttribution:
    return ReviewableAttribution(
        session_id=sid, experiment_id="exp-1", agent_version="v2", failure_mode=mode, detector_source=source,
        confidence=confidence, evidence_text="evidence", detector_version=version, provider=provider, model=model,
        prompt_version=prompt, created_at=datetime.fromisoformat(created),
    )


def _review(sid: str, mode: str, decision: str, corrected: str | None = None, updated="2026-01-02T00:00:00") -> ReviewResult:
    return ReviewResult(
        review_id=f"r-{sid}-{mode}", domain="commerce", session_id=sid, failure_mode=mode, decision=decision,
        corrected_mechanism=corrected, note=None, reviewer="analyst@example.com",
        created_at=datetime.fromisoformat(updated), updated_at=datetime.fromisoformat(updated),
    )


def test_unreviewed_attributions_never_contribute_to_any_rate():
    attributions = [_attribution("s1", "unnecessary_clarification"), _attribution("s2", "unnecessary_clarification")]
    # s2 was never reviewed -- reviews_by_key only has an entry for s1.
    reviews_by_key = {("s1", "unnecessary_clarification"): _review("s1", "unnecessary_clarification", "confirmed")}

    report = compute_attribution_quality(attributions, reviews_by_key)
    assert report.overall.reviewed_count == 1
    assert report.overall.confirmed_count == 1
    assert report.overall.confirmation_rate == 1.0


def test_confirmation_and_correction_rates_use_reviewed_count_as_the_denominator():
    attributions = [_attribution(f"s{i}", "unnecessary_clarification") for i in range(4)]
    reviews_by_key = {
        ("s0", "unnecessary_clarification"): _review("s0", "unnecessary_clarification", "confirmed"),
        ("s1", "unnecessary_clarification"): _review("s1", "unnecessary_clarification", "confirmed"),
        ("s2", "unnecessary_clarification"): _review("s2", "unnecessary_clarification", "rejected"),
        ("s3", "unnecessary_clarification"): _review("s3", "unnecessary_clarification", "rejected", corrected="wrong_tool_selection"),
    }

    counts = compute_attribution_quality(attributions, reviews_by_key).overall
    assert counts.reviewed_count == 4
    assert counts.confirmed_count == 2
    assert counts.rejected_count == 2  # both rejections, corrected or not
    assert counts.corrected_count == 1  # only the one with a supplied correction
    assert counts.confirmation_rate == 0.5
    assert counts.correction_rate == 0.25


def test_insufficient_review_data_below_the_threshold_enough_data_at_or_above_it():
    below = MIN_REVIEWS_FOR_QUALITY_CLAIM - 1
    attributions_below = [_attribution(f"s{i}", "unnecessary_clarification") for i in range(below)]
    reviews_below = {(f"s{i}", "unnecessary_clarification"): _review(f"s{i}", "unnecessary_clarification", "confirmed") for i in range(below)}
    assert compute_attribution_quality(attributions_below, reviews_below).overall.sample_status == "insufficient_review_data"

    at_threshold = MIN_REVIEWS_FOR_QUALITY_CLAIM
    attributions_at = [_attribution(f"s{i}", "unnecessary_clarification") for i in range(at_threshold)]
    reviews_at = {(f"s{i}", "unnecessary_clarification"): _review(f"s{i}", "unnecessary_clarification", "confirmed") for i in range(at_threshold)}
    assert compute_attribution_quality(attributions_at, reviews_at).overall.sample_status == "enough_data"


def test_zero_reviews_reports_none_rates_not_a_misleading_zero_or_hundred_percent():
    counts = compute_attribution_quality([], {}).overall
    assert counts.reviewed_count == 0
    assert counts.confirmation_rate is None
    assert counts.correction_rate is None
    assert counts.sample_status == "insufficient_review_data"


def test_per_mechanism_and_per_detector_source_breakdowns_are_independent():
    attributions = [
        _attribution("s1", "unnecessary_clarification", source="semantic"),
        _attribution("s2", "wrong_tool_selection", source="deterministic"),
    ]
    reviews_by_key = {
        ("s1", "unnecessary_clarification"): _review("s1", "unnecessary_clarification", "confirmed"),
        ("s2", "wrong_tool_selection"): _review("s2", "wrong_tool_selection", "rejected"),
    }
    report = compute_attribution_quality(attributions, reviews_by_key)

    by_mode = {m.failure_mode: m for m in report.by_mechanism}
    assert by_mode["unnecessary_clarification"].counts.confirmed_count == 1
    assert by_mode["wrong_tool_selection"].counts.rejected_count == 1

    by_source = {s.detector_source: s for s in report.by_detector_source}
    assert by_source["semantic"].counts.confirmed_count == 1
    assert by_source["deterministic"].counts.rejected_count == 1


def test_confidence_buckets_group_by_original_detection_confidence():
    attributions = [
        _attribution("s1", "m", confidence=0.2),
        _attribution("s2", "m", confidence=0.95),
        _attribution("s3", "m", confidence=1.0),
    ]
    reviews_by_key = {
        ("s1", "m"): _review("s1", "m", "rejected"),
        ("s2", "m"): _review("s2", "m", "confirmed"),
        ("s3", "m"): _review("s3", "m", "confirmed"),
    }
    report = compute_attribution_quality(attributions, reviews_by_key)
    by_label = {b.bucket_label: b for b in report.by_confidence_bucket}
    assert by_label["0.0-0.5"].counts.rejected_count == 1
    # 0.95 and 1.0 (inclusive upper bound) both land in the top bucket.
    assert by_label["0.9-1.0"].counts.confirmed_count == 2


def test_quality_by_version_groups_reviewed_items_by_detector_provenance_and_orders_chronologically():
    attributions = [
        _attribution("s1", "m", version="v1", created="2026-01-01T00:00:00"),
        _attribution("s2", "m", version="v1", created="2026-01-02T00:00:00"),
        _attribution("s3", "m", version="v2", created="2026-02-01T00:00:00"),
    ]
    reviews_by_key = {
        ("s1", "m"): _review("s1", "m", "confirmed"),
        ("s2", "m"): _review("s2", "m", "rejected"),
        ("s3", "m"): _review("s3", "m", "confirmed"),
    }
    buckets = compute_quality_by_version(attributions, reviews_by_key)
    assert [b.detector_version for b in buckets] == ["v1", "v2"]  # chronological
    assert buckets[0].counts.reviewed_count == 2
    assert buckets[0].counts.confirmed_count == 1
    assert buckets[1].counts.reviewed_count == 1
    assert buckets[1].counts.confirmed_count == 1


def test_disagreement_analysis_lists_rejections_and_aggregates_confusion_pairs():
    attributions = [
        _attribution("s1", "unnecessary_clarification", confidence=0.6),
        _attribution("s2", "unnecessary_clarification", confidence=0.7),
        _attribution("s3", "unnecessary_clarification", confidence=0.5),
    ]
    reviews_by_key = {
        ("s1", "unnecessary_clarification"): _review("s1", "unnecessary_clarification", "rejected", corrected="wrong_tool_selection"),
        ("s2", "unnecessary_clarification"): _review("s2", "unnecessary_clarification", "rejected", corrected="wrong_tool_selection"),
        ("s3", "unnecessary_clarification"): _review("s3", "unnecessary_clarification", "rejected"),  # no correction supplied
    }
    report = compute_disagreement_analysis(attributions, reviews_by_key)
    assert len(report.items) == 3
    assert report.confusion_pairs == [ConfusionPair(original_mechanism="unnecessary_clarification", corrected_mechanism="wrong_tool_selection", count=2)]


def test_confirmed_reviews_never_appear_in_disagreement_analysis():
    attributions = [_attribution("s1", "m")]
    reviews_by_key = {("s1", "m"): _review("s1", "m", "confirmed")}
    report = compute_disagreement_analysis(attributions, reviews_by_key)
    assert report.items == []
    assert report.confusion_pairs == []


def test_newest_version_per_mechanism_is_deterministic_and_picks_the_most_recently_introduced_version():
    attributions = [
        _attribution("s1", "m", version="v1", created="2026-01-01T00:00:00"),
        _attribution("s2", "m", version="v2", created="2026-02-01T00:00:00"),
        _attribution("s3", "m", version="v2", created="2026-02-05T00:00:00"),  # same version, later occurrence -- doesn't change "first seen"
    ]
    newest = newest_version_per_mechanism(attributions)
    assert newest["m"] == ("v2", "openrouter", "m1", "p1")


def test_newest_version_per_mechanism_breaks_ties_deterministically_by_version_tuple():
    # Two versions first-seen at the EXACT same instant -- must not depend
    # on dict/list iteration order.
    attributions = [
        _attribution("s1", "m", version="v-b", created="2026-01-01T00:00:00"),
        _attribution("s2", "m", version="v-a", created="2026-01-01T00:00:00"),
    ]
    newest = newest_version_per_mechanism(attributions)
    # "v-b" > "v-a" lexicographically, so it wins the tie both times this
    # runs, regardless of list order.
    assert newest["m"][0] == "v-b"
