# LLM Failure Classification & AI Evaluation

## 1. Role boundary (restated from PRD, load-bearing for this doc)

The LLM classifies and summarizes. It never computes a metric, a statistical test, or a financial value. Every number displayed anywhere in the product traces to `METRICS.md`-defined SQL/Python, never to LLM output. This document covers the one place an LLM genuinely runs at analysis time: **failure-mode classification and evidence extraction**, plus lightweight narrative generation that only interpolates already-computed numbers.

## 2. Failure taxonomy

`unnecessary_clarification`, `wrong_constraint_interpretation`, `poor_ranking`, `wrong_tool_selection`, `unsupported_product_claim`, `retrieval_failure`, `other`, `none` (no failure). Fixed, closed set — the classifier is constrained to output exactly one of these per session (multi-label is deferred; sessions with multiple issues are labeled by their most consequential failure, decided by the classifier's own confidence-ranked output, and this simplification is stated in the UI methodology note).

## 3. Classification pipeline

**Input** per session: the message transcript, the `agent_actions`/`tool_calls` sequence (action types, tool names, success/error flags — not raw JSON payloads, to keep prompts small), and the `recommendations.satisfies_constraints` flags. There is no `sessions.ground_truth_scenario` column and no `source='ground_truth'` row for the classifier to be given by mistake — ground truth is physically absent from the application database it reads from (`DATA_MODEL.md` §8), not merely filtered out of the prompt by convention. The classifier only ever sees the same observable data a human reviewer would see, and there is no code path by which it could see anything else.

**Prompting**: a single structured-output call per session (or batched, several sessions per call, for cost efficiency on the demo dataset) using a fixed instruction: taxonomy definitions with one example each, the session transcript, and a request for `{failure_mode, confidence (0-1), evidence_quote}` as strict JSON validated against a Pydantic schema. Malformed output is retried once, then falls back to `other` with confidence 0 and a logged parse failure — the pipeline never blocks on a bad LLM response.

**Provider abstraction**: `backend/llm/client.py` defines a minimal protocol:

```python
class LLMClient(Protocol):
    def classify_failure(self, session_context: SessionContext) -> FailureClassification: ...
    def summarize_finding(self, finding: Finding) -> str: ...
```

Two implementations: `AnthropicLLMClient` (real calls, used for the demo build and interviews) and `RuleBasedMockClient` (deterministic keyword/heuristic classifier used in unit tests and CI, and as a zero-API-key fallback for anyone running the repo locally). Both are wired through the same interface and a config flag (`LLM_PROVIDER=anthropic|mock`) selects one — this is what satisfies "not tied to one vendor" without building a multi-vendor plugin system.

**Cost control**: classification runs once per session at dataset-build/refresh time and is cached in `failure_labels` (`source='llm_classifier'`), not on every page load. The Investigation and AI Quality screens read the cached table.

## 4. Why classification is a real task, not a lookup

Because ground truth exists only in `validation_ground_truth.parquet` (`DATA_MODEL.md` §8) and never in the Postgres database the classifier and the app both read from, and because message text is generated with lexical/phrasing variation (synonyms, persona-driven tone, varying levels of explicitness — `DATA_MODEL.md` §3.5), the classifier has to infer the failure mode from conversational evidence the way a human reviewer would, rather than reading a hidden flag. This is what makes the precision/recall evaluation in §5 meaningful — and because the separation is physical (a different file, read by a different process), it holds even if a future contributor forgets the "don't use this column" convention, since there is no such column to forget about.

## 5. Evaluating the classifier itself

`validation_ground_truth.parquet` carries a generator-assigned ground-truth failure mode per session (`DATA_MODEL.md` §8), so the classifier's quality is measured directly. `scripts/evaluate_classifier.py` reads this parquet file and the app's `failure_labels` table (classifier predictions only) in its own process — the same access pattern as `tests/validate_ground_truth.py` — and joins them on `session_id` to build:

- **Confusion matrix** of `ground_truth failure_mode` vs. `llm_classifier failure_mode`, computed once per dataset build.
- **Per-class precision/recall/F1**, with particular attention to the classes that matter most to the Investigation story (`unnecessary_clarification`, `wrong_constraint_interpretation`) — the acceptance bar for the MVP is recall ≥ 0.7 and precision ≥ 0.6 on those two classes specifically (looser classes like `other`/`poor_ranking` are allowed lower bars since they're inherently fuzzier).
- **Calibration spot-check**: mean confidence on correct vs. incorrect classifications should be meaningfully separated (correct > incorrect); this is reported, not gated, since strict calibration testing is out of scope for two weeks.
- This evaluation report is generated by `scripts/evaluate_classifier.py` and its output (a small markdown/JSON report) is committed as evidence in the repo, analogous to a model card — this is the project's answer to "how do you know your AI evaluation step is trustworthy," which a reviewer will ask.

## 6. Automated evaluation vs. offline task success (relationship to `evaluations` table)

`evaluations.eval_type = offline_task_success` and `constraint_satisfaction` are **not** LLM outputs — they are computed deterministically by checking `recommendations` against `sessions.constraints_json` attribute-by-attribute (e.g., is `price_rub ≤ budget`, is `ram_gb ≥ requested`, is `weight_kg ≤ requested`). This is intentional: the metric that most directly claims "the agent did its job" must be the most auditable one in the system, with no model in the loop. `answer_faithfulness` is the one evaluation type where an LLM judgment is appropriate (checking whether the agent's natural-language claims about a product are supported by that product's actual attributes is a semantic-matching task unsuitable for a rule engine) — this is clearly labeled `evaluator='llm'` in the table and is the only evaluation score in the system with that provenance.

## 7. Narrative generation guardrail

`summarize_finding()` is given a `Finding` object that already contains every number to be mentioned (segment name, deltas, CIs, EC score, dominant failure mode and its share of excess abandonment, dominant trajectory pattern) and is prompted to produce *prose that references these exact figures*, not to compute or estimate new ones. Output is post-validated by regex-extracting any numbers in the LLM's prose and checking they appear in the input `Finding` object; a mismatch is logged and the UI falls back to a template-only sentence (no LLM prose) for that finding. This is the concrete mechanism enforcing "LLM must not be responsible for calculating product metrics" at the narrative layer, where the risk of silent number invention is highest.
