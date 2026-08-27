"""Shared data types used across sources, scoring, db, cli and gui."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

# Pipeline stages, in the order they normally progress through.
STAGES = ["New", "Contacted", "Replied", "Qualified", "Won", "Lost"]


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class LeadCandidate:
    """A raw hit returned by a lead source, before it is scored and stored."""

    source: str
    source_detail: str  # permalink / unique id from the source, used for dedup
    company: str = ""
    contact_name: str = ""
    title: str = ""
    email: str = ""
    phone: str = ""
    url: str = ""
    keyword_matched: str = ""
    raw_text: str = ""
    discovered_at: str = field(default_factory=utcnow_iso)


@dataclass
class Lead:
    """A stored lead, as persisted in the database."""

    id: int
    dedup_key: str
    company: str
    contact_name: str
    title: str
    email: str
    phone: str
    url: str
    source: str
    source_detail: str
    keyword_matched: str
    raw_text: str
    score: int
    stage: str
    notes: str
    next_follow_up: Optional[str]
    created_at: str
    updated_at: str
    last_seen_at: str
