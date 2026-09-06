"""Lightweight templated message text with lexical variation.

Not intended to be a sophisticated NLG system — Stage 1 has no classifier
consuming this text yet (AI_EVALUATION.md's classifier is Stage 3). Kept
varied enough that the schema and downstream stages have real text to
work with, using the shared rng for deterministic selection.
"""

from __future__ import annotations

import numpy as np

from datagen.rng import weighted_choice

_CONSTRAINT_PHRASES = {
    "budget": lambda v: f"under {v:,} RUB".replace(",", " "),
    "ram_min": lambda v: f"at least {v}GB of RAM",
    "weight_max": lambda v: f"under {v}kg",
    "screen_size_min": lambda v: f"at least {v}\" screen",
    "use_case": lambda v: f"good for {v.replace('_', ' ')}",
    "brand": lambda v: f"from {v}",
}

_CATEGORY_NOUN = {"laptop": "laptop", "monitor": "monitor", "accessory": "accessory"}

_OPENERS = [
    "Hi, I'm looking for a {noun} {constraints}.",
    "Can you help me find a {noun} {constraints}?",
    "I need a {noun} {constraints}.",
    "Looking for a good {noun} {constraints}, any suggestions?",
    "Hey, searching for a {noun} {constraints}.",
]

_OPENERS_NO_CONSTRAINTS = [
    "Hi, I'm looking for a {noun}, not sure exactly what I need yet.",
    "Can you help me pick a {noun}?",
    "I need a {noun} but I'm open to suggestions.",
    "What {noun} would you recommend?",
]

_CLARIFY_QUESTIONS = [
    "Could you tell me a bit more about what you'll use it for and your budget?",
    "What's your budget, and any must-have specs?",
    "A couple of quick questions first: budget range, and preferred brand if any?",
    "To narrow it down, what will you mainly use it for?",
]

_CLARIFY_RESPONSES = [
    "Sure, my budget is around {budget} RUB, mainly for {use_case}.",
    "I'd say up to {budget} RUB, and I need it for {use_case}.",
    "Around {budget} RUB, {use_case} is the main use.",
]

_RECOMMEND_INTROS = [
    "Here are a few options that match what you're looking for:",
    "Based on what you told me, these should work well:",
    "I found some good matches for you:",
    "Here's what I'd recommend:",
]

_NO_MATCH_INTROS = [
    "I couldn't find a perfect match, but here's the closest option:",
    "Nothing fits every requirement exactly, but this one comes close:",
]


def render_opener(rng: np.random.Generator, category: str, constraints: dict) -> str:
    noun = _CATEGORY_NOUN[category]
    if not constraints:
        template = weighted_choice(rng, _OPENERS_NO_CONSTRAINTS, [1.0] * len(_OPENERS_NO_CONSTRAINTS))
        return template.format(noun=noun)
    parts = [_CONSTRAINT_PHRASES[k](v) for k, v in constraints.items()]
    constraints_text = ", ".join(parts)
    template = weighted_choice(rng, _OPENERS, [1.0] * len(_OPENERS))
    return template.format(noun=noun, constraints=constraints_text)


def render_clarify_question(rng: np.random.Generator) -> str:
    return str(weighted_choice(rng, _CLARIFY_QUESTIONS, [1.0] * len(_CLARIFY_QUESTIONS)))


def render_clarify_response(rng: np.random.Generator, budget: int, use_case: str) -> str:
    template = weighted_choice(rng, _CLARIFY_RESPONSES, [1.0] * len(_CLARIFY_RESPONSES))
    return template.format(budget=f"{budget:,}".replace(",", " "), use_case=use_case.replace("_", " "))


def render_recommend_intro(rng: np.random.Generator, has_full_match: bool) -> str:
    pool = _RECOMMEND_INTROS if has_full_match else _NO_MATCH_INTROS
    return str(weighted_choice(rng, pool, [1.0] * len(pool)))
