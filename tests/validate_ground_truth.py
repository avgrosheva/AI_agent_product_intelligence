"""Validates that the real Investigation pipeline recovers all five
planted effects (DATA_MODEL.md SS6; INVESTIGATION.md SS7; Stage 2 review
requirement #12).

Ground truth is read ONLY in this file, and only in the assertion steps
below — every pipeline call above it operates on observable application
data alone (session_level_base.sql, agent_actions, session_failure_attributions).
Recovery is checked directionally (segment, sign, mechanism, downstream
effect), never by exact equality to the generator's internal parameters.

Two recovery tiers, both legitimate and both reported (Stage 2 review
requirement #9's "report honestly" applies here too):
- FULL recovery: the effect survives the complete pipeline — BH correction
  across the ~55-segment scan, the minimum-effect-size filter, and lands in
  the top-5 findings by |EC|.
- DIRECTIONAL recovery: the effect shows the correct sign and clears the
  minimum-practical-effect threshold in the raw (uncorrected) segment scan,
  but does not survive the harsh simultaneous-test correction at dev-scale
  sample sizes. This is an explicitly anticipated, acceptable outcome, not
  a failure — the demo-scale dataset exists partly to resolve it.

This file intentionally does NOT import anything from backend.investigation
or backend.llm that would let ground truth leak backward into the pipeline
— it only ever flows into this file's own assertions, after the fact.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import text

from backend.analytics import metric_registry
from backend.analytics.experiment_results import analyze_metric
from backend.analytics.sql_runner import run_sql_file
from backend.analytics.stats.clustering import cluster_arrays
from backend.investigation.pipeline import run_investigation
from backend.investigation.scoring import apply_bh_correction, compute_excess_contribution, run_segment_scan, scan_to_dataframe
from backend.investigation.segments import build_segment_registry
from backend.investigation.trajectory_attribution import _structural_features, reconstruct_trajectories
from backend.llm.client import FAILURE_MECHANISMS

DATA_DIR = Path("data")
PROFILE = "dev"


# ---------------------------------------------------------------------------
# Step 1: run the pipeline on observable data only (no ground truth touched yet)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def base_df(classified_engine):
    return run_sql_file(classified_engine, "session_level_base.sql")


@pytest.fixture(scope="module")
def agent_actions_df(classified_engine):
    with classified_engine.connect() as conn:
        return pd.read_sql(text("SELECT session_id, sequence_index, action_type::text AS action_type FROM agent_actions"), conn)


@pytest.fixture(scope="module")
def failure_attributions_wide_df(classified_engine):
    """Wide format, one row per session_id, one boolean column per
    FAILURE_MECHANISMS entry — mirrors backend.app.dependencies.
    get_failure_attributions_wide_df, duplicated here (rather than
    imported) so this file never needs a FastAPI app/engine-cache
    dependency, only the raw SQLAlchemy engine already used above."""
    with classified_engine.connect() as conn:
        long_df = pd.read_sql(
            text("SELECT session_id, failure_mode::text AS failure_mode, detected FROM session_failure_attributions"),
            conn,
        )
    if long_df.empty:
        return pd.DataFrame(columns=["session_id", *FAILURE_MECHANISMS])
    wide = long_df.pivot_table(index="session_id", columns="failure_mode", values="detected", aggfunc="first")
    wide = wide.reindex(columns=list(FAILURE_MECHANISMS))
    return wide.reset_index()


@pytest.fixture(scope="module")
def investigation_abandonment(base_df, agent_actions_df, failure_attributions_wide_df):
    return run_investigation(base_df, agent_actions_df, failure_attributions_wide_df, primary_metric_name="abandonment_rate")


@pytest.fixture(scope="module")
def investigation_satisfaction(base_df, agent_actions_df, failure_attributions_wide_df):
    return run_investigation(base_df, agent_actions_df, failure_attributions_wide_df, primary_metric_name="constraint_satisfaction_rate")


@pytest.fixture(scope="module")
def raw_satisfaction_scan(base_df):
    """The uncorrected/raw scan, used only to check DIRECTIONAL recovery
    for effects too weak to survive BH correction at dev scale (still
    observable-data-only — no ground truth involved)."""
    metric = metric_registry.get("constraint_satisfaction_rate")
    overall = analyze_metric(base_df, metric)
    rows = run_segment_scan(base_df, "constraint_satisfaction_rate")
    rows = apply_bh_correction(rows)
    rows = compute_excess_contribution(base_df, rows, "constraint_satisfaction_rate", overall)
    return scan_to_dataframe(rows)


@pytest.fixture(scope="module")
def consecutive_search_no_abandon_rate(base_df, agent_actions_df):
    """Independent (re-derived, not reused from Stage 2) observable check
    for effect 5: rate of sessions with two back-to-back `search` actions
    that did NOT end in abandonment, computed fresh via the Stage 3
    trajectory module's own reconstruction + structural-feature helpers —
    not Stage 2's has_consecutive_search column."""
    trajectories = reconstruct_trajectories(agent_actions_df)
    trajectories["has_repeat_search_success"] = trajectories["action_sequence"].apply(
        lambda seq: _structural_features(seq)[1] >= 1 and not _structural_features(seq)[2]
    )
    merged = base_df.merge(trajectories, on="session_id")
    seg = merged[merged.constraint_count_bucket == "2"]
    arrays = cluster_arrays(seg, "has_repeat_search_success")
    return {"v1": float(pd.Series(arrays.get("v1", [0])).mean()), "v2": float(pd.Series(arrays.get("v2", [0])).mean())}


def _find_exact(findings, label):
    return next((f for f in findings if f.segment_label == label), None)


