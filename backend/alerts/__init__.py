"""Stage 6: deterministic alert generation from persisted release
evaluations (backend.release). Domain-agnostic: never imports
backend.domains.commerce or backend.domains.support — every alert is
derived purely from a ReleaseEvaluationResult's already-computed fields,
supplied by the caller (backend.release.service)."""
