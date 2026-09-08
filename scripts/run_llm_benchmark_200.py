"""LEGACY / DEVELOPMENT DATA ONLY — evaluates the OLD exclusive 8-class
classifier (OpenRouterLLMClient.classify_failure, backend.llm.prompts.
failure_classification), superseded by the hybrid multi-label attribution
redesign. This subset was inspected and tuned against during that
redesign — see reports/final/development_set_200_exclusive_classifier/,
where its results are archived. Do NOT treat output from this script as a
final or unbiased benchmark, and do not use it to evaluate the current
architecture (deterministic detectors + classify_semantic) — use
scripts/run_hybrid_benchmark.py for that.

Clean, portfolio-scale real-LLM benchmark: exactly 200 sessions, one
fixed stratified subset, OpenRouter + anthropic/claude-sonnet-5.

This is a separate, additive measurement script — it does not modify
backend/llm/classification_pipeline.py, ground truth, the Investigation
engine, statistical logic, the deterministic ship/hold rules, the
frontend, or README.md. It sends byte-for-byte the same request as
OpenRouterLLMClient (backend.llm.openrouter_client.build_chat_kwargs,
which embeds the current SYSTEM_PROMPT/model/max_tokens/reasoning config)
and validates responses with the same strict parser
(backend.llm.openrouter_client.parse_and_validate) — nothing about the
request shape or validation is reimplemented or allowed to drift here.

The one thing intentionally NOT reused is OpenRouterLLMClient.classify_failure
itself: that method collapses every failure (network, malformed JSON,
exhausted retries) into a normal-looking FailureClassification(failure_mode
="other"), which is exactly the methodological flaw this benchmark is
required to avoid (api_failure/malformed_response/retry_exhausted must
never become a normal class prediction). So this script calls the OpenAI
client directly and keeps failure statuses in a separate lane from real
predictions.

Usage: OPENROUTER_API_KEY=... python -m scripts.run_llm_benchmark_200
Resumable: rerunning reuses the same subset file and skips sessions
already recorded with status "success" in the predictions file.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine

from backend.app.db import get_database_url
from backend.llm.client import FAILURE_TAXONOMY
from backend.llm.context_builder import build_all_contexts
from backend.llm.openrouter_client import (
    DEFAULT_MODEL,
    MAX_OUTPUT_TOKENS,
    OPENROUTER_BASE_URL,
    REASONING_CONFIG,
    MalformedResponseError,
    build_chat_kwargs,
    parse_and_validate,
)
from backend.llm.prompts.failure_classification import PROMPT_VERSION
from scripts.evaluate_classifier import check_acceptance_bars, confidence_comparison, confusion_matrix, per_class_metrics
from scripts.run_real_llm_evaluation import PRICE_PER_INPUT_TOKEN, PRICE_PER_OUTPUT_TOKEN, compute_latency_distribution

EVAL_SEED = 42
SUBSET_SIZE = 200

BASE_QUOTAS = {
    "none": 40,
    "unnecessary_clarification": 35,
    "wrong_constraint_interpretation": 35,
    "wrong_tool_selection": 20,
    "retrieval_failure": 20,
    "poor_ranking": 20,
    "unsupported_product_claim": 20,
}
TOP_UP_QUOTAS = {"unnecessary_clarification": 5, "wrong_constraint_interpretation": 5}
CLASS_QUOTAS = {k: BASE_QUOTAS.get(k, 0) + TOP_UP_QUOTAS.get(k, 0) for k in set(BASE_QUOTAS) | set(TOP_UP_QUOTAS)}
assert sum(CLASS_QUOTAS.values()) == SUBSET_SIZE, f"quotas must sum to {SUBSET_SIZE}, got {sum(CLASS_QUOTAS.values())}"

TRANSIENT_MAX_RETRIES = 2  # bounded retries with backoff, matching the existing client's retry bound
MALFORMED_MAX_RETRIES = 2  # matches OpenRouterLLMClient.MAX_RETRIES
CONSECUTIVE_403_ABORT_THRESHOLD = 2  # "repeated" 403s -> stop the whole run

OUT_DIR = Path("reports/final")
SUBSET_PATH = OUT_DIR / "llm_benchmark_200_subset.json"
PREDICTIONS_PATH = OUT_DIR / "llm_benchmark_200_predictions.jsonl"
SUMMARY_PATH = OUT_DIR / "llm_benchmark_200_summary.json"


class Aborted(Exception):
    """Raised internally to stop the run immediately on repeated 403s."""


def build_stratified_subset_200(ground_truth: pd.DataFrame, seed: int = EVAL_SEED) -> pd.DataFrame:
    """Deterministic per-class stratified sample using the exact quotas
    specified for this benchmark. Same sampling method (rng.choice without
    replacement, per class) as scripts/run_real_llm_evaluation.py's
    build_stratified_subset — not reused directly only because the quotas
    differ, not because the method changed."""
    rng = np.random.default_rng(seed)
    parts = []
    for failure_mode in FAILURE_TAXONOMY:
        quota = CLASS_QUOTAS.get(failure_mode, 0)
        if quota == 0:
            continue
        pool = ground_truth[ground_truth.ground_truth_failure_mode == failure_mode]
        if len(pool) < quota:
            raise ValueError(f"ground truth has only {len(pool)} '{failure_mode}' sessions, need {quota}")
        idx = rng.choice(pool.index.to_numpy(), size=quota, replace=False)
        parts.append(pool.loc[idx])
    subset = pd.concat(parts, ignore_index=True)
    return subset.sort_values("session_id").reset_index(drop=True)


def load_existing_predictions() -> dict:
    if not PREDICTIONS_PATH.exists():
        return {}
    results = {}
    with PREDICTIONS_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            results[row["session_id"]] = row
    return results


def append_prediction(row: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with PREDICTIONS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")


def rewrite_predictions(results: dict) -> None:
    """Used only to persist an in-place update (e.g. a retried session
    overwriting a prior failed attempt) — appends would otherwise leave
    stale duplicate rows for the same session_id."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with PREDICTIONS_PATH.open("w", encoding="utf-8") as f:
        for row in results.values():
            f.write(json.dumps(row, default=str) + "\n")


