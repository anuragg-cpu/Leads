"""Command-line interface.

Examples:
    abhayleads fetch                       run every enabled source
    abhayleads fetch --source reddit       run just one source
    abhayleads list --stage New            list new leads, best score first
    abhayleads list --due                  leads due for follow-up
    abhayleads show 42                     full detail for lead 42
    abhayleads update 42 --stage Contacted --notes "sent intro email" --follow-up 2026-09-03
    abhayleads stats                       pipeline summary
    abhayleads dedupe                      merge osm_places leads mapped twice
    abhayleads reset                       delete ALL leads and start over
    abhayleads gui                         open the CRM window

    abhayleads profile list                list your product/company profiles
    abhayleads profile create "OtherCo"    new profile, own config.yaml + leads.db
    abhayleads profile use "OtherCo"       switch the active profile
    abhayleads --profile "OtherCo" fetch   run one command against another profile
"""

import argparse
import sys
from pathlib import Path
from typing import Optional

from .config import default_paths, load_config
from .db import Database
from .fetcher import run_fetch
from .models import STAGES
from .profiles import (
    DEFAULT_PROFILE_NAME,
    create_profile,
    delete_profile,
    get_active_profile,
    list_profiles,
    profile_paths,
    set_active_profile,
)


def _resolve_paths(args) -> tuple[Optional[Path], Path, Optional[str]]:
    """Returns (config_path, db_path, active_profile_name_or_None).

    Explicit --db/--config always win (for testing/advanced use) and
    report profile_name=None. Otherwise resolves --profile, or the
    persisted active profile - auto-creating a "default" profile the
    very first time there isn't one yet, so this always has somewhere
    to point.
    """
    if getattr(args, "db", None) or getattr(args, "config", None):
        _, app_data_dir = default_paths()
        db_path = Path(args.db) if args.db else app_data_dir / "leads.db"
        config_path = Path(args.config) if args.config else None
        return config_path, db_path, None

    profile_name = getattr(args, "profile", None) or get_active_profile()
    if not profile_name:
        config_path, db_path = create_profile(DEFAULT_PROFILE_NAME)
        profile_name = DEFAULT_PROFILE_NAME
    else:
        config_path, db_path = profile_paths(profile_name)

    return config_path, db_path, profile_name


def _get_db(args) -> Database:
    _, db_path, _ = _resolve_paths(args)
    return Database(db_path)


def _get_config(args):
    config_path, _, _ = _resolve_paths(args)
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
            company=args.company,
            contact_name=args.contact_name,
            email=args.email,
            phone=args.phone,
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


def cmd_reset(args):
    db = _get_db(args)
    if not args.yes:
        answer = input("This permanently deletes ALL leads in this profile. Type 'yes' to confirm: ")
        if answer.strip().lower() != "yes":
            print("Cancelled - nothing was deleted.")
            db.close()
            return
    count = db.delete_all_leads()
    print(f"Deleted {count} lead(s). config.yaml is untouched - run `abhayleads fetch` to start over.")
    db.close()


def cmd_profile_list(args):
    profiles = list_profiles()
    active = get_active_profile()
    if not profiles:
        print('No profiles yet. Create one with: abhayleads profile create "Name"')
        return
    for name in profiles:
        marker = "*" if name == active else " "
        print(f"{marker} {name}")


def cmd_profile_create(args):
    try:
        config_path, _ = create_profile(args.name)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    print(f"Created profile {args.name!r}.")
    print(f"  Config: {config_path}")
    print(f'  Edit its keywords, then run: abhayleads --profile "{args.name}" fetch')


def cmd_profile_use(args):
    try:
        set_active_profile(args.name)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    print(f"Active profile is now {args.name!r}.")


def cmd_profile_delete(args):
    try:
        delete_profile(args.name, delete_files=args.delete_files)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    if args.delete_files:
        print(f"Deleted profile {args.name!r} and its files.")
    else:
        print(f"Removed profile {args.name!r} from the list (its files were kept on disk).")


def cmd_gui(args):
    from .gui.app import launch

    config_path, db_path, profile_name = _resolve_paths(args)
    launch(db_path, config_path, profile_name)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="abhayleads", description="Abhay Leads - local lead-gen CRM")
    parser.add_argument("--db", help="Path to the SQLite database (overrides profile selection)")
    parser.add_argument("--config", help="Path to config.yaml (overrides profile selection)")
    parser.add_argument("--profile", help="Which profile to use for this command (default: the active profile)")
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

    p_update = sub.add_parser("update", help="Update a lead's stage/notes/follow-up/contact info")
    p_update.add_argument("lead_id", type=int)
    p_update.add_argument("--stage", choices=STAGES)
    p_update.add_argument("--notes")
    p_update.add_argument("--follow-up", help="ISO date, e.g. 2026-09-03")
    p_update.add_argument("--clear-follow-up", action="store_true")
    p_update.add_argument("--company")
    p_update.add_argument("--contact-name")
    p_update.add_argument("--email")
    p_update.add_argument("--phone")
    p_update.set_defaults(func=cmd_update)

    p_stats = sub.add_parser("stats", help="Pipeline summary and last fetch run")
    p_stats.set_defaults(func=cmd_stats)

    p_dedupe = sub.add_parser(
        "dedupe", help="Merge osm_places leads with an identical name in the same locality"
    )
    p_dedupe.set_defaults(func=cmd_dedupe)

    p_reset = sub.add_parser("reset", help="Delete ALL leads in the current profile to start over")
    p_reset.add_argument("--yes", action="store_true", help="Skip the confirmation prompt")
    p_reset.set_defaults(func=cmd_reset)

    p_gui = sub.add_parser("gui", help="Open the CRM window")
    p_gui.set_defaults(func=cmd_gui)

    p_profile = sub.add_parser(
        "profile", help="Manage product/company profiles - each has its own config.yaml and leads.db"
    )
    p_profile.set_defaults(func=cmd_profile_list)
    profile_sub = p_profile.add_subparsers(dest="profile_command")

    p_profile_list = profile_sub.add_parser("list", help="List profiles")
    p_profile_list.set_defaults(func=cmd_profile_list)

    p_profile_create = profile_sub.add_parser("create", help="Create a new profile")
    p_profile_create.add_argument("name")
    p_profile_create.set_defaults(func=cmd_profile_create)

    p_profile_use = profile_sub.add_parser("use", help="Switch the active profile")
    p_profile_use.add_argument("name")
    p_profile_use.set_defaults(func=cmd_profile_use)

    p_profile_delete = profile_sub.add_parser("delete", help="Remove a profile")
    p_profile_delete.add_argument("name")
    p_profile_delete.add_argument(
        "--delete-files", action="store_true", help="Also permanently delete its config.yaml and leads.db"
    )
    p_profile_delete.set_defaults(func=cmd_profile_delete)

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
