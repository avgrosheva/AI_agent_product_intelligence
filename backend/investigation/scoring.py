"""Segment scan, Benjamini-Hochberg correction, and excess-contribution
(EC) scoring (INVESTIGATION.md SS1-SS3; Stage 2 review requirements #2, #3).

Every per-segment comparison goes through `experiment_results.analyze_metric`
— the same cluster-aware (user-level), sample-size-gated function used for
the Stage 2 metric table. This module adds no separate, session-level
inference path: Stage 2 review requirement #2 explicitly forbids falling
back to session-independent inference anywhere in the scan.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from backend.analytics import metric_registry
from backend.analytics.experiment_results import MetricResult, analyze_metric
from backend.analytics.stats.correction import benjamini_hochberg
from backend.investigation.segments import Segment, build_segment_registry
from backend.investigation.thresholds import BH_Q, MIN_ABSOLUTE_EFFECT_RATE, MIN_COHENS_D


@dataclass
class SegmentScanRow:
    segment: Segment
    result: MetricResult
    bh_significant: bool = False
    excess_contribution: float | None = None
    meets_min_effect: bool = False


def run_segment_scan(df: pd.DataFrame, primary_metric_name: str) -> list[SegmentScanRow]:
    """One cluster-aware comparison per candidate segment (INVESTIGATION.md SS1-SS3 steps 1-2)."""
    metric = metric_registry.get(primary_metric_name)
    segments = build_segment_registry()
    rows: list[SegmentScanRow] = []
    for seg in segments:
        mask = seg.mask_fn(df)
        result = analyze_metric(df, metric, segment_label=seg.label, segment_mask=mask)
        rows.append(SegmentScanRow(segment=seg, result=result))
    return rows


def apply_bh_correction(rows: list[SegmentScanRow], q: float = BH_Q) -> list[SegmentScanRow]:
    """BH correction applied ONLY across this bounded, pre-registered scan
    (STATISTICS.md SS6; Stage 2 review requirement #3) — never expanded to
    a larger search space."""
    testable_idx = [i for i, r in enumerate(rows) if r.result.verdict != "insufficient_evidence" and r.result.p_value is not None]
    if not testable_idx:
        return rows
    p_values = [rows[i].result.p_value for i in testable_idx]
    rejected = benjamini_hochberg(p_values, q=q)
    for i, is_significant in zip(testable_idx, rejected):
        rows[i].bh_significant = bool(is_significant)
    return rows


def _meets_min_effect(row: SegmentScanRow, metric_def) -> bool:
    r = row.result
    if r.cluster_mean_v1 is None or r.cluster_mean_v2 is None:
        return False
    if metric_def.is_rate_metric:
        return abs(r.cluster_mean_v2 - r.cluster_mean_v1) >= MIN_ABSOLUTE_EFFECT_RATE
    if r.effect_size_value is None:
        return False
    return abs(r.effect_size_value) >= MIN_COHENS_D


def compute_excess_contribution(df: pd.DataFrame, rows: list[SegmentScanRow], primary_metric_name: str, overall_result: MetricResult) -> list[SegmentScanRow]:
    """EC(s) = user_share(s) x (segment_delta(s) - overall_delta) (INVESTIGATION.md SS2, as revised)."""
    metric_def = metric_registry.get(primary_metric_name)
    total_users = df["user_id"].nunique()
    overall_delta = None
    if overall_result.cluster_mean_v1 is not None and overall_result.cluster_mean_v2 is not None:
        overall_delta = overall_result.cluster_mean_v2 - overall_result.cluster_mean_v1

    for row in rows:
        row.meets_min_effect = _meets_min_effect(row, metric_def)
        r = row.result
        if overall_delta is None or r.cluster_mean_v1 is None or r.cluster_mean_v2 is None:
            row.excess_contribution = None
            continue
        segment_delta = r.cluster_mean_v2 - r.cluster_mean_v1
        n_users_segment = r.n_users_v1 + r.n_users_v2
        user_share = n_users_segment / total_users if total_users else 0.0
        row.excess_contribution = user_share * (segment_delta - overall_delta)
    return rows


def rank_findings(rows: list[SegmentScanRow], top_k: int) -> list[SegmentScanRow]:
    """Segments must pass correction + minimum effect size before ranking
    (INVESTIGATION.md SS3 step 4); ranked by |EC(s)| (step 5)."""
    passing = [
        r for r in rows
        if r.bh_significant and r.meets_min_effect and r.excess_contribution is not None
    ]
    passing.sort(key=lambda r: abs(r.excess_contribution), reverse=True)
    return passing[:top_k]


def scan_to_dataframe(rows: list[SegmentScanRow]) -> pd.DataFrame:
    out = []
    for row in rows:
        r = row.result
        out.append(
            {
                "segment": row.segment.label,
                "dimensions": ",".join(row.segment.dimensions),
                "n_users_v1": r.n_users_v1,
                "n_users_v2": r.n_users_v2,
                "cluster_mean_v1": r.cluster_mean_v1,
                "cluster_mean_v2": r.cluster_mean_v2,
                "p_value": r.p_value,
                "bh_significant": row.bh_significant,
                "effect_size_value": r.effect_size_value,
                "meets_min_effect": row.meets_min_effect,
                "excess_contribution": row.excess_contribution,
                "verdict": r.verdict,
            }
        )
    return pd.DataFrame(out)
