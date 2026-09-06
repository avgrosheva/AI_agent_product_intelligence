"""Stage 5 SS12: manual check that the Stage 4 API works unchanged against
whatever dataset is currently loaded (run this while demo data is loaded).

Usage: start the API (`python -m uvicorn backend.app.main:app --port 8123`)
against the demo-loaded database, then run this script.
"""

from __future__ import annotations

import sys
import time

import httpx

BASE = "http://127.0.0.1:8123"


def check(method: str, path: str, expected_status: int = 200, **kwargs) -> dict:
    t0 = time.time()
    resp = httpx.request(method, f"{BASE}{path}", timeout=30, **kwargs)
    elapsed = time.time() - t0
    status = "OK" if resp.status_code == expected_status else "FAIL"
    print(f"[{status}] {method} {path} -> {resp.status_code} ({elapsed:.3f}s)")
    if resp.status_code != expected_status:
        print(f"       body: {resp.text[:300]}")
        sys.exit(1)
    return resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}


def main() -> None:
    experiments = check("GET", "/experiments")
    eid = experiments["experiments"][0]["experiment_id"]
    print(f"experiment_id = {eid}")

    check("GET", f"/experiments/{eid}")
    metrics = check("GET", f"/experiments/{eid}/metrics")
    print(f"  {len(metrics['metrics'])} metrics returned")
    check("GET", f"/experiments/{eid}/funnel")
    check("GET", f"/experiments/{eid}/guardrails")

    for lens in ["abandonment", "conversion", "constraint_satisfaction"]:
        inv = check("GET", f"/experiments/{eid}/investigation", params={"lens": lens})
        print(f"  lens={lens}: {len(inv['findings'])} findings, recommendation={inv['recommendation']['verdict']}")

    ai_quality = check("GET", f"/experiments/{eid}/ai-quality")
    print(f"  {len(ai_quality['failure_mode_distribution'])} failure modes")

    sessions = check("GET", "/sessions", params={"limit": 10})
    print(f"  total sessions: {sessions['total']}")
    sid = sessions["items"][0]["session_id"]
    check("GET", f"/sessions/{sid}")

    check("GET", "/ai-quality/classifier-evaluation")

    # reproduce a finding's segment via the sessions filter
    abandonment_inv = check("GET", f"/experiments/{eid}/investigation", params={"lens": "abandonment"})
    if abandonment_inv["findings"]:
        dims = abandonment_inv["findings"][0]["segment_filter"]["dimensions"]
        reproduced = check("GET", "/sessions", params={**dims, "limit": 1})
        print(f"  segment_filter {dims} reproduces {reproduced['total']} sessions")

    check("GET", "/experiments/00000000-0000-0000-0000-000000000000", expected_status=404)
    check("GET", f"/experiments/{eid}/investigation", expected_status=422)  # missing lens

    print("\nAll demo-scale API checks passed.")


if __name__ == "__main__":
    main()
