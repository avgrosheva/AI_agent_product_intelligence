"""Langfuse connection configuration (Stage 9 task 4: "use environment
variables/secrets safely"). LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY
always come from this process's own environment — never from a request
body, a CLI argument, or any other value that could end up echoed into a
log line, an error response, or a database row. `host` is not a secret
(a self-hosted Langfuse URL) and may be overridden per call.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_HOST = "https://cloud.langfuse.com"


class LangfuseConfigError(Exception):
    pass


@dataclass(frozen=True)
class LangfuseConnectionConfig:
    public_key: str
    secret_key: str
    host: str = DEFAULT_HOST

    @classmethod
    def from_env(cls, *, host_override: str | None = None) -> "LangfuseConnectionConfig":
        public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
        secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
        if not public_key or not secret_key:
            raise LangfuseConfigError(
                "LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY must both be set in this server's "
                "environment. The Langfuse connector never accepts API keys through a request body "
                "or CLI argument, so a key can never be echoed into a request log or an error response."
            )
        host = host_override or os.environ.get("LANGFUSE_HOST", DEFAULT_HOST)
        return cls(public_key=public_key, secret_key=secret_key, host=host)

    def __repr__(self) -> str:
        # The secret key is the one value that must never appear in a log
        # line, a traceback, or an accidental print(config) — the public
        # key is, per Langfuse's own naming, safe to display.
        return f"LangfuseConnectionConfig(public_key={self.public_key!r}, secret_key='***redacted***', host={self.host!r})"

    __str__ = __repr__