def classify_one(client, ctx, state: dict) -> dict:
    """Returns a result row with a status in {success, api_failure,
    malformed_response}. Raises Aborted if repeated 403s are hit — the
    caller must stop the entire run, not just this session, when that
    happens."""
    last_error = None
    total_retries = 0
    for attempt in range(max(TRANSIENT_MAX_RETRIES, MALFORMED_MAX_RETRIES) + 1):
        t0 = time.monotonic()
        try:
            import openai

            response = client.chat.completions.create(**build_chat_kwargs(DEFAULT_MODEL, ctx))
        except openai.PermissionDeniedError as exc:
            state["consecutive_403"] += 1
            last_error = str(exc)
            total_retries += 1
            if state["consecutive_403"] >= CONSECUTIVE_403_ABORT_THRESHOLD:
                raise Aborted(f"{CONSECUTIVE_403_ABORT_THRESHOLD} consecutive 403 (key-limit) errors: {exc}") from exc
            time.sleep(2)
            continue
        except (openai.RateLimitError, openai.InternalServerError, openai.APIConnectionError, openai.APITimeoutError) as exc:
            state["consecutive_403"] = 0
            last_error = str(exc)
            total_retries += 1
            if attempt >= TRANSIENT_MAX_RETRIES:
                return {"status": "api_failure", "error": last_error, "retries": total_retries, "latency_seconds": time.monotonic() - t0}
            time.sleep(2 ** (attempt + 1))
            continue
        except Exception as exc:  # any other transport-level failure
            state["consecutive_403"] = 0
            last_error = str(exc)
            total_retries += 1
            if attempt >= TRANSIENT_MAX_RETRIES:
                return {"status": "api_failure", "error": last_error, "retries": total_retries, "latency_seconds": time.monotonic() - t0}
            time.sleep(2 ** (attempt + 1))
            continue

        state["consecutive_403"] = 0
        latency = time.monotonic() - t0
        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", None) if usage else None
        output_tokens = getattr(usage, "completion_tokens", None) if usage else None
        text_content = response.choices[0].message.content
        try:
            parsed = parse_and_validate(text_content)
            return {
                "status": "success",
                "predicted_mode": parsed["failure_mode"],
                "confidence": parsed["confidence"],
                "evidence_text": parsed["evidence_text"],
                "latency_seconds": latency,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "retries": total_retries,
            }
        except MalformedResponseError as exc:
            last_error = str(exc)
            total_retries += 1
            if attempt >= MALFORMED_MAX_RETRIES:
                return {
                    "status": "malformed_response",
                    "error": last_error,
                    "retries": total_retries,
                    "latency_seconds": latency,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                }
            continue

    return {"status": "api_failure", "error": last_error or "exhausted retries", "retries": total_retries, "latency_seconds": None}


