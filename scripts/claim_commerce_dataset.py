"""Stage 8 task 3/4: assign the (single, shared) commerce demo dataset to
one project. Run this once per environment after creating the project
that should see commerce data — an unclaimed or wrongly-claimed project
sees zero commerce experiments/sessions, by design (never another
project's data, and never a silent full-dataset leak).

Usage: python -m scripts.claim_commerce_dataset --project-id <uuid>
"""

from __future__ import annotations

import argparse

from sqlalchemy import create_engine

from backend.app.db import get_database_url
from backend.domains.commerce.ownership import claim_commerce_dataset, get_commerce_dataset_owner


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True, help="The project_id (UUID) that should own the commerce demo dataset.")
    args = parser.parse_args()

    engine = create_engine(get_database_url())
    previous_owner = get_commerce_dataset_owner(engine)
    n = claim_commerce_dataset(engine, args.project_id)
    print(f"Assigned {n} commerce experiment(s) to project '{args.project_id}'.")
    if previous_owner and previous_owner != args.project_id:
        print(f"(previously owned by project '{previous_owner}')")


if __name__ == "__main__":
    main()
