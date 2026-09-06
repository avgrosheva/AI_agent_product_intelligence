"""Run failure classification over the loaded dataset and populate
failure_labels. Default client is the deterministic RuleBasedMockClient —
no API key required. Pass --client anthropic for the real LLM path
(requires ANTHROPIC_API_KEY and `pip install -e ".[llm]"`).

Usage: python -m scripts.run_classification [--client mock|anthropic]
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
    parser.add_argument("--client", choices=["mock", "anthropic"], default="mock")
    args = parser.parse_args()

    if args.client == "mock":
        client = RuleBasedMockClient()
    else:
        from backend.llm.anthropic_client import AnthropicLLMClient

        client = AnthropicLLMClient()

    engine = create_engine(get_database_url())
    t0 = time.time()
    n = classify_all_sessions(engine, client)
    elapsed = time.time() - t0
    print(f"Classified {n} sessions with {args.client} client in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
