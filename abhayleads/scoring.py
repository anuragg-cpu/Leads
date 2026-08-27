"""Keyword-based lead scoring.

This is intentionally simple: it's a starting point you should tune once
real results come in, not a machine-learning model. See docs/MARKETING_BASICS.md
for how to think about scoring/ICP fit in general.
"""

import re
from typing import Any

from .models import LeadCandidate


def _find_matches(text: str, keywords: list[str]) -> list[str]:
    text_lower = text.lower()
    return [kw for kw in keywords if kw.lower() in text_lower]


def is_excluded(candidate: LeadCandidate, config: dict[str, Any]) -> bool:
    exclude_keywords = config.get("product", {}).get("exclude_keywords", []) or []
    if not exclude_keywords:
        return False
    text = f"{candidate.title}\n{candidate.raw_text}".lower()
    return any(kw.lower() in text for kw in exclude_keywords)


def score_candidate(candidate: LeadCandidate, config: dict[str, Any]) -> tuple[int, str]:
    """Returns (score 0-100, comma-separated matched keywords)."""
    keywords = config.get("product", {}).get("keywords", []) or []
    if not keywords:
        return 0, ""

    scoring_cfg = config.get("scoring", {})
    per_keyword = scoring_cfg.get("points_per_keyword", 20)
    title_bonus = scoring_cfg.get("title_match_bonus", 15)
    source_weight = scoring_cfg.get("source_weights", {}).get(candidate.source, 1.0)

    title_matches = set(_find_matches(candidate.title, keywords))
    body_matches = set(_find_matches(candidate.raw_text, keywords))
    all_matches = title_matches | body_matches

    if not all_matches:
        return 0, ""

    raw_score = len(all_matches) * per_keyword + len(title_matches) * title_bonus
    weighted = raw_score * source_weight
    score = max(0, min(100, round(weighted)))
    return score, ", ".join(sorted(all_matches))
