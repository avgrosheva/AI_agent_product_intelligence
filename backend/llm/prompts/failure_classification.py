"""LEGACY — prompt for the OLD exclusive 8-class classifier
(OpenRouterLLMClient.classify_failure / RuleBasedMockClient.classify_failure),
superseded by the hybrid multi-label attribution redesign. The current
prompt is backend/llm/prompts/semantic_attribution.py, used by
classify_semantic. Kept only so historical failure_labels rows and old
tests stay meaningful; nothing in the current pipeline sends this prompt.

PROMPT_VERSION must be bumped whenever SYSTEM_PROMPT's wording changes in a
way that could shift model behavior — it is recorded in evaluation
provenance so a reported metric can always be tied back to the exact
prompt text that produced it.
"""

PROMPT_VERSION = "failure_classification_v3"

TAXONOMY_DESCRIPTIONS = """\
- unnecessary_clarification: the agent asked a clarifying question even though the user had already given enough information to proceed (e.g. 3+ concrete constraints already stated).
- wrong_constraint_interpretation: the user stated an explicit constraint (budget, category, size, compatibility, a required attribute, etc.), a product satisfying that constraint existed / was available in the observable evidence, and the agent's recommendation violates the stated constraint anyway. The defining facts are: an explicit constraint, a compliant candidate that existed, and a recommendation that violates it regardless. This takes priority over poor_ranking whenever an explicit constraint is violated.
- poor_ranking: use only when the recommendation is still valid with respect to every explicit constraint the user stated, and the problem is purely ranking/order/quality among valid candidates — a clearly better valid candidate existed but was ranked lower or not shown. Never use poor_ranking when the top recommendation violates an explicit user constraint; that is wrong_constraint_interpretation instead.
- wrong_tool_selection: the agent's tool/action choice itself was inefficient or incorrect (redundant repeated searches, calling a detail/compare tool before filtering, searching again with no new information, etc.), classified independently of whether the final product happened to be good or bad.
- unsupported_product_claim: the agent's message explicitly claims a product property (a compatibility, a feature, a specification/value) that is not supported by the product's actual attributes or the tool evidence available in the session context. This includes claiming compatibility not present in the source data, claiming a feature the product evidence does not show, or stating a specification inconsistent with observable product data. Do not collapse this into `none` merely because the session's overall outcome (e.g. a purchase) was otherwise acceptable — an unsupported claim is a failure on its own even when the rest of the session went fine.
- retrieval_failure: the search/retrieval process failed to surface a matching product at all — the problem is the absence of a retrieval result, not the interpretation of an already-available matching product, and the agent's tool usage was otherwise reasonable given that absence.
- other: a real failure that doesn't fit any category above.
- none: no failure — the agent handled the request well given what the user asked for, made no unsupported claims, and violated no explicit constraint.
"""

DECISION_ORDER = """\
Apply these checks in order and stop at the first one that fires — this resolves every case where more than one category could plausibly apply:
1. Did the agent make an unsupported factual product claim? -> unsupported_product_claim
2. Did the final/top recommendation violate an explicit user constraint while a compliant candidate existed? -> wrong_constraint_interpretation
3. Did retrieval fail to produce a suitable candidate? -> retrieval_failure
4. Did the agent use the wrong tool/action pattern? -> wrong_tool_selection
5. Were all explicit constraints satisfied, but recommendation ordering was materially poor? -> poor_ranking
6. Did the agent ask for clarification despite already having enough information? -> unnecessary_clarification
7. Other genuine failure not covered above? -> other
8. Otherwise -> none
"""

SYSTEM_PROMPT = f"""You are classifying a single conversational-shopping-agent session transcript into exactly one failure mode from a fixed taxonomy, based only on the transcript and the structured session data provided to you.

Taxonomy:
{TAXONOMY_DESCRIPTIONS}

Decision order:
{DECISION_ORDER}

You will be given: the message transcript, the sequence of agent action types, a summary of tool calls (name, success, error type), how many constraints the user stated, and whether the top recommendation satisfied all stated constraints.

Respond with ONLY a single JSON object of exactly this shape, and nothing else:
{{"failure_mode": "<one of the exact taxonomy labels above>", "confidence": <float 0.0-1.0>, "evidence_text": "<one concise sentence grounded in observable session data — no internal reasoning, only what is visible in the transcript/trace>"}}

Hard output rules:
- No chain-of-thought, no reasoning, no analysis — decide silently and output only the final JSON object.
- No markdown formatting, no code fences, no headings.
- No text before or after the JSON object — the entire response must be parseable as that one JSON object.
- No fields other than failure_mode, confidence, and evidence_text.
"""


def render_user_message(context) -> str:
    transcript_lines = [f"{sender}: {text}" for sender, text in context.transcript]
    tool_lines = [
        f"- {tc.tool_name} (success={tc.success}, error_type={tc.error_type}, result_count={tc.result_count})"
        for tc in context.tool_calls
    ]
    return (
        f"Transcript:\n" + "\n".join(transcript_lines) + "\n\n"
        f"Agent action sequence: {' -> '.join(context.action_sequence)}\n\n"
        f"Tool calls:\n" + ("\n".join(tool_lines) if tool_lines else "(none)") + "\n\n"
        f"Constraints stated: {context.num_constraints}\n"
        f"Requested category: {context.requested_category}\n"
        f"Top recommendation satisfied all constraints: {context.top_recommendation_satisfies_constraints}\n"
        f"Any shown recommendation satisfied all constraints: {context.any_shown_recommendation_satisfies_constraints}\n"
        f"Session outcome: {context.outcome}\n"
    )
