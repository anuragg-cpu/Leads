"""Orchestrates a fetch run: calls each enabled source, scores results,
and upserts them into the database. Shared by the CLI and the GUI so
they can't drift apart.
"""

from dataclasses import dataclass
from typing import Any, Callable, Optional

from .db import Database
from .scoring import is_excluded, score_candidate
from .sources import get_enabled_sources


@dataclass
class FetchResult:
    run_id: int
    new_leads: int
    updated_leads: int
    dropped_no_keywords: int
    errors: list[str]
    sources_run: list[str]
    stopped: bool = False


def run_fetch(
    db: Database,
    config: dict[str, Any],
    only_sources: Optional[list[str]] = None,
    progress: Optional[Callable[[str], None]] = None,
    on_lead_saved: Optional[Callable[[], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
) -> FetchResult:
    """Runs every enabled (or explicitly selected) source once.

    `progress`, if given, is called with short human-readable status
    strings - useful for a GUI to show "Searching hackernews..." etc.

    `on_lead_saved`, if given, is called right after each individual
    candidate is scored and written to the database - a source finding
    hundreds of leads over several minutes (osm_places, walking many
    localities) no longer means waiting for all of them before anything
    shows up; each one lands in the db the moment it's found.

    `should_stop`, if given, is polled after every candidate (and before
    starting each source) - returning True ends the run early. Whatever
    was already saved stays saved; this only stops looking for more.
    Cooperative, not instant: a source blocked on one in-flight network
    request finishes that single request before the next check.
    """
    keywords = config.get("product", {}).get("keywords", []) or []
    sources = get_enabled_sources(config, only=only_sources)
    run_id = db.start_fetch_run([s.name for s in sources])

    new_count = 0
    updated_count = 0
    errors: list[str] = []
    stopped = False

    if not keywords:
        errors.append(
            "No keywords configured in product.keywords - every candidate would "
            "score 0. Add keywords to config.yaml before fetching."
        )

    for source in sources:
        if should_stop and should_stop():
            stopped = True
            break

        if progress:
            progress(f"Searching {source.name}...")
            source.progress_callback = progress

        for candidate in source.safe_fetch(keywords):
            if is_excluded(candidate, config):
                continue
            score, matched = score_candidate(candidate, config)
            candidate.keyword_matched = matched
            _, is_new = db.upsert_candidate(candidate, score)
            if is_new:
                new_count += 1
            else:
                updated_count += 1
            if on_lead_saved:
                on_lead_saved()
            if should_stop and should_stop():
                stopped = True
                break

        errors.extend(source.warnings)
        if stopped:
            break

    db.finish_fetch_run(run_id, new_count, updated_count, errors)
    if progress:
        status = "Stopped" if stopped else "Done"
        progress(f"{status}: {new_count} new, {updated_count} updated, {len(errors)} error(s).")

    return FetchResult(
        run_id=run_id,
        new_leads=new_count,
        updated_leads=updated_count,
        dropped_no_keywords=0,
        errors=errors,
        sources_run=[s.name for s in sources],
        stopped=stopped,
    )
