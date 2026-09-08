"""Run the current hybrid multi-label attribution pipeline over the loaded
dataset and populate session_failure_attributions (deterministic detectors
+ one semantic LLM call per session — see AI_EVALUATION.md SS2-3). Default
client is the deterministic RuleBasedMockClient — no API key required.
Pass --client openrouter for the real LLM path (requires OPENROUTER_API_KEY
and `pip install -e ".[llm]"`; model is configurable via OPENROUTER_MODEL,
see backend/llm/openrouter_client.py).

Usage: python -m scripts.run_classification [--client mock|openrouter]
"""

from __future__ import annotations

import argparse
import time

from sqlalchemy import create_engine

from backend.app.db import get_database_url
from backend.llm.classification_pipeline import classify_all_sessions
from backend.llm.mock_client import RuleBasedMockClient


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--client", choices=["mock", "openrouter"], default="mock")
    args = parser.parse_args()

    if args.client == "mock":
        client = RuleBasedMockClient()
    else:
        from backend.llm.openrouter_client import OpenRouterLLMClient

        client = OpenRouterLLMClient()

    engine = create_engine(get_database_url())
    t0 = time.time()
    n = classify_all_sessions(engine, client)
    elapsed = time.time() - t0
    print(f"Classified {n} sessions with {args.client} client in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