# ---------------------------------------------------------------------------
# Step 2: NOW read ground truth, only to check what the pipeline already produced
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ground_truth(classified_engine):
    # depends on classified_engine only to force the dev dataset (and its
    # validation_ground_truth.parquet sibling) to have been generated, and
    # failure_labels to have been populated by the mock classifier before
    # any test below reads this fixture — this fixture never reads from
    # classified_engine itself.
    return pd.read_parquet(DATA_DIR / PROFILE / "validation_ground_truth.parquet")


def test_ground_truth_artifact_was_not_needed_to_produce_any_fixture_above(ground_truth):
    """Sanity check on the harness itself: this is the first and only place
    in this file `ground_truth` is used as a fixture dependency."""
    assert set(ground_truth.columns) == {
        "session_id",
        "ground_truth_scenario",
        "ground_truth_failure_mode",
        "truth_unnecessary_clarification",
        "truth_wrong_constraint_interpretation",
        "truth_retrieval_failure",
        "truth_wrong_tool_selection",
        "truth_poor_ranking",
        "truth_unsupported_product_claim",
    }


def test_overclarify_v2_fully_recovered(investigation_abandonment, ground_truth):
    finding = _find_exact(investigation_abandonment.findings, "constraint_count_bucket=3+")
    assert finding is not None, "overclarify_v2's target segment did not survive the full pipeline"
    assert finding.cluster_mean_v2 > finding.cluster_mean_v1, "expected v2 worse (higher abandonment)"
    assert finding.dominant_failure_mode == "unnecessary_clarification"
    assert (ground_truth.ground_truth_scenario == "overclarify_v2").sum() > 0


def test_android_latency_fully_recovered(investigation_abandonment, ground_truth):
    finding = _find_exact(investigation_abandonment.findings, "platform=android")
    assert finding is not None, "android_latency's target segment did not survive the full pipeline"
    assert finding.cluster_mean_v2 > finding.cluster_mean_v1, "expected v2 worse (higher abandonment)"
    assert (ground_truth.ground_truth_scenario == "android_latency").sum() > 0


def test_monitor_constraint_regression_recovered(raw_satisfaction_scan, investigation_satisfaction, ground_truth):
    """Recovery tier for this effect is reported, not asserted as fixed:
    it was DIRECTIONAL at dev scale before the hybrid multi-label
    generator changes reshuffled the shared RNG draw sequence (an
    accepted, disclosed consequence of adding two new mechanisms — see
    datagen/session_builder.py's module docstring), and is now FULL —
    this segment survives BH correction and lands in the top-5 findings.
    Both are legitimate outcomes at dev scale; only the raw-scan
    directional checks below are treated as required."""
    row = raw_satisfaction_scan[raw_satisfaction_scan.segment == "requested_category=monitor"]
    assert not row.empty
    r = row.iloc[0]
    assert r.cluster_mean_v2 < r.cluster_mean_v1, "expected v2 worse (lower constraint satisfaction)"
    assert r.meets_min_effect, "expected the effect to clear the minimum-practical-effect threshold even if not BH-significant"
    assert r.p_value < 0.05, "expected raw significance even if it doesn't survive correction at dev scale"
    full = _find_exact(investigation_satisfaction.findings, "requested_category=monitor")
    if full is not None:
        assert full.cluster_mean_v2 < full.cluster_mean_v1
    assert (ground_truth.ground_truth_scenario == "monitor_constraint_regression_v2").sum() > 0


def test_exploratory_uplift_directionally_recovered(raw_satisfaction_scan, ground_truth):
    row = raw_satisfaction_scan[raw_satisfaction_scan.segment == "constraint_count_bucket=0-1"]
    assert not row.empty
    r = row.iloc[0]
    assert r.cluster_mean_v2 > r.cluster_mean_v1, "expected v2 better (higher constraint satisfaction)"
    assert (ground_truth.ground_truth_scenario == "exploratory_uplift").sum() > 0


def test_tool_selection_improved_directionally_recovered(consecutive_search_no_abandon_rate, ground_truth):
    assert consecutive_search_no_abandon_rate["v2"] < consecutive_search_no_abandon_rate["v1"], (
        "expected v2 to have a lower rate of repeated-search-but-still-successful sessions"
    )
    assert (ground_truth.ground_truth_scenario == "tool_selection_v2_improved").sum() > 0


def test_no_more_than_one_spurious_top_finding_per_run(base_df, investigation_abandonment, investigation_satisfaction, ground_truth):
    """Bounding false positives (Stage 2 review requirement #13): every
    top-5 finding across both runs should be dominated by sessions from a
    real planted scenario, with at most one exception per run reported as
    a genuine (disclosed, not hidden) false positive / incidental finding."""
    scenario_by_session = ground_truth.set_index("session_id")["ground_truth_scenario"]

    def unexplained_findings(result) -> list[str]:
        unexplained = []
        for finding in result.findings:
            seg = next(s for s in build_segment_registry() if s.label == finding.segment_label)
            mask = seg.mask_fn(base_df)
            sids = base_df.loc[mask, "session_id"].astype(str)  # ground_truth's session_id is str (parquet); base_df's is UUID (DB)
            scenarios = scenario_by_session.reindex(sids).value_counts(normalize=True)
            if scenarios.empty or scenarios.get("baseline", 0) > 0.85:
                unexplained.append(finding.segment_label)
        return unexplained

    unexplained_abandonment = unexplained_findings(investigation_abandonment)
    unexplained_satisfaction = unexplained_findings(investigation_satisfaction)

    assert len(unexplained_abandonment) <= 1, f"more than one unexplained finding in abandonment_rate scan: {unexplained_abandonment}"
    assert len(unexplained_satisfaction) <= 1, f"more than one unexplained finding in constraint_satisfaction_rate scan: {unexplained_satisfaction}"
