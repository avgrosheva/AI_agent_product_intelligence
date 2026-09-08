"""The commerce domain: the conversational-shopping-agent demo this
project ships today. Everything shopping-specific that used to be
scattered as hardcoded constants inside backend/investigation/ and
backend/analytics/ now lives here as explicit, named data — the six
failure mechanisms, the three guardrails, the segment dimensions/values,
and the metric-name-to-column bindings. backend/llm/context_builder.py
remains the actual storage adapter (Postgres commerce schema ->
SessionContext); this package is the domain's registered configuration.
"""
