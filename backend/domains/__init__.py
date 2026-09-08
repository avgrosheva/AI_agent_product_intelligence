"""Domain packages. Each subpackage supplies the domain-specific data and
adapters a real agent product needs on top of backend/core/'s generic
types — mechanisms, guardrails, segment dimensions, metric value-column
bindings, and (for commerce) the product/recommendation storage adapter.
backend/domains/commerce/ is the one that backs this project's shopping
demo; a second, non-shopping domain would add a sibling package here
without needing to change backend/core/.
"""
