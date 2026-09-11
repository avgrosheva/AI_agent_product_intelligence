"""Stage 19: turns human review outcomes
(backend.review.models.AttributionReview) into measurable
attribution-quality metrics — confirmation/correction rates, per-mechanism
and per-detector-source breakdowns, confidence-bucket calibration,
quality-over-time by detector/model/prompt version, and disagreement
(confusion-pair) analysis.

Pure computation over (ReviewableAttribution, ReviewResult) pairs already
fetched by the caller — no DB access of its own, matching
backend.analytics.experiment_results's own "takes a dataframe, doesn't
fetch it" convention. This module measures and surfaces review-based
quality; it never feeds back into detection (no retraining, no threshold
tuning, no prompt changes) — human review must not silently change
production behavior (Stage 19 task 7).

Every denominator here is reviewed_count, never total-detected count:
Stage 19 task 1's "do not treat unreviewed items as correct or incorrect"
means an attribution nobody has looked at yet contributes to NO rate
anywhere in this module — it simply isn't in the `reviews_by_key` a
caller passes in.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from backend.core.attribution import ReviewableAttribution
from backend.review.service import ReviewResult

# Stage 19 task 3: a simple, deterministic minimum-review threshold.
# Below this many REVIEWED items, a rate is reported as
# "insufficient_review_data" rather than a strong claim -- the raw counts
# are always still returned (a count of 1 or 2 is itself informative),
# but a RATE computed from under 10 reviews (e.g. "100%" from 1/1, or
# "50%" from 1/2) reads as far more confident than the sample actually
# supports. 10 matches this project's own established sparse-data
# convention for a minimum group size
# (backend.analytics.experiment_results.MIN_USERS_FOR_TEST) -- kept as
# its own constant rather than importing that one, since this counts
# REVIEWED ITEMS, a different unit than clustered users, and the two
# thresholds are free to diverge if experience shows they should.
MIN_REVIEWS_FOR_QUALITY_CLAIM = 10

SampleStatus = Literal["insufficient_review_data", "enough_data"]

# Stage 19 task 1: confidence calibration buckets -- does a
# higher-confidence detection actually get confirmed more often? The
# upper bound of the last bucket is inclusive of confidence == 1.0.
CONFIDENCE_BUCKETS: tuple[tuple[float, float], ...] = ((0.0, 0.5), (0.5, 0.7), (0.7, 0.9), (0.9, 1.0))


def _confidence_bucket_label(lo: float, hi: float) -> str:
    return f"{lo:.1f}-{hi:.1f}"


def _bucket_for_confidence(confidence: float) -> tuple[float, float] | None:
    last_index = len(CONFIDENCE_BUCKETS) - 1
    for i, (lo, hi) in enumerate(CONFIDENCE_BUCKETS):
        is_last_bucket = i == last_index
        if lo <= confidence < hi or (is_last_bucket and confidence == hi):
            return (lo, hi)
    return None


@dataclass(frozen=True)
class QualityCounts:
    reviewed_count: int
    confirmed_count: int
    rejected_count: int
    corrected_count: int
    confirmation_rate: float | None  # None only when reviewed_count == 0
    correction_rate: float | None
    sample_status: SampleStatus

    @staticmethod
    def from_reviews(reviews: list[ReviewResult]) -> "QualityCounts":
        reviewed = len(reviews)
        confirmed = sum(1 for r in reviews if r.decision == "confirmed")
        # "rejected" counts every rejection; "corrected" is the subset of
        # rejections where the reviewer also supplied what the mechanism
        # actually was (backend.review.service.submit_review's
        # corrected_mechanism) -- a plain reject with no correction is
        # still a rejection, just not a correction.
        rejected = sum(1 for r in reviews if r.decision == "rejected")
        corrected = sum(1 for r in reviews if r.decision == "rejected" and r.corrected_mechanism is not None)
        confirmation_rate = (confirmed / reviewed) if reviewed else None
        correction_rate = (corrected / reviewed) if reviewed else None
        status: SampleStatus = "enough_data" if reviewed >= MIN_REVIEWS_FOR_QUALITY_CLAIM else "insufficient_review_data"
        return QualityCounts(
            reviewed_count=reviewed, confirmed_count=confirmed, rejected_count=rejected, corrected_count=corrected,
            confirmation_rate=confirmation_rate, correction_rate=correction_rate, sample_status=status,
        )


@dataclass(frozen=True)
class MechanismQuality:
    failure_mode: str
    detector_source: str
    counts: QualityCounts


@dataclass(frozen=True)
class DetectorSourceQuality:
    detector_source: str  # "deterministic" | "semantic"
    counts: QualityCounts


@dataclass(frozen=True)
class ConfidenceBucketQuality:
    bucket_label: str
    bucket_min: float
    bucket_max: float
    counts: QualityCounts


@dataclass(frozen=True)
class AttributionQualityReport:
    overall: QualityCounts
    by_mechanism: list[MechanismQuality]
    by_detector_source: list[DetectorSourceQuality]
    by_confidence_bucket: list[ConfidenceBucketQuality]


def _reviewed_pairs(
    attributions: list[ReviewableAttribution], reviews_by_key: dict[tuple[str, str], ReviewResult]
) -> list[tuple[ReviewableAttribution, ReviewResult]]:
    return [(a, reviews_by_key[(a.session_id, a.failure_mode)]) for a in attributions if (a.session_id, a.failure_mode) in reviews_by_key]


def compute_attribution_quality(
    attributions: list[ReviewableAttribution], reviews_by_key: dict[tuple[str, str], ReviewResult]
) -> AttributionQualityReport:
    """`reviews_by_key`: (session_id, failure_mode) -> ReviewResult, for
    keys that were actually reviewed -- the same shape
    backend.review.service.list_review_queue already builds internally.
    Any attribution not present as a key is unreviewed and contributes to
    nothing here."""
    reviewed_pairs = _reviewed_pairs(attributions, reviews_by_key)
    overall = QualityCounts.from_reviews([r for _, r in reviewed_pairs])

    by_mechanism_reviews: dict[str, list[ReviewResult]] = {}
    by_mechanism_source: dict[str, str] = {}
    by_source_reviews: dict[str, list[ReviewResult]] = {}
    by_bucket_reviews: dict[tuple[float, float], list[ReviewResult]] = {}

    for a, r in reviewed_pairs:
        by_mechanism_reviews.setdefault(a.failure_mode, []).append(r)
        by_mechanism_source[a.failure_mode] = a.detector_source
        by_source_reviews.setdefault(a.detector_source, []).append(r)
        if a.confidence is not None:
            bucket = _bucket_for_confidence(a.confidence)
            if bucket is not None:
                by_bucket_reviews.setdefault(bucket, []).append(r)

    by_mechanism = [
        MechanismQuality(failure_mode=mode, detector_source=by_mechanism_source[mode], counts=QualityCounts.from_reviews(revs))
        for mode, revs in sorted(by_mechanism_reviews.items())
    ]
    by_detector_source = [
        DetectorSourceQuality(detector_source=source, counts=QualityCounts.from_reviews(revs))
        for source, revs in sorted(by_source_reviews.items())
    ]
    by_confidence_bucket = [
        ConfidenceBucketQuality(
            bucket_label=_confidence_bucket_label(lo, hi), bucket_min=lo, bucket_max=hi,
            counts=QualityCounts.from_reviews(by_bucket_reviews.get((lo, hi), [])),
        )
        for lo, hi in CONFIDENCE_BUCKETS
    ]

    return AttributionQualityReport(overall=overall, by_mechanism=by_mechanism, by_detector_source=by_detector_source, by_confidence_bucket=by_confidence_bucket)


@dataclass(frozen=True)
class VersionQualityBucket:
    detector_version: str
    provider: str | None
    model: str | None
    prompt_version: str | None
    first_seen: datetime
    last_seen: datetime
    counts: QualityCounts


def compute_quality_by_version(
    attributions: list[ReviewableAttribution], reviews_by_key: dict[tuple[str, str], ReviewResult]
) -> list[VersionQualityBucket]:
    """Groups REVIEWED attributions by their (detector_version, provider,
    model, prompt_version) tuple -- Stage 19 task 2: "whether attribution
    quality is degrading after a model/prompt/detector version change,"
    using the provenance already stored per-attribution
    (session_failure_attributions.detector_version/provider/model/
    prompt_version) rather than re-deriving it. Ordered by first_seen, so
    reading the list top-to-bottom is reading it chronologically -- a
    drop in confirmation_rate at a later bucket is a visible regression
    right after a version change."""
    buckets: dict[tuple, list[tuple[ReviewableAttribution, ReviewResult]]] = {}
    for a, r in _reviewed_pairs(attributions, reviews_by_key):
        version_key = (a.detector_version, a.provider, a.model, a.prompt_version)
        buckets.setdefault(version_key, []).append((a, r))

    results = [
        VersionQualityBucket(
            detector_version=detector_version, provider=provider, model=model, prompt_version=prompt_version,
            first_seen=min(a.created_at for a, _ in pairs), last_seen=max(a.created_at for a, _ in pairs),
            counts=QualityCounts.from_reviews([r for _, r in pairs]),
        )
        for (detector_version, provider, model, prompt_version), pairs in buckets.items()
    ]
    results.sort(key=lambda b: (b.first_seen, b.detector_version))
    return results


@dataclass(frozen=True)
class DisagreementItem:
    session_id: str
    experiment_id: str
    original_mechanism: str
    corrected_mechanism: str | None  # None: a plain rejection, no correction supplied
    original_confidence: float | None
    detector_source: str
    detector_version: str
    provider: str | None
    model: str | None
    prompt_version: str | None
    reviewed_at: datetime


@dataclass(frozen=True)
class ConfusionPair:
    original_mechanism: str
    corrected_mechanism: str
    count: int


@dataclass(frozen=True)
class DisagreementReport:
    items: list[DisagreementItem]
    confusion_pairs: list[ConfusionPair]


def compute_disagreement_analysis(
    attributions: list[ReviewableAttribution], reviews_by_key: dict[tuple[str, str], ReviewResult]
) -> DisagreementReport:
    """Stage 19 task 4: every rejected review (corrected or not) with the
    full provenance a reviewer or an engineer investigating a quality dip
    would need, plus the most common (original -> corrected) confusion
    pairs aggregated across them -- a pair only exists when a correction
    was actually supplied, a plain reject contributes to the item list
    but not to any confusion pair (there is nothing to pair it with)."""
    by_key = {(a.session_id, a.failure_mode): a for a in attributions}
    items: list[DisagreementItem] = []
    pair_counts: dict[tuple[str, str], int] = {}

    for key, review in reviews_by_key.items():
        if review.decision != "rejected":
            continue
        a = by_key.get(key)
        if a is None:
            continue
        items.append(DisagreementItem(
            session_id=a.session_id, experiment_id=a.experiment_id, original_mechanism=a.failure_mode,
            corrected_mechanism=review.corrected_mechanism, original_confidence=a.confidence,
            detector_source=a.detector_source, detector_version=a.detector_version, provider=a.provider,
            model=a.model, prompt_version=a.prompt_version, reviewed_at=review.updated_at,
        ))
        if review.corrected_mechanism is not None:
            pair_key = (a.failure_mode, review.corrected_mechanism)
            pair_counts[pair_key] = pair_counts.get(pair_key, 0) + 1

    items.sort(key=lambda i: (i.reviewed_at, i.session_id), reverse=True)
    confusion_pairs = sorted(
        (ConfusionPair(original_mechanism=o, corrected_mechanism=c, count=n) for (o, c), n in pair_counts.items()),
        key=lambda p: (-p.count, p.original_mechanism, p.corrected_mechanism),
    )
    return DisagreementReport(items=items, confusion_pairs=confusion_pairs)


def newest_version_per_mechanism(attributions: list[ReviewableAttribution]) -> dict[str, tuple[str, str | None, str | None, str | None]]:
    """failure_mode -> the (detector_version, provider, model,
    prompt_version) tuple that was FIRST SEEN most recently for that
    mechanism -- i.e. "which version was introduced last." Used by
    backend.review.service.list_review_queue (Stage 19 task 6) to
    prioritize reviewing items on a freshly-deployed version, which has
    no confirmation-rate track record yet. Deterministic: ties in
    first-seen timestamp are broken by the version tuple's own natural
    (lexicographic) ordering, never by dict/iteration order."""
    first_seen: dict[tuple[str, tuple], datetime] = {}
    for a in attributions:
        version_key = (a.detector_version, a.provider or "", a.model or "", a.prompt_version or "")
        k = (a.failure_mode, version_key)
        if k not in first_seen or a.created_at < first_seen[k]:
            first_seen[k] = a.created_at

    by_mode: dict[str, list[tuple[datetime, tuple]]] = {}
    for (mode, version_key), ts in first_seen.items():
        by_mode.setdefault(mode, []).append((ts, version_key))

    return {mode: max(entries, key=lambda e: (e[0], e[1]))[1] for mode, entries in by_mode.items()}
