"""Single source of truth for the application database URL.

Reads DATABASE_URL from the environment; falls back to the local dev
Postgres container (see README / docs/ROADMAP.md Stage 1) so the common
case (running everything on one machine during development) needs no
extra setup.
"""

import os

DEFAULT_DATABASE_URL = "postgresql+psycopg://app:app_password@localhost:5434/ai_agent_pi"


def get_database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