def main() -> None:
    load_dotenv()
    import openai

    try:
        client = openai.OpenAI(base_url=OPENROUTER_BASE_URL, api_key=__import__("os").environ["OPENROUTER_API_KEY"])
    except KeyError:
        print("OPENROUTER_API_KEY is not set.", file=sys.stderr)
        sys.exit(1)

    ground_truth = pd.read_parquet(Path("data/demo/validation_ground_truth.parquet"))
    ground_truth["session_id"] = ground_truth["session_id"].astype(str)

    # ---- Subset: constructed and persisted before any model call ----
    if SUBSET_PATH.exists():
        subset_meta = json.loads(SUBSET_PATH.read_text())
        subset_ids = subset_meta["session_ids"]
        print(f"Reusing existing subset from {SUBSET_PATH} ({len(subset_ids)} sessions, seed={subset_meta['evaluation_seed']})")
    else:
        subset = build_stratified_subset_200(ground_truth)
        subset_ids = subset["session_id"].tolist()
        class_distribution = subset["ground_truth_failure_mode"].value_counts().to_dict()
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        subset_meta = {
            "evaluation_seed": EVAL_SEED,
            "subset_size": len(subset_ids),
            "class_quotas": CLASS_QUOTAS,
            "class_distribution": class_distribution,
            "session_ids": subset_ids,
        }
        SUBSET_PATH.write_text(json.dumps(subset_meta, indent=2))
        print(f"Built new subset: {len(subset_ids)} sessions (seed={EVAL_SEED}), saved to {SUBSET_PATH}")

    assert len(subset_ids) == SUBSET_SIZE

    existing = load_existing_predictions()
    todo_ids = [sid for sid in subset_ids if existing.get(sid, {}).get("status") != "success"]
    print(f"{len(existing)} predictions already recorded, {sum(1 for r in existing.values() if r.get('status') == 'success')} successful.")
    print(f"{len(todo_ids)} sessions to (re)attempt this run.")

    if todo_ids:
        engine = create_engine(get_database_url())
        contexts = {str(ctx.session_id): ctx for ctx in build_all_contexts(engine, session_ids=todo_ids)}
        state = {"consecutive_403": 0}
        aborted = False
        abort_message = ""
        for i, sid in enumerate(todo_ids, start=1):
            ctx = contexts.get(sid)
            if ctx is None:
                row = {"session_id": sid, "status": "api_failure", "error": "session_id not found via build_all_contexts"}
            else:
                try:
                    result = classify_one(client, ctx, state)
                except Aborted as exc:
                    aborted = True
                    abort_message = str(exc)
                    break
                row = {"session_id": sid, "prompt_version": PROMPT_VERSION, **result}
            existing[sid] = row
            append_prediction(row)
            if i % 25 == 0 or i == len(todo_ids):
                print(f"  attempted {i}/{len(todo_ids)}")

        if aborted:
            print(f"\n*** RUN ABORTED: {abort_message} ***")
            print("Stopping immediately per policy: repeated 403 key-limit errors are not converted into fallback labels.")

        # De-duplicate the append-only log (a resumed run may have retried
        # a session that already had a failed row from a prior attempt).
        rewrite_predictions(existing)

    # ---- Failure accounting (always computed, before any validity gate) ----
    all_rows = [existing[sid] for sid in subset_ids if sid in existing]
    n_success = sum(1 for r in all_rows if r["status"] == "success")
    n_api_failure = sum(1 for r in all_rows if r["status"] == "api_failure")
    n_malformed = sum(1 for r in all_rows if r["status"] == "malformed_response")
    n_attempted = len(all_rows)
    n_not_attempted = SUBSET_SIZE - n_attempted
    total_retries = sum(r.get("retries", 0) or 0 for r in all_rows)
    coverage = n_success / SUBSET_SIZE

    print("\n=== Failure accounting ===")
    print(f"successful real predictions: {n_success}")
    print(f"api_failure: {n_api_failure}")
    print(f"malformed_response: {n_malformed}")
    print(f"retry_exhausted (api_failure + malformed_response): {n_api_failure + n_malformed}")
    print(f"not attempted (run aborted early): {n_not_attempted}")
    print(f"total retries across all sessions: {total_retries}")
    print(f"coverage: {n_success}/{SUBSET_SIZE} = {coverage:.1%}")

    is_valid = coverage >= 0.98
    print(f"\n{'EVALUATION VALID' if is_valid else 'EVALUATION INVALID — insufficient real-LLM coverage'}")

    summary = {
        "provider": "openrouter",
        "model": DEFAULT_MODEL,
        "prompt_version": PROMPT_VERSION,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "reasoning_config": REASONING_CONFIG,
        "evaluation_seed": EVAL_SEED,
        "subset_size": SUBSET_SIZE,
        "class_quotas": CLASS_QUOTAS,
        "n_success": n_success,
        "n_api_failure": n_api_failure,
        "n_malformed_response": n_malformed,
        "n_not_attempted": n_not_attempted,
        "total_retries": total_retries,
        "coverage": coverage,
        "is_valid": is_valid,
    }

    if not is_valid:
        SUMMARY_PATH.write_text(json.dumps(summary, indent=2, default=str))
        print(f"\nSummary (invalid run) written to {SUMMARY_PATH}")
        return

    # ---- Scoring (only successful real predictions; coverage >= 98%) ----
    success_rows = [r for r in all_rows if r["status"] == "success"]
    predictions_df = pd.DataFrame(success_rows)[["session_id", "predicted_mode", "confidence", "latency_seconds", "input_tokens", "output_tokens"]]
    merged = predictions_df.merge(ground_truth, on="session_id", how="inner")
    assert len(merged) == n_success, "every successful prediction must join to ground truth"

    cm = confusion_matrix(merged)
    per_class = per_class_metrics(cm)
    conf_cmp = confidence_comparison(merged)
    acceptance = check_acceptance_bars(per_class)

    support = per_class["support"].to_numpy()
    f1 = per_class["f1"].to_numpy()
    valid_f1 = ~np.isnan(f1)
    macro_f1 = float(np.mean(f1[valid_f1])) if valid_f1.any() else float("nan")
    weighted_f1 = float(np.average(f1[valid_f1], weights=support[valid_f1])) if valid_f1.any() and support[valid_f1].sum() > 0 else float("nan")

    latency_dist = compute_latency_distribution(predictions_df["latency_seconds"].dropna())
    total_input_tokens = int(predictions_df["input_tokens"].dropna().sum())
    total_output_tokens = int(predictions_df["output_tokens"].dropna().sum())
    approx_cost_usd = total_input_tokens * PRICE_PER_INPUT_TOKEN + total_output_tokens * PRICE_PER_OUTPUT_TOKEN

    ground_truth_dist = merged["ground_truth_failure_mode"].value_counts().to_dict()
    predicted_dist = merged["predicted_mode"].value_counts().to_dict()

    print("\n=== Ground-truth class distribution (scored sessions) ===")
    print(ground_truth_dist)
    print("\n=== Predicted class distribution ===")
    print(predicted_dist)
    print("\n=== Confusion matrix (rows=ground truth, cols=predicted) ===")
    print(cm.to_string())
    print("\n=== Per-class precision/recall/F1 ===")
    print(per_class.to_string(index=False))
    print(f"\nMacro F1: {macro_f1:.4f}   Weighted F1: {weighted_f1:.4f}   Overall accuracy: {conf_cmp['overall_accuracy']:.4f}")
    print("\n=== Priority-class acceptance bars ===")
    print(acceptance.to_string(index=False))
    print(f"\nMean confidence (correct): {conf_cmp['mean_confidence_correct']:.4f}")
    print(f"Mean confidence (incorrect): {conf_cmp['mean_confidence_incorrect']:.4f}")
    print(f"\nLatency: {latency_dist}")
    print(f"Tokens: input={total_input_tokens} output={total_output_tokens}  avg_total/session={(total_input_tokens + total_output_tokens) / n_success:.0f}")
    print(f"Approx. total cost: ${approx_cost_usd:.4f}   approx. cost/session: ${approx_cost_usd / n_success:.5f}")

    summary.update(
        {
            "ground_truth_distribution": ground_truth_dist,
            "predicted_distribution": predicted_dist,
            "confusion_matrix": cm.to_dict(),
            "per_class_metrics": per_class.to_dict(orient="records"),
            "macro_f1": macro_f1,
            "weighted_f1": weighted_f1,
            "overall_accuracy": conf_cmp["overall_accuracy"],
            "priority_class_acceptance": acceptance.to_dict(orient="records"),
            "mean_confidence_correct": conf_cmp["mean_confidence_correct"],
            "mean_confidence_incorrect": conf_cmp["mean_confidence_incorrect"],
            "latency": latency_dist,
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "approx_cost_usd": approx_cost_usd,
            "approx_cost_per_session_usd": approx_cost_usd / n_success,
        }
    )
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, default=str))
    print(f"\nSummary written to {SUMMARY_PATH}")


if __name__ == "__main__":
    main()
