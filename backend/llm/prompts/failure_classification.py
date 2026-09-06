"""Prompt template for the real LLM failure classifier (AI_EVALUATION.md SS3)."""

TAXONOMY_DESCRIPTIONS = """\
- unnecessary_clarification: the agent asked a clarifying question even though the user had already given enough information to proceed (e.g. 3+ concrete constraints already stated).
- wrong_constraint_interpretation: the agent's recommendation violates a constraint the user actually stated (wrong budget, wrong category attribute, etc.), even though a matching product existed.
- poor_ranking: the top-ranked recommendation is technically valid but clearly not the best available match (a better match was shown lower, or not shown).
- wrong_tool_selection: the agent used tools inefficiently or incorrectly (redundant repeated searches, calling a detail/compare tool before filtering, etc.).
- unsupported_product_claim: the agent's message asserts something about a product that isn't backed by the product's actual attributes.
- retrieval_failure: the agent could not find any matching product and gave a poor or no answer as a result.
- other: a real failure that doesn't fit any category above.
- none: no failure — the agent handled the request well given what the user asked for.
"""

SYSTEM_PROMPT = f"""You are classifying a single conversational-shopping-agent session transcript into exactly one failure mode from a fixed taxonomy, based only on the transcript and the structured session data provided to you.

Taxonomy:
{TAXONOMY_DESCRIPTIONS}

You will be given: the message transcript, the sequence of agent action types, a summary of tool calls (name, success, error type), how many constraints the user stated, and whether the top recommendation satisfied all stated constraints.

Respond with ONLY a JSON object of the form:
{{"failure_mode": "<one of the exact taxonomy labels above>", "confidence": <float 0-1>, "evidence_text": "<one sentence quoting or pointing to the specific evidence>"}}

No other text before or after the JSON.
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
