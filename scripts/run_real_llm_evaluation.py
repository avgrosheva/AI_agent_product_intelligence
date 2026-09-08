"""LEGACY — evaluates the OLD exclusive 8-class classifier
(OpenRouterLLMClient.classify_failure), superseded by the hybrid
multi-label attribution redesign. Do not use this to evaluate the current
architecture (deterministic detectors + classify_semantic); use
scripts/run_hybrid_benchmark.py instead, which scores against the current
independent multi-label ground truth (`truth_*` columns).

Real LLM (OpenRouter) evaluation over a fixed, deterministic, stratified
subset of the demo dataset (AI_EVALUATION.md SS5 history; final-release
real-LLM requirement AT THE TIME).

Ground-truth usage boundary (Stage 2 review requirement #4, extended):
this script is the THIRD place — with tests/validate_ground_truth.py and
scripts/evaluate_classifier.py — permitted to open
validation_ground_truth.parquet, and it uses it in two clearly separated
phases:

  1. SAMPLING (before any LLM call): ground truth's failure_mode column is
     used only to pick which session_ids go into the subset, stratified so
     every observed class is represented and the two priority classes get
     extra weight. This is standard "build a labeled test set" practice —
     the model never sees this column, only session_ids come out of it.
  2. SCORING (strictly after every prediction has been written to disk in
     save_predictions() below): ground truth is joined against the saved
     predictions to compute the report. No prediction is ever adjusted,
     retried, or dropped based on how it compares to the label.

The model itself only ever receives a SessionContext (backend.llm.client),
built by backend.llm.context_builder — which has no code path that reads
ground truth at all, independent of anything in this script.

Usage: OPENROUTER_API_KEY=... python -m scripts.run_real_llm_evaluation
       [--data-dir data] [--profile demo] [--subset-size 460]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine

from backend.app.db import get_database_url
from backend.llm.client import FAILURE_TAXONOMY
from backend.llm.context_builder import build_all_contexts
from backend.llm.provenance import REAL_LLM_EVALUATION_SUMMARY_PATH, real_llm_classifier_version, write_real_llm_evaluation_summary
from scripts.evaluate_classifier import check_acceptance_bars, confidence_comparison, confusion_matrix, per_class_metrics

EVAL_SEED = 42

# Priority classes (unnecessary_clarification, wrong_constraint_interpretation)
# get a larger quota; every other class observed in ground truth gets a
# smaller but non-trivial quota; "none" (the majority/no-failure class) is
# included at a moderate count so accuracy/negative-class behavior is
# still measurable without dominating the subset. Total lands in the
# requested 300-500 range for this dataset's actual class support.
CLASS_QUOTAS = {
    "unnecessary_clarification": 80,
    "wrong_constraint_interpretation": 80,
    "retrieval_failure": 50,
    "wrong_tool_selection": 50,
    "poor_ranking": 50,
    "unsupported_product_claim": 50,
    "other": 50,
    "none": 100,
}

OUT_DIR = Path("reports/final")
SUBSET_METADATA_PATH = OUT_DIR / "real_llm_eval_subset.json"
PREDICTIONS_PATH = OUT_DIR / "real_llm_predictions.parquet"

# OpenRouter list pricing for anthropic/claude-sonnet-5 at the time this
# was written (USD per token) — an approximation for the cost estimate in
# the report, not a billing-accurate figure.
PRICE_PER_INPUT_TOKEN = 2.0 / 1_000_000
PRICE_PER_OUTPUT_TOKEN = 10.0 / 1_000_000


def build_stratified_subset(ground_truth: pd.DataFrame, seed: int = EVAL_SEED) -> pd.DataFrame:
    """Deterministic stratified sample across every failure_mode actually
    present in ground truth, capped per class by CLASS_QUOTAS (or all
    available rows if fewer exist than the quota)."""
    rng = np.random.default_rng(seed)
    parts = []
    for failure_mode in FAILURE_TAXONOMY:
        quota = CLASS_QUOTAS.get(failure_mode, 0)
        pool = ground_truth[ground_truth.ground_truth_failure_mode == failure_mode]
        if len(pool) == 0 or quota == 0:
            continue
        n = min(quota, len(pool))
        idx = rng.choice(pool.index.to_numpy(), size=n, replace=False)
        parts.append(pool.loc[idx])
    subset = pd.concat(parts, ignore_index=True) if parts else ground_truth.iloc[0:0]
    return subset.sort_values("session_id").reset_index(drop=True)


def save_predictions(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PREDICTIONS_PATH, index=False)
    return df


def compute_latency_distribution(latencies: pd.Series) -> dict:
    return {
        "min_s": float(latencies.min()),
        "p50_s": float(latencies.median()),
        "mean_s": float(latencies.mean()),
        "p95_s": float(latencies.quantile(0.95)),
        "max_s": float(latencies.max()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=str, default="data")
    parser.add_argument("--profile", type=str, default="demo")
    args = parser.parse_args()

    from backend.llm.openrouter_client import OpenRouterLLMClient

    try:
        client = OpenRouterLLMClient()
    except ModuleNotFoundError:
        print("The 'openai' package is required for the real-LLM evaluation: pip install -e \".[llm]\"", file=sys.stderr)
        sys.exit(1)
    except KeyError:
        print(
            "OPENROUTER_API_KEY is not set. Real-LLM evaluation cannot run without it — "
            "this is the one unresolved release item until a key is supplied.",
            file=sys.stderr,
        )
        sys.exit(1)

    # ---- Phase 1: sampling (ground truth used only to pick session_ids) ----
    ground_truth = pd.read_parquet(Path(args.data_dir) / args.profile / "validation_ground_truth.parquet")
    ground_truth["session_id"] = ground_truth["session_id"].astype(str)
    subset = build_stratified_subset(ground_truth)
    subset_ids = subset["session_id"].tolist()

    class_distribution = subset["ground_truth_failure_mode"].value_counts().to_dict()
    print(f"Stratified subset: {len(subset_ids)} sessions (seed={EVAL_SEED})")
    for mode, n in class_distribution.items():
        print(f"  {mode}: {n}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    subset_metadata = {
        "evaluation_seed": EVAL_SEED,
        "subset_size": len(subset_ids),
        "class_quotas": CLASS_QUOTAS,
        "class_distribution": class_distribution,
        "session_ids": subset_ids,
    }
    SUBSET_METADATA_PATH.write_text(json.dumps(subset_metadata, indent=2))

    # ---- Classify the subset only (never all 32k sessions) ----
    engine = create_engine(get_database_url())
    contexts = build_all_contexts(engine, session_ids=subset_ids)
    print(f"Built {len(contexts)} session contexts (observable data only). Classifying via OpenRouter ({client.model})...")

    prediction_rows = []
    n_fallback = 0
    for i, ctx in enumerate(contexts, start=1):
        result = client.classify_failure(ctx)
        if client.last_fallback:
            n_fallback += 1
        prediction_rows.append(
            {
                # context_builder yields ctx.session_id as whatever the DB
                # driver returns for a UUID column (a uuid.UUID object, not
                # a str) — cast explicitly so this matches ground_truth's
                # str-cast session_id column on merge below.
                "session_id": str(ctx.session_id),
                "predicted_mode": result.failure_mode,
                "confidence": result.confidence,
                "evidence_text": result.evidence_text,
                "latency_seconds": client.last_latency_seconds,
                "input_tokens": client.last_input_tokens,
                "output_tokens": client.last_output_tokens,
                "retry_count": client.last_retry_count,
                "fallback": client.last_fallback,
            }
        )
        if i % 50 == 0:
            print(f"  classified {i}/{len(contexts)}")

    # ---- Phase 2 checkpoint: predictions are now durably saved ----
    predictions_df = save_predictions(prediction_rows)
    print(f"Saved {len(predictions_df)} predictions to {PREDICTIONS_PATH} ({n_fallback} fell back after retries).")

    # ---- Phase 2: scoring (ground truth used only from here on) ----
    merged = predictions_df.merge(ground_truth, on="session_id", how="inner")
    cm = confusion_matrix(merged)
    per_class = per_class_metrics(cm)
    conf_cmp = confidence_comparison(merged)
    acceptance = check_acceptance_bars(per_class)
    all_bars_met = bool(acceptance.recall_pass.all() and acceptance.precision_pass.all())

    support = per_class["support"].to_numpy()
    f1 = per_class["f1"].to_numpy()
    valid = ~np.isnan(f1)
    macro_f1 = float(np.mean(f1[valid])) if valid.any() else float("nan")
    weighted_f1 = float(np.average(f1[valid], weights=support[valid])) if valid.any() and support[valid].sum() > 0 else float("nan")

    latency_dist = compute_latency_distribution(predictions_df["latency_seconds"].dropna())
    total_input_tokens = int(predictions_df["input_tokens"].dropna().sum())
    total_output_tokens = int(predictions_df["output_tokens"].dropna().sum())
    approx_cost_usd = total_input_tokens * PRICE_PER_INPUT_TOKEN + total_output_tokens * PRICE_PER_OUTPUT_TOKEN

    print("\n=== Confusion matrix (rows=ground truth, cols=predicted) ===")
    print(cm.to_string())
    print("\n=== Per-class precision/recall/F1 ===")
    print(per_class.to_string(index=False))
    print(f"\nMacro F1: {macro_f1:.4f}   Weighted F1: {weighted_f1:.4f}   Overall accuracy: {conf_cmp['overall_accuracy']:.4f}")
    print("\n=== Acceptance bars (priority classes) ===")
    print(acceptance.to_string(index=False))
    print(f"\nALL PRIORITY ACCEPTANCE BARS MET: {all_bars_met}")
    print(f"\nLatency: {latency_dist}")
    print(f"Tokens: input={total_input_tokens} output={total_output_tokens}  Approx. cost: ${approx_cost_usd:.4f}")

    summary = {
        "classifier_type": "real_llm",
        "provider": "openrouter",
        "model": client.model,
        "classifier_version": real_llm_classifier_version("openrouter", client.model),
        "prompt_version": client.prompt_version,
        "evaluation_seed": EVAL_SEED,
        "subset_size": len(subset_ids),
        "n_fallback_after_retries": n_fallback,
        "class_distribution": class_distribution,
        "confusion_matrix": cm.to_dict(),
        "per_class_metrics": per_class.to_dict(orient="records"),
        "macro_f1": macro_f1,
        "weighted_f1": weighted_f1,
        "overall_accuracy": conf_cmp["overall_accuracy"],
        "mean_confidence_correct": conf_cmp["mean_confidence_correct"],
        "mean_confidence_incorrect": conf_cmp["mean_confidence_incorrect"],
        "acceptance_bars": acceptance.to_dict(orient="records"),
        "acceptance_bars_met": all_bars_met,
        "latency_distribution": latency_dist,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "approx_cost_usd": approx_cost_usd,
    }
    write_real_llm_evaluation_summary(summary)
    print(f"\nReal-LLM evaluation summary written to {REAL_LLM_EVALUATION_SUMMARY_PATH}")


if __name__ == "__main__":
    main()
