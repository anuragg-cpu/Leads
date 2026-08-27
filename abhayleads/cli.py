"""Command-line interface.

Examples:
    abhayleads fetch                       run every enabled source
    abhayleads fetch --source reddit       run just one source
    abhayleads list --stage New            list new leads, best score first
    abhayleads list --due                  leads due for follow-up
    abhayleads show 42                     full detail for lead 42
    abhayleads update 42 --stage Contacted --notes "sent intro email" --follow-up 2026-09-03
    abhayleads stats                       pipeline summary
    abhayleads gui                         open the CRM window
"""

import argparse
import sys
from pathlib import Path

from .config import default_paths, load_config
from .db import Database
from .fetcher import run_fetch
from .models import STAGES


def _get_db(args) -> Database:
    _, app_data_dir = default_paths()
    db_path = Path(args.db) if getattr(args, "db", None) else app_data_dir / "leads.db"
    return Database(db_path)


def _get_config(args):
    config_path = Path(args.config) if getattr(args, "config", None) else None
    return load_config(config_path)


def cmd_fetch(args):
    db = _get_db(args)
    config = _get_config(args)
    result = run_fetch(db, config, only_sources=[args.source] if args.source else None, progress=print)

    print(f"\nSources run: {', '.join(result.sources_run) or '(none enabled)'}")
    print(f"New leads:     {result.new_leads}")
    print(f"Updated leads: {result.updated_leads}")
    if result.errors:
        print(f"Errors ({len(result.errors)}):")
        for err in result.errors:
            print(f"  - {err}")
    db.close()


def cmd_list(args):
    db = _get_db(args)
    leads = db.list_leads(
        stage=args.stage,
        source=args.source,
        min_score=args.min_score,
        due_only=args.due,
        search=args.search,
    )
    if not leads:
        print("No leads match that filter.")
        db.close()
        return

    print(f"{'ID':<5} {'Score':<6} {'Stage':<11} {'Company/Source':<28} {'Title'}")
    print("-" * 100)
    for lead in leads:
        company = lead["company"] or f"({lead['source']})"
        title = (lead["title"] or "")[:60]
        print(f"{lead['id']:<5} {lead['score']:<6} {lead['stage']:<11} {company[:28]:<28} {title}")
    print(f"\n{len(leads)} lead(s).")
    db.close()


def cmd_show(args):
    db = _get_db(args)
    lead = db.get_lead(args.lead_id)
    if lead is None:
        print(f"No lead with id {args.lead_id}", file=sys.stderr)
        db.close()
        sys.exit(1)

    for key in lead.keys():
        print(f"{key:>16}: {lead[key]}")

    print("\nStage history:")
    for row in db.stage_history(args.lead_id):
        print(f"  {row['changed_at']}  ->  {row['stage']}")
    db.close()


def cmd_update(args):
    db = _get_db(args)
    try:
        db.update_lead(
            args.lead_id,
            stage=args.stage,
            notes=args.notes,
            next_follow_up=args.follow_up,
            clear_follow_up=args.clear_follow_up,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        db.close()
        sys.exit(1)
    print(f"Updated lead {args.lead_id}.")
    db.close()


def cmd_stats(args):
    db = _get_db(args)
    stats = db.stats()
    last_run = db.last_fetch_run()

    print(f"Total leads: {stats['total']}")
    print(f"Due for follow-up: {stats['due_for_follow_up']}")
    print("\nBy stage:")
    for stage, count in stats["by_stage"].items():
        print(f"  {stage:<11} {count}")
    print("\nBy source:")
    for source, count in stats["by_source"].items():
        print(f"  {source:<14} {count}")

    if last_run:
        print(f"\nLast fetch run: {last_run['started_at']}")
        print(f"  New: {last_run['new_leads']}  Updated: {last_run['updated_leads']}")
    else:
        print("\nNo fetch runs yet - try `abhayleads fetch`.")
    db.close()


def cmd_dedupe(args):
    db = _get_db(args)
    summaries = db.merge_exact_duplicate_osm_leads()
    if not summaries:
        print("No exact-duplicate osm_places leads found.")
    else:
        total_removed = sum(len(s["removed_ids"]) for s in summaries)
        print(f"Merged {len(summaries)} duplicate group(s), removed {total_removed} duplicate lead(s):")
        for s in summaries:
            print(f"  {s['company']} ({s['locality']}): kept #{s['kept_id']}, removed {s['removed_ids']}")
    db.close()


def cmd_gui(args):
    from .gui.app import launch

    _, app_data_dir = default_paths()
    db_path = Path(args.db) if getattr(args, "db", None) else app_data_dir / "leads.db"
    config_path = Path(args.config) if getattr(args, "config", None) else None
    launch(db_path, config_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="abhayleads", description="Abhay Leads - local lead-gen CRM")
    parser.add_argument("--db", help="Path to the SQLite database (default: ~/AbhayLeads/leads.db)")
    parser.add_argument("--config", help="Path to config.yaml (default: ~/AbhayLeads/config/config.yaml)")
    sub = parser.add_subparsers(dest="command")

    p_fetch = sub.add_parser("fetch", help="Run lead sources and store new/updated leads")
    p_fetch.add_argument("--source", help="Only run this one source (e.g. reddit)")
    p_fetch.set_defaults(func=cmd_fetch)

    p_list = sub.add_parser("list", help="List stored leads")
    p_list.add_argument("--stage", choices=STAGES)
    p_list.add_argument("--source")
    p_list.add_argument("--min-score", type=int, default=0)
    p_list.add_argument("--due", action="store_true", help="Only leads due for follow-up")
    p_list.add_argument("--search", help="Substring search across company/name/title/text")
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="Show full detail for one lead")
    p_show.add_argument("lead_id", type=int)
    p_show.set_defaults(func=cmd_show)

    p_update = sub.add_parser("update", help="Update a lead's stage/notes/follow-up")
    p_update.add_argument("lead_id", type=int)
    p_update.add_argument("--stage", choices=STAGES)
    p_update.add_argument("--notes")
    p_update.add_argument("--follow-up", help="ISO date, e.g. 2026-09-03")
    p_update.add_argument("--clear-follow-up", action="store_true")
    p_update.set_defaults(func=cmd_update)

    p_stats = sub.add_parser("stats", help="Pipeline summary and last fetch run")
    p_stats.set_defaults(func=cmd_stats)

    p_dedupe = sub.add_parser(
        "dedupe", help="Merge osm_places leads with an identical name in the same locality"
    )
    p_dedupe.set_defaults(func=cmd_dedupe)

    p_gui = sub.add_parser("gui", help="Open the CRM window")
    p_gui.set_defaults(func=cmd_gui)

    return parser


def main(argv: list[str] | None = None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if not getattr(args, "command", None):
        # No subcommand: behave like double-clicking the .exe - open the GUI.
        cmd_gui(args)
        return

    args.func(args)


if __name__ == "__main__":
    main()
