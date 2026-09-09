"""Stage 7 tasks 5-6: basic, deterministic economics — cost per session,
cost per successful session, incremental cost, and (only where a value/
revenue column is actually available) an estimated business-impact
delta. Domain-agnostic: works off whatever columns a domain's own
EconomicsConfig names in its analytics_base_df(), never assumes any
particular domain's schema, and never invents a number a domain didn't
provide data for — that field is null instead.
"""
