"""Minimum practical-effect and correction thresholds for the Investigation
engine (STATISTICS.md SS5-SS6, INVESTIGATION.md SS1-SS3). Named constants,
not hard-coded inline, per STATISTICS.md SS5.
"""

MIN_ABSOLUTE_EFFECT_RATE = 0.02   # 2pp minimum practical effect for rate metrics
MIN_COHENS_D = 0.2                # minimum practical effect for continuous metrics (Cohen's d or rank-biserial)
BH_Q = 0.10                       # Benjamini-Hochberg FDR level for the segment scan (STATISTICS.md SS6)
TOP_K_FINDINGS = 5                # INVESTIGATION.md SS3 step 5
MIN_EXCESS_ABANDONMENT_COUNT = 5  # INVESTIGATION.md SS4: minimum |E(segment)| before reporting a failure-mode share
MIN_PATTERN_SESSIONS_FOR_TEST = 5 # trajectory pattern must have >=5 sessions to be tested (INVESTIGATION.md SS5)
RARE_SEQUENCE_MIN_COUNT = 5       # exact trajectory sequences below this count are canonicalized (INVESTIGATION.md SS5)

# METRICS.md SS5 guardrail thresholds
GUARDRAIL_LATENCY_P95_RATIO = 1.15
GUARDRAIL_TOOL_ERROR_ABS_INCREASE = 0.02
GUARDRAIL_COST_RATIO = 1.20
