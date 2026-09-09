"""Scheduled/on-demand release monitoring (Stage 11 tasks 1-2). A
monitoring job is just "run backend.release.service.evaluate_and_persist_
release for one (project, domain, experiment, primary_metric) on a
cadence, and record what happened" — no new evaluation or decision
logic of its own. See backend.monitoring.service for job execution and
backend.monitoring.scheduler for the background polling loop."""
