"""Builds one session's full row set: sessions, messages, agent_actions,
tool_calls, recommendations, product_events, evaluations, plus a
ground-truth row (validation artifact only — never written to the app DB).

Orchestrates the effects in datagen/effects.py in a fixed order so a run
is fully reproducible given the shared rng. See DATA_MODEL.md SS6 for the
effect specifications this implements.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np

from datagen.assignment import assign_agent_version
from datagen.constants import (
    BASELINE_TEMPLATE_WEIGHTS,
    DEVICE_TIER_WEIGHTS,
    DEVICE_TIERS,
    PLATFORM_WEIGHTS,
    PLATFORMS,
    PRICE_IN_PER_1K_TOKENS,
    PRICE_OUT_PER_1K_TOKENS,
    REQUEST_CATEGORY_WEIGHTS,
    USE_CASE_TAGS,
    constraint_bucket,
)
from datagen.constraints import CatalogStats, build_constraints, count_satisfied, product_satisfies
from datagen.effects import (
    apply_exploratory_template_shift,
    apply_overclarify_effect,
    apply_tool_selection_effect,
    extra_search_latency_ms,
    latency_abandon_probability,
    resolve_violation_rate,
)
from datagen.ids import child_id, entity_id
from datagen.messages_text import (
    render_clarify_question,
    render_clarify_response,
    render_opener,
    render_recommend_intro,
)
from datagen.rng import bernoulli, weighted_choice


@dataclass
class SessionRows:
    session: dict
    messages: list = field(default_factory=list)
    agent_actions: list = field(default_factory=list)
    tool_calls: list = field(default_factory=list)
    recommendations: list = field(default_factory=list)
    product_events: list = field(default_factory=list)
    evaluations: list = field(default_factory=list)
    ground_truth: dict = field(default_factory=dict)


def _normalize(weights: dict) -> dict:
    total = sum(weights.values())
    return {k: v / total for k, v in weights.items()}


def _token_count(text: str) -> int:
    return max(4, int(len(text.split()) * 1.3))


def _action_reasoning_tokens(rng: np.random.Generator) -> int:
    return max(20, int(rng.normal(70, 15)))


def _tool_result_tokens(rng: np.random.Generator) -> int:
    return max(30, int(rng.normal(120, 30)))


def build_session(
    rng: np.random.Generator,
    profile_name: str,
    seed: int,
    session_index: int,
    user: dict,
    experiment: dict,
    products_by_category: dict[str, list[dict]],
    stats: CatalogStats,
    session_start: datetime,
) -> SessionRows:
    session_id = entity_id(profile_name, seed, "session", session_index)
    agent_version = assign_agent_version(user["user_id"], experiment["experiment_id"])
    model_name = "agent-v1-model" if agent_version == "v1" else "agent-v2-model"

    # --- pre-treatment attributes: decided before agent_version has any influence ---
    requested_category = weighted_choice(
        rng, list(REQUEST_CATEGORY_WEIGHTS.keys()), list(REQUEST_CATEGORY_WEIGHTS.values())
    )
    num_constraints_target = int(
        weighted_choice(rng, [0, 1, 2, 3, 4, 5], [0.15, 0.25, 0.25, 0.20, 0.10, 0.05])
    )
    constraints = build_constraints(rng, requested_category, num_constraints_target, user["persona"], stats)
    num_constraints = len(constraints)
    bucket = constraint_bucket(num_constraints)

    if bernoulli(rng, 0.15):
        other_platforms = [p for p in PLATFORMS if p != user["platform_pref"]]
        platform = weighted_choice(rng, other_platforms, [1.0] * len(other_platforms))
    else:
        platform = user["platform_pref"]
    device_tier = weighted_choice(rng, DEVICE_TIERS, DEVICE_TIER_WEIGHTS)
    locale = user["locale"]

    # --- trajectory template selection (post-treatment: agent_version allowed here) ---
    weights = dict(BASELINE_TEMPLATE_WEIGHTS[bucket])
    weights = apply_overclarify_effect(weights, agent_version, bucket)
    weights = apply_tool_selection_effect(weights, agent_version)
    weights = apply_exploratory_template_shift(weights, agent_version, bucket)
    weights = _normalize(weights)
    template = str(weighted_choice(rng, list(weights.keys()), list(weights.values())))

    rows = SessionRows(session=None)  # type: ignore[arg-type]
    seq = 0
    turn = 0
    cur_time = session_start
    total_tokens_in = 0
    total_tokens_out = 0

    def add_action(action_type: str, latency_ms: int) -> dict:
        nonlocal seq, cur_time, total_tokens_out
        action = {
            "action_id": child_id(profile_name, seed, "action", session_index, seq),
            "session_id": session_id,
            "sequence_index": seq,
            "action_type": action_type,
            "started_at": cur_time,
            "latency_ms": latency_ms,
            "model_name": model_name,
            "agent_version": agent_version,
        }
        rows.agent_actions.append(action)
        total_tokens_out += _action_reasoning_tokens(rng)
        cur_time = cur_time + timedelta(milliseconds=latency_ms)
        seq += 1
        return action

    def add_tool_call(action: dict, tool_name: str, latency_ms: int, success: bool, error_type: str) -> None:
        nonlocal total_tokens_in
        rows.tool_calls.append(
            {
                "tool_call_id": child_id(profile_name, seed, "toolcall", session_index, len(rows.tool_calls)),
                "action_id": action["action_id"],
                "session_id": session_id,
                "tool_name": tool_name,
                "input_json": {"category": requested_category, "constraints": constraints},
                "output_json": {"result_count": int(rng.integers(0, 12))},
                "success": success,
                "error_type": error_type,
                "latency_ms": latency_ms,
            }
        )
        total_tokens_in += _tool_result_tokens(rng)

    def add_message(sender: str, text: str, latency_ms: int | None) -> None:
        nonlocal total_tokens_in, total_tokens_out
        tokens = _token_count(text)
        rows.messages.append(
            {
                "message_id": child_id(profile_name, seed, "message", session_index, len(rows.messages)),
                "session_id": session_id,
                "turn_index": turn,
                "sender": sender,
                "text": text,
                "created_at": cur_time,
                "tokens": tokens,
                "latency_ms": latency_ms,
            }
        )
        if sender == "user":
            total_tokens_in += tokens
        else:
            total_tokens_out += tokens

    # turn 0: user opener
    add_message("user", render_opener(rng, requested_category, constraints), None)

    a0 = add_action("understand_query", max(60, int(rng.lognormal(5.1, 0.3))))

    def do_search() -> None:
        base_latency = max(150, int(rng.lognormal(6.3, 0.35)))
        extra = extra_search_latency_ms(rng, platform, agent_version)
        latency = int(base_latency + extra)
        action = add_action("search", latency)
        error_type = "empty_result" if bernoulli(rng, 0.08) else "none"
        add_tool_call(action, "search_products", latency, success=(error_type == "none"), error_type=error_type)

    def do_filter() -> None:
        latency = max(80, int(rng.lognormal(5.7, 0.3)))
        action = add_action("filter", latency)
        add_tool_call(action, "filter_products", latency, success=True, error_type="none")

    def do_clarify() -> None:
        nonlocal turn
        latency = max(80, int(rng.lognormal(5.5, 0.25)))
        action = add_action("clarify", latency)
        add_message("agent", render_clarify_question(rng), latency)

    def do_extra_recommend_tool() -> None:
        if bernoulli(rng, 0.12):
            latency = max(60, int(rng.lognormal(5.2, 0.3)))
            action = add_action("answer", latency)
            add_tool_call(action, "get_product_details", latency, success=True, error_type="none")

    ends_abandoned_by_template = template in ("dead_end_abandon", "clarify_then_abandon")
    reaches_recommend_candidate = not ends_abandoned_by_template

    if template == "simple_success":
        do_search()
    elif template == "filtered_success":
        do_search()
        do_filter()
    elif template == "clarified_success":
        do_search()
        do_clarify()
        turn += 1
        add_message(
            "user",
            render_clarify_response(
                rng,
                constraints.get("budget", stats.price_percentile(requested_category, 60)),
                constraints.get("use_case", str(weighted_choice(rng, USE_CASE_TAGS, [1.0] * len(USE_CASE_TAGS)))),
            ),
            None,
        )
        do_search()
    elif template == "redundant_search_success":
        do_search()
        do_search()
        if bernoulli(rng, 0.5):
            do_filter()
    elif template == "dead_end_abandon":
        do_search()
        do_search()
        do_search()
    elif template == "clarify_then_abandon":
        do_search()
        do_clarify()

    # --- effect 3: latency-driven abandonment can override a would-be success ---
    latency_flip = False
    if reaches_recommend_candidate:
        latency_so_far = sum(a["latency_ms"] for a in rows.agent_actions)
        abandon_p = latency_abandon_probability(latency_so_far)
        if bernoulli(rng, abandon_p):
            latency_flip = True

    ends_abandoned = ends_abandoned_by_template or latency_flip

    recommendation_rows: list[dict] = []
    top_satisfies = None
    violation_fired = False
    retrieval_failure = False

    if not ends_abandoned:
        do_extra_recommend_tool()
        category_products = products_by_category[requested_category]
        matching = [p for p in category_products if product_satisfies(p, constraints)]

        if matching:
            ranked_matches = sorted(matching, key=lambda p: -p["rating"])
            violation_rate = resolve_violation_rate(requested_category, num_constraints, agent_version)
            if num_constraints > 0 and bernoulli(rng, violation_rate):
                matching_ids = {p["product_id"] for p in matching}
                non_matching = [p for p in category_products if p["product_id"] not in matching_ids]
                if non_matching:
                    ranked_partial = sorted(
                        non_matching, key=lambda p: (-count_satisfied(p, constraints), -p["rating"])
                    )
                    top_pick = ranked_partial[0]
                    violation_fired = True
                    shown_pool = [top_pick] + ranked_matches[:4]
                else:
                    top_pick = ranked_matches[0]
                    shown_pool = ranked_matches[:5]
            else:
                top_pick = ranked_matches[0]
                shown_pool = ranked_matches[:5]
        else:
            retrieval_failure = True
            ranked_all = sorted(
                category_products, key=lambda p: (-count_satisfied(p, constraints), -p["rating"])
            )
            top_pick = ranked_all[0]
            shown_pool = ranked_all[:5]

        shown = shown_pool[:5] if len(shown_pool) >= 3 else shown_pool
        if not shown:
            shown = [top_pick]

        latency = max(60, int(rng.lognormal(5.3, 0.25)))
        add_action("recommend", latency)
        add_message("agent", render_recommend_intro(rng, has_full_match=bool(matching) and not violation_fired), latency)

        for rank, product in enumerate(shown, start=1):
            satisfies = product_satisfies(product, constraints)
            if rank == 1:
                top_satisfies = satisfies
            recommendation_rows.append(
                {
                    "rec_id": child_id(profile_name, seed, "rec", session_index, rank),
                    "session_id": session_id,
                    "turn_index": turn,
                    "product_id": product["product_id"],
                    "rank_position": rank,
                    "shown_at": cur_time,
                    "clicked": False,
                    "clicked_at": None,
                    "satisfies_constraints": satisfies,
                }
            )
    else:
        add_action("abandon_flow", max(20, int(rng.lognormal(4.0, 0.3))))

    rows.recommendations = recommendation_rows

    # --- funnel simulation (only the top-ranked recommendation is engaged with) ---
    outcome = "abandoned" if ends_abandoned else "no_action"
    if recommendation_rows:
        top_rec = recommendation_rows[0]
        top_product = next(p for p in products_by_category[requested_category] if p["product_id"] == top_rec["product_id"])
        rows.product_events.append(
            _product_event(profile_name, seed, session_index, len(rows.product_events), session_id, user["user_id"], top_rec["product_id"], "impression", cur_time, top_product["price_rub"])
        )
        for rec in recommendation_rows[1:]:
            prod = next(p for p in products_by_category[requested_category] if p["product_id"] == rec["product_id"])
            rows.product_events.append(
                _product_event(profile_name, seed, session_index, len(rows.product_events), session_id, user["user_id"], rec["product_id"], "impression", cur_time, prod["price_rub"])
            )

        satisfies = top_rec["satisfies_constraints"]
        click_p = 0.35 + (0.15 if satisfies else -0.10) + (top_product["rating"] - 4.0) * 0.08
        if bernoulli(rng, click_p):
            top_rec["clicked"] = True
            top_rec["clicked_at"] = cur_time + timedelta(seconds=int(rng.integers(3, 40)))
            rows.product_events.append(
                _product_event(profile_name, seed, session_index, len(rows.product_events), session_id, user["user_id"], top_rec["product_id"], "click", top_rec["clicked_at"], top_product["price_rub"])
            )
            cart_p = 0.50 + (0.20 if satisfies else -0.20)
            if user["persona"] == "budget" and "budget" in constraints:
                cart_p -= 0.05
            if bernoulli(rng, cart_p):
                cart_time = top_rec["clicked_at"] + timedelta(seconds=int(rng.integers(5, 60)))
                rows.product_events.append(
                    _product_event(profile_name, seed, session_index, len(rows.product_events), session_id, user["user_id"], top_rec["product_id"], "add_to_cart", cart_time, top_product["price_rub"])
                )
                purchase_p = 0.55 + (0.15 if satisfies else -0.15)
                if bernoulli(rng, purchase_p):
                    purchase_time = cart_time + timedelta(seconds=int(rng.integers(10, 120)))
                    rows.product_events.append(
                        _product_event(profile_name, seed, session_index, len(rows.product_events), session_id, user["user_id"], top_rec["product_id"], "purchase", purchase_time, top_product["price_rub"])
                    )
                    outcome = "purchase"
                else:
                    outcome = "add_to_cart_only"
            else:
                outcome = "no_action"
        else:
            outcome = "no_action"

    # --- evaluations: only when a recommendation was actually produced ---
    if recommendation_rows and top_satisfies is not None:
        frac_satisfied = count_satisfied(
            next(p for p in products_by_category[requested_category] if p["product_id"] == recommendation_rows[0]["product_id"]),
            constraints,
        ) / len(constraints) if constraints else 1.0
        rows.evaluations.append(
            _evaluation(profile_name, seed, session_index, session_id, "constraint_satisfaction", frac_satisfied, cur_time)
        )
        rows.evaluations.append(
            _evaluation(profile_name, seed, session_index, session_id, "offline_task_success", 1.0 if top_satisfies else 0.0, cur_time)
        )

    # --- ground truth tagging (validation artifact only; priority order matters) ---
    scenario = "baseline"
    failure_mode = "none"
    if template in ("clarified_success", "clarify_then_abandon") and bucket == "3+":
        # Behavioral tag, not gated on agent_version: v1 also clarifies here at its
        # (lower) baseline rate, and a real classifier would label the behavior
        # regardless of which version produced it. The *effect* is the v1-vs-v2
        # RATE difference in this segment, discovered by aggregation downstream —
        # gating the label itself on version would create an artificial 0%-vs-X%
        # cliff for v1, which the approved docs explicitly warn against.
        scenario = "overclarify_v2"
        failure_mode = "unnecessary_clarification"
    elif requested_category == "monitor":
        scenario = "monitor_constraint_regression_v2"
        failure_mode = "wrong_constraint_interpretation" if violation_fired else "none"
    elif bucket == "0-1":
        scenario = "exploratory_uplift"
        failure_mode = "wrong_constraint_interpretation" if violation_fired else "none"
    elif template == "redundant_search_success":
        scenario = "tool_selection_v2_improved"
        failure_mode = "wrong_tool_selection"
    elif latency_flip:
        scenario = "android_latency"
        failure_mode = "none"
    elif retrieval_failure:
        scenario = "baseline"
        failure_mode = "retrieval_failure"
    else:
        noise = weighted_choice(rng, ["poor_ranking", "unsupported_product_claim", "none"], [0.03, 0.02, 0.95])
        failure_mode = str(noise)

    num_turns = turn + 1
    total_latency_ms = sum(a["latency_ms"] for a in rows.agent_actions)
    cost = (total_tokens_in / 1000.0) * PRICE_IN_PER_1K_TOKENS + (total_tokens_out / 1000.0) * PRICE_OUT_PER_1K_TOKENS

    # The funnel simulation above can append click/add_to_cart/purchase
    # product_events with timestamps after the agent's last action (cur_time) —
    # the user keeps interacting with the page after the agent stops talking.
    # ended_at must cover those too, or downstream event-in-bounds checks fail.
    event_times = [pe["event_time"] for pe in rows.product_events]
    session_ended_at = max([cur_time, *event_times]) if event_times else cur_time

    rows.session = {
        "session_id": session_id,
        "user_id": user["user_id"],
        "experiment_id": experiment["experiment_id"],
        "agent_version": agent_version,
        "started_at": session_start,
        "ended_at": session_ended_at,
        "platform": platform,
        "device_tier": device_tier,
        "locale": locale,
        "initial_query_text": rows.messages[0]["text"],
        "constraints_json": constraints,
        "requested_category": requested_category,
        "num_constraints": num_constraints,
        "outcome": outcome,
        "num_turns": num_turns,
        "total_latency_ms": total_latency_ms,
        "total_tokens_in": total_tokens_in,
        "total_tokens_out": total_tokens_out,
        "total_cost_usd": round(cost, 6),
    }
    rows.ground_truth = {
        "session_id": session_id,
        "ground_truth_scenario": scenario,
        "ground_truth_failure_mode": failure_mode,
    }
    return rows


def _product_event(profile_name, seed, session_index, event_index, session_id, user_id, product_id, event_type, event_time, price) -> dict:
    return {
        "event_id": child_id(profile_name, seed, "event", session_index, event_index),
        "session_id": session_id,
        "user_id": user_id,
        "product_id": product_id,
        "event_type": event_type,
        "event_time": event_time,
        "price_at_event": price,
    }


def _evaluation(profile_name, seed, session_index, session_id, eval_type, score, created_at) -> dict:
    idx = 0 if eval_type == "constraint_satisfaction" else 1
    return {
        "eval_id": child_id(profile_name, seed, "eval", session_index, idx),
        "session_id": session_id,
        "eval_type": eval_type,
        "score": round(score, 4),
        "evaluator": "rule_based",
        "rationale_text": None,
        "created_at": created_at,
    }
