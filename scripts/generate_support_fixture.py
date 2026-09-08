"""Generates a small, deterministic, entirely non-commerce fixture dataset
(a hypothetical support-ticket-triage agent) proving the generic
ingestion/adapter layers work for a domain with no products, no
recommendations, no shopping vocabulary at all (Stage 3 task 6).

Planted effect (for the comparison proof, not a rigorous statistical
demo): v2's "smart routing" raises resolution_rate and lowers handle time,
at the cost of a slightly higher escalation_rate — deliberately small
enough that the escalation guardrail (backend.domains.support.guardrails,
threshold 0.05 absolute) does NOT breach, so the demo shows a clean "ship"
signal from a totally different domain's own metrics/guardrails.

Usage: python -m scripts.generate_support_fixture [--out data/fixtures/support_sessions.json] [--seed 7] [--n-users 150]
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

TICKET_CATEGORIES = ["billing", "technical", "account_access", "shipping_status", "general_inquiry"]
AGENT_OPENERS = [
    "Thanks for reaching out — I can help with that.",
    "Sorry for the trouble, let's get this sorted.",
    "I've pulled up your account, one moment.",
]
USER_OPENERS = {
    "billing": "I was charged twice this month, can you check?",
    "technical": "The app keeps crashing when I open settings.",
    "account_access": "I can't log in, it says my password is wrong.",
    "shipping_status": "My order hasn't arrived and tracking hasn't updated.",
    "general_inquiry": "Can you tell me more about your premium plan?",
}


def build_fixture(seed: int, n_users: int) -> dict:
    rng = np.random.default_rng(seed)
    experiment_id = "support-routing-v2-2026"
    experiments = [
        {
            "external_experiment_id": experiment_id,
            "name": "Smart Ticket Routing v2",
            "control_version": "v1",
            "treatment_version": "v2",
            "start_date": "2026-06-01",
            "end_date": "2026-06-30",
        }
    ]

    sessions = []
    session_start = datetime(2026, 6, 1, 9, 0, 0)
    for user_idx in range(n_users):
        agent_version = "v1" if rng.random() < 0.5 else "v2"
        n_sessions_for_user = int(rng.integers(1, 3))
        for s in range(n_sessions_for_user):
            category = str(rng.choice(TICKET_CATEGORIES))
            # planted effect: v2 resolves more often and faster, escalates
            # slightly more often (small, guardrail-safe trade-off)
            resolve_p = 0.62 if agent_version == "v1" else 0.80
            escalate_p_given_unresolved = 0.35 if agent_version == "v1" else 0.45
            handle_time_base = 420 if agent_version == "v1" else 260

            outcome_roll = rng.random()
            if outcome_roll < resolve_p:
                outcome_label = "resolved"
            elif rng.random() < escalate_p_given_unresolved:
                outcome_label = "escalated"
            else:
                outcome_label = "abandoned"

            handle_time = max(60.0, float(rng.normal(handle_time_base, 60)))
            csat = None
            if outcome_label == "resolved":
                csat = float(np.clip(rng.normal(4.3 if agent_version == "v2" else 3.9, 0.6), 1, 5))

            external_session_id = f"support-{user_idx:04d}-{s}"
            started_at = session_start + timedelta(minutes=int(user_idx * 7 + s * 3))
            ended_at = started_at + timedelta(seconds=handle_time)

            messages = [
                {
                    "external_message_id": f"{external_session_id}-m0",
                    "turn_index": 0,
                    "sender": "user",
                    "text": USER_OPENERS[category],
                    "created_at": started_at.isoformat(),
                },
                {
                    "external_message_id": f"{external_session_id}-m1",
                    "turn_index": 1,
                    "sender": "agent",
                    "text": str(rng.choice(AGENT_OPENERS)),
                    "created_at": (started_at + timedelta(seconds=5)).isoformat(),
                },
            ]
            actions = [
                {
                    "external_action_id": f"{external_session_id}-a0",
                    "sequence_index": 0,
                    "action_type": "triage_ticket",
                    "started_at": started_at.isoformat(),
                    "latency_ms": int(rng.integers(200, 1200)),
                    "tool_calls": [
                        {
                            "external_tool_call_id": f"{external_session_id}-tc0",
                            "tool_name": "lookup_account",
                            "success": bool(rng.random() < 0.95),
                            "latency_ms": int(rng.integers(100, 600)),
                        }
                    ],
                },
                {
                    "external_action_id": f"{external_session_id}-a1",
                    "sequence_index": 1,
                    "action_type": "respond",
                    "started_at": (started_at + timedelta(seconds=6)).isoformat(),
                    "latency_ms": int(rng.integers(200, 900)),
                    "tool_calls": [],
                },
            ]

            outcome_metrics = []
            if csat is not None:
                outcome_metrics.append({"name": "csat_score", "value": round(csat, 2)})

            sessions.append(
                {
                    "external_session_id": external_session_id,
                    "external_experiment_id": experiment_id,
                    "agent_version": agent_version,
                    "external_user_id": f"support-user-{user_idx:04d}",
                    "started_at": started_at.isoformat(),
                    "ended_at": ended_at.isoformat(),
                    "messages": messages,
                    "actions": actions,
                    "outcome": {"label": outcome_label, "metrics": outcome_metrics},
                    "metrics": [{"name": "handle_time_seconds", "value": round(handle_time, 1)}],
                    "context": {"ticket_category": category},
                }
            )

    return {"domain": "support", "experiments": experiments, "sessions": sessions}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=str, default="data/fixtures/support_sessions.json")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--n-users", type=int, default=150)
    args = parser.parse_args()

    fixture = build_fixture(args.seed, args.n_users)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(fixture, indent=2), encoding="utf-8")
    print(f"wrote {len(fixture['sessions'])} sessions ({args.n_users} users) to {out_path}")


if __name__ == "__main__":
    main()
