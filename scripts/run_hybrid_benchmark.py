"""Hybrid multi-label attribution benchmark (final evaluation for the
attribution redesign — AI_EVALUATION.md addendum).

Evaluates the two halves of the architecture independently, against the
independent multi-label ground truth (data/demo/validation_ground_truth
.parquet's truth_* columns, which the old single-label
ground_truth_failure_mode never had):

  1. Deterministic detectors (retrieval_failure, poor_ranking,
     wrong_tool_selection) — free, instant, no LLM call at all.
  2. The one semantic LLM call per session (unnecessary_clarification,
     wrong_constraint_interpretation, unsupported_product_claim) — real
     OpenRouter calls, same reliability configuration already proven
     (backend.llm.openrouter_client.build_chat_kwargs's semantic sibling,
     reasoning disabled, 900-token budget, strict validation, bounded
     retries, malformed/api_failure tracked separately, never folded into
     a normal prediction).

Two subsets, selected with --subset:

  new_holdout (the only one that counts as a final, unbiased benchmark):
    a fresh 200-session set, disjoint from the old exclusive-classifier
    dev set, stratified on the independent truth_* flags, constructed and
    persisted BEFORE any LLM call, never resampled after seeing
    predictions.

  old_dev (development data only, NOT a final benchmark): the OLD
    200-session set from the exclusive-classifier era (reports/final/
    development_set_200_exclusive_classifier/), re-scored here under the
    NEW architecture and NEW independent ground truth — informative
    (shows how the redesigned pipeline behaves on already-inspected
    sessions) but explicitly not the unbiased number, since those 200
    session_ids were inspected and tuned against twice already.

Usage:
  python -m scripts.run_hybrid_benchmark --subset new_holdout
  python -m scripts.run_hybrid_benchmark --subset old_dev
Resumable: reruns reuse the persisted subset and skip sessions already
recorded with status "success" for the semantic call.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine

from backend.app.db import get_database_url
from backend.llm.client import DETERMINISTIC_MECHANISMS, FAILURE_MECHANISMS, SEMANTIC_MECHANISMS
from backend.llm.context_builder import build_all_contexts
from backend.llm.deterministic_detectors import DETECTOR_VERSION, run_deterministic_detectors
from backend.llm.openrouter_client import (
    DEFAULT_MODEL,
    MAX_OUTPUT_TOKENS,
    OPENROUTER_BASE_URL,
    REASONING_CONFIG,
    MalformedResponseError,
    build_semantic_chat_kwargs,
    parse_and_validate_semantic,
)
from backend.llm.prompts.semantic_attribution import PROMPT_VERSION

EVAL_SEED = 42
SUBSET_SIZE = 200

# Minimums, not exact quotas: mechanisms overlap, so ordinary
# mutually-exclusive stratification doesn't apply. Sampled per-mechanism
# pool draws naturally overlap (a session satisfying two mechanisms can
# cover both quotas at once); remaining slots up to 200 are filled from
# sessions with no mechanism detected at all, for negative-class coverage.
MIN_POSITIVES = {
    "unnecessary_clarification": 35,
    "wrong_constraint_interpretation": 35,
    "unsupported_product_claim": 30,
    "retrieval_failure": 30,
    "poor_ranking": 30,
    "wrong_tool_selection": 30,
}

OLD_DEV_SUBSET_PATH = Path("reports/final/development_set_200_exclusive_classifier/llm_benchmark_200_subset.json")

TRANSIENT_MAX_RETRIES = 2
MALFORMED_MAX_RETRIES = 2
CONSECUTIVE_403_ABORT_THRESHOLD = 2

GROUND_TRUTH_PATH = Path("data/demo/validation_ground_truth.parquet")
PRICE_PER_INPUT_TOKEN = 2.0 / 1_000_000
PRICE_PER_OUTPUT_TOKEN = 10.0 / 1_000_000


class Aborted(Exception):
    pass


def _load_ground_truth() -> pd.DataFrame:
    gt = pd.read_parquet(GROUND_TRUTH_PATH)
    gt["session_id"] = gt["session_id"].astype(str)
    return gt


def build_new_holdout_subset(gt: pd.DataFrame, exclude_ids: set[str], seed: int = EVAL_SEED) -> list[str]:
    rng = np.random.default_rng(seed)
    pool = gt[~gt["session_id"].isin(exclude_ids)].set_index("session_id")
    selected: set[str] = set()

    for mech, quota in MIN_POSITIVES.items():
        mech_pool = pool.index[pool[f"truth_{mech}"]].tolist()
        already_covering = sum(1 for sid in mech_pool if sid in selected)
        still_needed = max(0, quota - already_covering)
        remaining = [sid for sid in mech_pool if sid not in selected]
        if len(remaining) < still_needed:
            raise ValueError(f"ground truth has only {len(remaining)} unselected '{mech}' positives, need {still_needed}")
        if still_needed:
            chosen = rng.choice(remaining, size=still_needed, replace=False)
            selected.update(chosen.tolist())

    truth_cols = [f"truth_{m}" for m in FAILURE_MECHANISMS]
    none_mask = ~pool[truth_cols].any(axis=1)
    none_pool = [sid for sid in pool.index[none_mask].tolist() if sid not in selected]
    rng.shuffle(none_pool)
    for sid in none_pool:
        if len(selected) >= SUBSET_SIZE:
            break
        selected.add(sid)

    subset_ids = sorted(selected)
    if len(subset_ids) > SUBSET_SIZE:
        # Overlap was lower than expected: trim deterministically. Every
        # quota was already satisfied above, so trimming risks only the
        # padding/none sessions, never a mechanism's minimum coverage,
        # PROVIDED trimming removes none-sessions first — enforced by
        # trimming from the end of the sorted id list only after confirming
        # every mechanism still meets its quota post-trim.
        candidate = subset_ids[:SUBSET_SIZE]
        candidate_set = set(candidate)
        for mech, quota in MIN_POSITIVES.items():
            covered = sum(1 for sid in candidate_set if pool.loc[sid, f"truth_{mech}"])
            if covered < quota:
                raise ValueError(f"trimming to {SUBSET_SIZE} would drop '{mech}' below its quota of {quota}")
        subset_ids = candidate
    return subset_ids


def prevalence(gt: pd.DataFrame, subset_ids: list[str]) -> dict:
    sub = gt[gt["session_id"].isin(subset_ids)]
    return {m: int(sub[f"truth_{m}"].sum()) for m in FAILURE_MECHANISMS}


def get_or_build_new_holdout(gt: pd.DataFrame, out_dir: Path) -> tuple[list[str], dict]:
    subset_path = out_dir / "semantic_holdout_200_subset.json"
    if subset_path.exists():
        meta = json.loads(subset_path.read_text(encoding="utf-8"))
        return meta["session_ids"], meta
    old_dev_meta = json.loads(OLD_DEV_SUBSET_PATH.read_text(encoding="utf-8"))
    exclude_ids = set(old_dev_meta["session_ids"])
    subset_ids = build_new_holdout_subset(gt, exclude_ids, seed=EVAL_SEED)
    meta = {
        "status": "FINAL HELD-OUT BENCHMARK — disjoint from the old 200-session development set, constructed before any LLM call, never resampled after seeing predictions.",
        "evaluation_seed": EVAL_SEED,
        "subset_size": len(subset_ids),
        "min_positive_quotas": MIN_POSITIVES,
        "prevalence": prevalence(gt, subset_ids),
        "session_ids": subset_ids,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    subset_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return subset_ids, meta


def score_deterministic(gt: pd.DataFrame, subset_ids: list[str], engine) -> dict:
    contexts = {str(c.session_id): c for c in build_all_contexts(engine, session_ids=subset_ids)}
    gt_by_id = gt.set_index("session_id")

    rows = []
    for sid in subset_ids:
        ctx = contexts.get(sid)
        if ctx is None:
            continue
        results = {r.mechanism: r.detected for r in run_deterministic_detectors(ctx)}
        row = {"session_id": sid, **{f"pred_{m}": results[m] for m in DETERMINISTIC_MECHANISMS}}
        rows.append(row)
    pred_df = pd.DataFrame(rows)
    merged = pred_df.merge(gt_by_id[[f"truth_{m}" for m in DETERMINISTIC_MECHANISMS]], on=None, left_on="session_id", right_index=True)

    per_mechanism = {}
    for m in DETERMINISTIC_MECHANISMS:
        y_true = merged[f"truth_{m}"].astype(bool)
        y_pred = merged[f"pred_{m}"].astype(bool)
        tp = int((y_true & y_pred).sum())
        fp = int((~y_true & y_pred).sum())
        fn = int((y_true & ~y_pred).sum())
        tn = int((~y_true & ~y_pred).sum())
        precision = tp / (tp + fp) if (tp + fp) > 0 else float("nan")
        recall = tp / (tp + fn) if (tp + fn) > 0 else float("nan")
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 and not (np.isnan(precision) or np.isnan(recall)) else float("nan")
        per_mechanism[m] = {
            "precision": precision, "recall": recall, "f1": f1,
            "support": int(y_true.sum()), "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        }
    return {"n_scored": len(merged), "per_mechanism": per_mechanism}


def _classify_semantic_one(client, ctx, state: dict) -> dict:
    last_error = None
    total_retries = 0
    for attempt in range(max(TRANSIENT_MAX_RETRIES, MALFORMED_MAX_RETRIES) + 1):
        t0 = time.monotonic()
        try:
            import openai

            response = client.chat.completions.create(**build_semantic_chat_kwargs(DEFAULT_MODEL, ctx))
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
                return {"status": "api_failure", "error": last_error, "retries": total_retries}
            time.sleep(2 ** (attempt + 1))
            continue
        except Exception as exc:
            state["consecutive_403"] = 0
            last_error = str(exc)
            total_retries += 1
            if attempt >= TRANSIENT_MAX_RETRIES:
                return {"status": "api_failure", "error": last_error, "retries": total_retries}
            time.sleep(2 ** (attempt + 1))
            continue

        state["consecutive_403"] = 0
        latency = time.monotonic() - t0
        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", None) if usage else None
        output_tokens = getattr(usage, "completion_tokens", None) if usage else None
        try:
            parsed = parse_and_validate_semantic(response.choices[0].message.content)
            return {
                "status": "success",
                "predictions": {m: parsed[m]["detected"] for m in SEMANTIC_MECHANISMS},
                "confidences": {m: parsed[m]["confidence"] for m in SEMANTIC_MECHANISMS},
                "latency_seconds": latency, "input_tokens": input_tokens, "output_tokens": output_tokens,
                "retries": total_retries,
            }
        except MalformedResponseError as exc:
            last_error = str(exc)
            total_retries += 1
            if attempt >= MALFORMED_MAX_RETRIES:
                return {
                    "status": "malformed_response", "error": last_error, "retries": total_retries,
                    "latency_seconds": latency, "input_tokens": input_tokens, "output_tokens": output_tokens,
                }
            continue

    return {"status": "api_failure", "error": last_error or "exhausted retries", "retries": total_retries}


def run_semantic_benchmark(subset_ids: list[str], engine, out_dir: Path, tag: str) -> dict:
    load_dotenv()
    import os

    import openai

    predictions_path = out_dir / f"{tag}_predictions.jsonl"
    existing: dict[str, dict] = {}
    if predictions_path.exists():
        for line in predictions_path.open("r", encoding="utf-8"):
            line = line.strip()
            if line:
                row = json.loads(line)
                existing[row["session_id"]] = row

    todo_ids = [sid for sid in subset_ids if existing.get(sid, {}).get("status") != "success"]
    print(f"[{tag}] {len(existing)} recorded, {sum(1 for r in existing.values() if r.get('status') == 'success')} successful, {len(todo_ids)} to (re)attempt")

    if todo_ids:
        client = openai.OpenAI(base_url=OPENROUTER_BASE_URL, api_key=os.environ["OPENROUTER_API_KEY"])
        contexts = {str(c.session_id): c for c in build_all_contexts(engine, session_ids=todo_ids)}
        state = {"consecutive_403": 0}
        aborted, abort_message = False, ""
        for i, sid in enumerate(todo_ids, start=1):
            ctx = contexts.get(sid)
            if ctx is None:
                row = {"session_id": sid, "status": "api_failure", "error": "session_id not found via build_all_contexts"}
            else:
                try:
                    result = _classify_semantic_one(client, ctx, state)
                except Aborted as exc:
                    aborted, abort_message = True, str(exc)
                    break
                row = {"session_id": sid, "prompt_version": PROMPT_VERSION, **result}
            existing[sid] = row
            if i % 25 == 0 or i == len(todo_ids):
                print(f"[{tag}]   attempted {i}/{len(todo_ids)}")
        if aborted:
            print(f"[{tag}] *** ABORTED: {abort_message} ***")
        out_dir.mkdir(parents=True, exist_ok=True)
        with predictions_path.open("w", encoding="utf-8") as f:
            for row in existing.values():
                f.write(json.dumps(row, default=str) + "\n")

    all_rows = [existing[sid] for sid in subset_ids if sid in existing]
    n_success = sum(1 for r in all_rows if r["status"] == "success")
    n_api_failure = sum(1 for r in all_rows if r["status"] == "api_failure")
    n_malformed = sum(1 for r in all_rows if r["status"] == "malformed_response")
    total_retries = sum(r.get("retries", 0) or 0 for r in all_rows)
    coverage = n_success / len(subset_ids)

    return {
        "n_success": n_success, "n_api_failure": n_api_failure, "n_malformed_response": n_malformed,
        "n_not_attempted": len(subset_ids) - len(all_rows), "total_retries": total_retries,
        "coverage": coverage, "is_valid": coverage >= 0.98, "rows": all_rows,
    }


def score_semantic(gt: pd.DataFrame, rows: list[dict]) -> dict:
    success_rows = [r for r in rows if r["status"] == "success"]
    gt_by_id = gt.set_index("session_id")

    records = []
    for r in success_rows:
        rec = {"session_id": r["session_id"]}
        for m in SEMANTIC_MECHANISMS:
            rec[f"pred_{m}"] = r["predictions"][m]
            rec[f"conf_{m}"] = r["confidences"][m]
        records.append(rec)
    df = pd.DataFrame(records)
    if df.empty:
        return {"n_scored": 0, "per_mechanism": {}}
    df = df.merge(gt_by_id[[f"truth_{m}" for m in SEMANTIC_MECHANISMS]], left_on="session_id", right_index=True)

    per_mechanism = {}
    hamming_errors = 0
    exact_matches = 0
    all_f1 = []
    supports = []
    for m in SEMANTIC_MECHANISMS:
        y_true = df[f"truth_{m}"].astype(bool)
        y_pred = df[f"pred_{m}"].astype(bool)
        tp = int((y_true & y_pred).sum())
        fp = int((~y_true & y_pred).sum())
        fn = int((y_true & ~y_pred).sum())
        tn = int((~y_true & ~y_pred).sum())
        precision = tp / (tp + fp) if (tp + fp) > 0 else float("nan")
        recall = tp / (tp + fn) if (tp + fn) > 0 else float("nan")
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 and not (np.isnan(precision) or np.isnan(recall)) else float("nan")
        conf_correct = df.loc[y_true == y_pred, f"conf_{m}"]
        conf_incorrect = df.loc[y_true != y_pred, f"conf_{m}"]
        per_mechanism[m] = {
            "precision": precision, "recall": recall, "f1": f1, "support": int(y_true.sum()),
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "mean_confidence_correct": float(conf_correct.mean()) if len(conf_correct) else float("nan"),
            "mean_confidence_incorrect": float(conf_incorrect.mean()) if len(conf_incorrect) else float("nan"),
        }
        hamming_errors += int((y_true != y_pred).sum())
        if not np.isnan(f1):
            all_f1.append(f1)
        supports.append(int(y_true.sum()))

    exact_match_mask = pd.Series(True, index=df.index)
    for m in SEMANTIC_MECHANISMS:
        exact_match_mask &= df[f"truth_{m}"].astype(bool) == df[f"pred_{m}"].astype(bool)
    exact_matches = int(exact_match_mask.sum())

    tp_total = sum(per_mechanism[m]["tp"] for m in SEMANTIC_MECHANISMS)
    fp_total = sum(per_mechanism[m]["fp"] for m in SEMANTIC_MECHANISMS)
    fn_total = sum(per_mechanism[m]["fn"] for m in SEMANTIC_MECHANISMS)
    micro_precision = tp_total / (tp_total + fp_total) if (tp_total + fp_total) > 0 else float("nan")
    micro_recall = tp_total / (tp_total + fn_total) if (tp_total + fn_total) > 0 else float("nan")
    micro_f1 = (2 * micro_precision * micro_recall / (micro_precision + micro_recall)) if (micro_precision + micro_recall) > 0 else float("nan")
    macro_f1 = float(np.mean(all_f1)) if all_f1 else float("nan")

    latencies = pd.Series([r["latency_seconds"] for r in success_rows if r.get("latency_seconds") is not None])
    input_tokens = sum(r.get("input_tokens") or 0 for r in success_rows)
    output_tokens = sum(r.get("output_tokens") or 0 for r in success_rows)
    cost = input_tokens * PRICE_PER_INPUT_TOKEN + output_tokens * PRICE_PER_OUTPUT_TOKEN

    return {
        "n_scored": len(df),
        "per_mechanism": per_mechanism,
        "micro_precision": micro_precision, "micro_recall": micro_recall, "micro_f1": micro_f1,
        "macro_f1": macro_f1,
        "exact_match_ratio": exact_matches / len(df) if len(df) else float("nan"),
        "hamming_loss": hamming_errors / (len(df) * len(SEMANTIC_MECHANISMS)) if len(df) else float("nan"),
        "latency_p50": float(latencies.quantile(0.5)) if len(latencies) else None,
        "latency_p95": float(latencies.quantile(0.95)) if len(latencies) else None,
        "input_tokens": input_tokens, "output_tokens": output_tokens,
        "cost_usd": cost, "cost_per_session": cost / len(success_rows) if success_rows else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--subset", choices=["new_holdout", "old_dev"], required=True)
    args = parser.parse_args()

    out_dir = Path("reports/final")
    gt = _load_ground_truth()
    engine = create_engine(get_database_url())

    if args.subset == "new_holdout":
        subset_ids, meta = get_or_build_new_holdout(gt, out_dir)
        tag = "semantic_holdout_200"
        print(f"new_holdout subset: {len(subset_ids)} sessions, prevalence={meta['prevalence']}")
    else:
        old_meta = json.loads(OLD_DEV_SUBSET_PATH.read_text(encoding="utf-8"))
        subset_ids = old_meta["session_ids"]
        tag = "old_dev_200_rescored"
        print(f"old_dev subset (reused, not resampled): {len(subset_ids)} sessions")

    det_result = score_deterministic(gt, subset_ids, engine)
    print(f"\n=== Deterministic detectors ({args.subset}) ===")
    for m, s in det_result["per_mechanism"].items():
        print(f"  {m}: precision={s['precision']:.3f} recall={s['recall']:.3f} f1={s['f1']:.3f} support={s['support']} fp={s['fp']} fn={s['fn']}")

    sem_run = run_semantic_benchmark(subset_ids, engine, out_dir, tag)
    print(f"\n=== Semantic LLM coverage ({args.subset}) ===")
    print(f"  success={sem_run['n_success']} api_failure={sem_run['n_api_failure']} malformed={sem_run['n_malformed_response']} "
          f"not_attempted={sem_run['n_not_attempted']} retries={sem_run['total_retries']} coverage={sem_run['coverage']:.1%} valid={sem_run['is_valid']}")

    sem_result = None
    if sem_run["is_valid"]:
        sem_result = score_semantic(gt, sem_run["rows"])
        print(f"\n=== Semantic LLM metrics ({args.subset}) ===")
        for m, s in sem_result["per_mechanism"].items():
            print(f"  {m}: precision={s['precision']:.3f} recall={s['recall']:.3f} f1={s['f1']:.3f} support={s['support']}")
        print(f"  micro_f1={sem_result['micro_f1']:.3f} macro_f1={sem_result['macro_f1']:.3f} "
              f"exact_match_ratio={sem_result['exact_match_ratio']:.3f} hamming_loss={sem_result['hamming_loss']:.3f}")
        print(f"  latency p50={sem_result['latency_p50']} p95={sem_result['latency_p95']}")
        print(f"  tokens in={sem_result['input_tokens']} out={sem_result['output_tokens']} cost=${sem_result['cost_usd']:.4f} cost/session=${sem_result['cost_per_session']:.5f}")
    else:
        print("\nEVALUATION INVALID for semantic metrics — insufficient coverage; not presenting F1 as final.")

    summary = {
        "subset": args.subset,
        "model": DEFAULT_MODEL,
        "prompt_version": PROMPT_VERSION,
        "detector_version": DETECTOR_VERSION,
        "reasoning_config": REASONING_CONFIG,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "evaluation_seed": EVAL_SEED,
        "subset_size": len(subset_ids),
        "deterministic": det_result,
        "semantic_coverage": {k: v for k, v in sem_run.items() if k != "rows"},
        "semantic_metrics": sem_result,
    }
    (out_dir / f"{tag}_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\nSummary written to {out_dir / f'{tag}_summary.json'}")


if __name__ == "__main__":
    main()
