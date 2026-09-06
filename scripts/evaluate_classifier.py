"""Offline evaluation of the failure classifier against planted ground
truth (AI_EVALUATION.md SS5; Stage 2 review requirement #9 — mandatory).

This is the ONLY script, besides tests/validate_ground_truth.py, permitted
to read validation_ground_truth.parquet. It reads the app's failure_labels
(classifier predictions, source='llm_classifier') and the validation
artifact (ground truth, source of truth for this evaluation only) and
joins them in this process — never inside backend/investigation or
backend/llm, which must never see this file.

Usage: python -m scripts.evaluate_classifier [--data-dir data] [--profile dev]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

from backend.app.db import get_database_url
from backend.llm.client import FAILURE_TAXONOMY
from backend.llm.provenance import read_classifier_metadata, write_evaluation_summary

# Acceptance bars (AI_EVALUATION.md SS5): recall >= 0.7, precision >= 0.6
# for the two classes that matter most to the Investigation story.
PRIORITY_CLASSES = {"unnecessary_clarification": {"recall": 0.7, "precision": 0.6},
                     "wrong_constraint_interpretation": {"recall": 0.7, "precision": 0.6}}


def load_predictions(engine) -> pd.DataFrame:
    with engine.connect() as conn:
        df = pd.read_sql(
            text("SELECT session_id, failure_mode::text AS predicted_mode, confidence FROM failure_labels WHERE source = 'llm_classifier'"),
            conn,
        )
    df["session_id"] = df["session_id"].astype(str)
    return df


def load_ground_truth(data_dir: Path, profile: str) -> pd.DataFrame:
    gt = pd.read_parquet(data_dir / profile / "validation_ground_truth.parquet")
    gt["session_id"] = gt["session_id"].astype(str)
    return gt[["session_id", "ground_truth_failure_mode"]]


def confusion_matrix(merged: pd.DataFrame) -> pd.DataFrame:
    return pd.crosstab(merged["ground_truth_failure_mode"], merged["predicted_mode"], dropna=False).reindex(
        index=list(FAILURE_TAXONOMY), columns=list(FAILURE_TAXONOMY), fill_value=0
    )


def per_class_metrics(cm: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for label in FAILURE_TAXONOMY:
        tp = cm.loc[label, label]
        fn = cm.loc[label, :].sum() - tp
        fp = cm.loc[:, label].sum() - tp
        precision = tp / (tp + fp) if (tp + fp) > 0 else float("nan")
        recall = tp / (tp + fn) if (tp + fn) > 0 else float("nan")
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 and not np.isnan(precision) and not np.isnan(recall) else float("nan")
        rows.append({"failure_mode": label, "support": int(cm.loc[label, :].sum()), "precision": precision, "recall": recall, "f1": f1})
    return pd.DataFrame(rows)


def confidence_comparison(merged: pd.DataFrame) -> dict:
    correct = merged[merged.predicted_mode == merged.ground_truth_failure_mode]
    incorrect = merged[merged.predicted_mode != merged.ground_truth_failure_mode]
    return {
        "mean_confidence_correct": float(correct.confidence.mean()) if len(correct) else float("nan"),
        "mean_confidence_incorrect": float(incorrect.confidence.mean()) if len(incorrect) else float("nan"),
        "n_correct": len(correct),
        "n_incorrect": len(incorrect),
        "overall_accuracy": len(correct) / len(merged) if len(merged) else float("nan"),
    }


def check_acceptance_bars(per_class: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for label, bars in PRIORITY_CLASSES.items():
        row = per_class[per_class.failure_mode == label].iloc[0]
        rows.append(
            {
                "failure_mode": label,
                "recall": row.recall,
                "recall_bar": bars["recall"],
                "recall_pass": bool(row.recall >= bars["recall"]) if not np.isnan(row.recall) else False,
                "precision": row.precision,
                "precision_bar": bars["precision"],
                "precision_pass": bool(row.precision >= bars["precision"]) if not np.isnan(row.precision) else False,
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=str, default="data")
    parser.add_argument("--profile", type=str, default="dev")
    args = parser.parse_args()

    engine = create_engine(get_database_url())
    predictions = load_predictions(engine)
    ground_truth = load_ground_truth(Path(args.data_dir), args.profile)
    merged = predictions.merge(ground_truth, on="session_id", how="inner")

    print(f"Evaluated {len(merged)} sessions ({len(predictions)} predictions, {len(ground_truth)} ground-truth rows)")

    cm = confusion_matrix(merged)
    print("\n=== Confusion matrix (rows=ground truth, cols=predicted) ===")
    print(cm.to_string())

    per_class = per_class_metrics(cm)
    print("\n=== Per-class precision/recall/F1 ===")
    print(per_class.to_string(index=False))

    conf_cmp = confidence_comparison(merged)
    print("\n=== Confidence comparison ===")
    for k, v in conf_cmp.items():
        print(f"  {k}: {v}")

    acceptance = check_acceptance_bars(per_class)
    print("\n=== Acceptance bars (AI_EVALUATION.md SS5) ===")
    print(acceptance.to_string(index=False))
    all_pass = bool(acceptance.recall_pass.all() and acceptance.precision_pass.all())
    print(f"\nALL ACCEPTANCE BARS MET: {all_pass}")

    out_dir = Path("reports/stage3")
    out_dir.mkdir(parents=True, exist_ok=True)
    cm.to_csv(out_dir / "classifier_confusion_matrix.csv")
    per_class.to_csv(out_dir / "classifier_per_class_metrics.csv", index=False)
    acceptance.to_csv(out_dir / "classifier_acceptance_bars.csv", index=False)

    meta = read_classifier_metadata()
    if meta is not None:
        write_evaluation_summary(
            classifier_type=meta.classifier_type,
            classifier_version=meta.classifier_version,
            summary={
                "n_sessions_evaluated": len(merged),
                "overall_accuracy": conf_cmp["overall_accuracy"],
                "mean_confidence_correct": conf_cmp["mean_confidence_correct"],
                "mean_confidence_incorrect": conf_cmp["mean_confidence_incorrect"],
                "acceptance_bars_met": all_pass,
                "acceptance_bars": acceptance.to_dict(orient="records"),
                "per_class_metrics": per_class.to_dict(orient="records"),
                "confusion_matrix": cm.to_dict(),
            },
        )
        print(f"\nEvaluation summary recorded for classifier_type={meta.classifier_type} version={meta.classifier_version}")
    else:
        print("\nWARNING: no classifier_metadata.json found — run scripts.run_classification first so this evaluation can be tied to a specific classifier version.")


if __name__ == "__main__":
    main()
