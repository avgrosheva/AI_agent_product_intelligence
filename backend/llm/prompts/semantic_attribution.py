"""Prompt template for the semantic multi-label attribution call (hybrid
attribution redesign, AI_EVALUATION.md SS3 addendum). Supersedes
failure_classification.py's exclusive-classifier prompt for the three
mechanisms that genuinely require interpreting conversation context;
retrieval_failure/poor_ranking/wrong_tool_selection are deterministic
now (backend/llm/deterministic_detectors.py) and never sent to the model.

PROMPT_VERSION must be bumped whenever SYSTEM_PROMPT's wording changes in a
way that could shift model behavior — recorded in provenance so a reported
metric can always be tied back to the exact prompt text that produced it.
"""

PROMPT_VERSION = "semantic_attribution_v1"

MECHANISM_DESCRIPTIONS = """\
1. unnecessary_clarification: detected when the agent asks the user for information that was already sufficiently provided, or asks a clarifying question that does not materially resolve any real ambiguity given what the user had already stated. Use the full conversation context — do not infer this from a constraint count alone.

2. wrong_constraint_interpretation: detected when the user stated an explicit requirement (budget, category, size, compatibility, a required attribute, etc.), a product satisfying that requirement existed among the shown candidates, and the agent's recommendation or reasoning conflicts with the stated requirement anyway. Do NOT use this when no shown candidate ever satisfied the constraint (that is a retrieval problem, handled elsewhere) and do NOT use this for ranking quality among fully compliant candidates (also handled elsewhere).

3. unsupported_product_claim: detected when the assistant's message asserts a specific factual property about the recommended product (a compatibility, a feature/use case, a specification or value) that conflicts with or is unsupported by the product attributes given below. Do not skip this just because the session's overall outcome was otherwise fine — an unsupported claim is a failure on its own, independent of outcome.
"""

SYSTEM_PROMPT = f"""You are evaluating a single conversational-shopping-agent session for three INDEPENDENT semantic judgments, based only on the transcript and structured session data provided to you. Each judgment is a separate yes/no decision. Any combination may be true — including all three false, or more than one true. Never force exactly one to be true.

{MECHANISM_DESCRIPTIONS}

You will be given: the message transcript, the sequence of agent action types, a summary of tool calls (name, success, error type), how many constraints the user stated, whether the top recommendation satisfied all stated constraints, and the observable attributes of every shown/recommended product (including whether each one satisfies the stated constraints).

Respond with ONLY a single JSON object of exactly this shape, and nothing else:
{{"unnecessary_clarification": {{"detected": <bool>, "confidence": <float 0.0-1.0>, "evidence_text": "<one concise sentence grounded in observable data>"}}, "wrong_constraint_interpretation": {{"detected": <bool>, "confidence": <float 0.0-1.0>, "evidence_text": "<one concise sentence>"}}, "unsupported_product_claim": {{"detected": <bool>, "confidence": <float 0.0-1.0>, "evidence_text": "<one concise sentence>"}}}}

Hard output rules:
- No chain-of-thought, no reasoning, no analysis — decide silently and output only the final JSON object.
- No markdown formatting, no code fences, no headings.
- No text before or after the JSON object.
- No top-level keys other than the three named mechanisms; no fields inside each mechanism other than detected, confidence, and evidence_text.
"""


def _format_product(p) -> str:
    tags = ", ".join(p.use_case_tags) if p.use_case_tags else "(none)"
    specs = []
    if p.ram_gb is not None:
        specs.append(f"{p.ram_gb}GB RAM")
    if p.storage_gb is not None:
        specs.append(f"{p.storage_gb}GB storage")
    if p.weight_kg is not None:
        specs.append(f"{p.weight_kg}kg")
    if p.cpu_tier is not None:
        specs.append(f"cpu={p.cpu_tier}")
    if p.gpu_tier is not None:
        specs.append(f"gpu={p.gpu_tier}")
    if p.screen_in is not None:
        specs.append(f'{p.screen_in}" screen')
    specs_text = ", ".join(specs) if specs else "(no additional specs)"
    return (
        f"- rank {p.rank_position}: {p.brand} {p.category}, {p.price_rub} RUB, rating {p.rating}, "
        f"in_stock={p.in_stock}, use_case_tags=[{tags}], {specs_text}, "
        f"satisfies_stated_constraints={p.satisfies_constraints}"
    )


def render_user_message(context) -> str:
    transcript_lines = [f"{sender}: {text}" for sender, text in context.transcript]
    tool_lines = [
        f"- {tc.tool_name} (success={tc.success}, error_type={tc.error_type}, result_count={tc.result_count})"
        for tc in context.tool_calls
    ]
    product_lines = [_format_product(p) for p in context.recommended_products]
    return (
        f"Transcript:\n" + "\n".join(transcript_lines) + "\n\n"
        f"Agent action sequence: {' -> '.join(context.action_sequence)}\n\n"
        f"Tool calls:\n" + ("\n".join(tool_lines) if tool_lines else "(none)") + "\n\n"
        f"Constraints stated: {context.num_constraints}\n"
        f"Requested category: {context.requested_category}\n"
        f"Top recommendation satisfied all constraints: {context.top_recommendation_satisfies_constraints}\n"
        f"Any shown recommendation satisfied all constraints: {context.any_shown_recommendation_satisfies_constraints}\n"
        f"Shown/recommended products:\n" + ("\n".join(product_lines) if product_lines else "(none shown)") + "\n\n"
        f"Session outcome: {context.outcome}\n"
    )
