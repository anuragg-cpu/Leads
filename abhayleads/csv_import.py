"""Bulk-add leads from a CSV file - for lead types no automated source can
find (e.g. a hand-curated list of CCTV dealers/system integrators - see
docs/SOURCES.md's `security_dealer` section for why that one has to be
manual), or a export from another CRM/spreadsheet. Shared by the CLI
(`abhayleads import-csv`) and the GUI (File -> Import CSV...), and works
against either a local Database or a RemoteDatabase - same read/write
surface either way, see db_factory.py.

Column names are matched flexibly (case-insensitive, several aliases per
field - see _COLUMN_ALIASES) rather than requiring one exact header row,
since a real export (e.g. from another CRM) rarely uses this app's own
field names verbatim.
"""

import csv
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import STAGES, LeadCandidate

# canonical field -> accepted header names (lowercased). First match in a
# row's header wins if a file somehow has more than one alias for the
# same field.
_COLUMN_ALIASES: dict[str, list[str]] = {
    "external_id": ["external_id", "lead id", "lead_id", "id"],
    "company": ["company", "company name", "org/society name", "organization", "org name", "society name", "business name"],
    "contact_name": ["contact_name", "contact person", "contact", "name"],
    "category": ["title", "segment", "category", "role", "designation"],
    "email": ["email", "email address"],
    "phone": ["phone", "phone number", "mobile", "contact number"],
    "url": ["url", "website"],
    "address": ["address", "area/zone", "area", "zone"],
    "city": ["city"],
    "score": ["score", "lead score"],
    "stage": ["stage", "status"],
    "next_follow_up": ["next_follow_up", "next follow-up", "next follow up", "followup", "follow up", "follow-up"],
    "last_contact": ["last_contact", "last contact"],
    "notes": ["notes", "note", "remarks"],
    "owner": ["owner"],
    "original_source": ["source"],
}

_HEADER_TO_FIELD = {alias: canonical for canonical, aliases in _COLUMN_ALIASES.items() for alias in aliases}

# A handful of real-world typos seen in actual CRM exports - extend as
# more turn up rather than failing the whole row over one misspelling.
_STAGE_TYPO_FIXES = {"conatcted": "contacted"}

_DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"]


@dataclass
class ImportResult:
    imported: int = 0
    skipped_lines: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def skipped(self) -> int:
        return len(self.skipped_lines)


def _normalize_stage(raw: str) -> tuple[Optional[str], Optional[str]]:
    """Returns (stage_or_None, warning_or_None). None stage means "leave
    it as the New a fresh insert already defaults to"."""
    if not raw:
        return None, None
    key = raw.strip().lower()
    key = _STAGE_TYPO_FIXES.get(key, key)
    for stage in STAGES:
        if stage.lower() == key:
            return stage, None
    return None, f"unknown status/stage {raw!r} - left as New"


def _parse_date(raw: str) -> tuple[Optional[str], Optional[str]]:
    """Returns (iso_date_or_None, warning_or_None)."""
    if not raw:
        return None, None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw.strip(), fmt).strftime("%Y-%m-%d"), None
        except ValueError:
            continue
    return None, f"unrecognized date {raw!r} - skipped"


def import_csv(db, path: Path, dry_run: bool = False) -> ImportResult:
    """Reads `path` and upserts one lead per valid row.

    A row needs at least a company or a contact name to be kept - others
    are counted in `skipped_lines` (1-indexed file line numbers, header
    included, matching what a user sees opening the file in a text
    editor/Excel).

    When the file has an id column (aliases: external_id/lead id/id),
    that value becomes part of the lead's dedup key - re-importing the
    same file (or a later export of the same source CRM with the same
    ids) updates the existing leads instead of duplicating them, the
    same way re-running an automated fetch does. Without an id column,
    every row is a distinct new lead (like `abhayleads add`).

    `dry_run=True` runs every validation but writes nothing - use it to
    preview a file before committing it, since (unlike a fetch) a bad
    import can't be told apart from real data afterward to undo it.
    """
    result = ImportResult()

    # utf-8-sig: Excel's default "CSV UTF-8" export prepends a BOM, which
    # would otherwise land inside the first header name (e.g. "﻿company")
    # and silently fail to match any alias below.
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            result.warnings.append("File has no header row - nothing imported.")
            return result

        for line_number, row in enumerate(reader, start=2):  # 1 is the header
            fields: dict[str, str] = {}
            for header, value in row.items():
                canonical = _HEADER_TO_FIELD.get((header or "").strip().lower())
                if canonical and canonical not in fields:
                    fields[canonical] = (value or "").strip()

            company = fields.get("company", "")
            contact_name = fields.get("contact_name", "")
            if not company and not contact_name:
                result.skipped_lines.append(line_number)
                continue

            score = 0
            score_raw = fields.get("score", "")
            if score_raw:
                try:
                    score = int(float(score_raw))
                except ValueError:
                    result.warnings.append(f"line {line_number}: invalid score {score_raw!r} - using 0")

            stage, stage_warning = _normalize_stage(fields.get("stage", ""))
            if stage_warning:
                result.warnings.append(f"line {line_number}: {stage_warning}")

            next_follow_up, date_warning = _parse_date(fields.get("next_follow_up", ""))
            if date_warning:
                result.warnings.append(f"line {line_number}: next follow-up {date_warning}")

            result.imported += 1
            if dry_run:
                continue

            external_id = fields.get("external_id", "")
            source_detail = f"csv_import:{external_id}" if external_id else f"csv_import-{uuid.uuid4().hex}"

            address_parts = [fields.get("address", ""), fields.get("city", "")]
            address = ", ".join(p for p in address_parts if p)
            raw_text_parts = [f"Imported from {path.name}."]
            if address:
                raw_text_parts.append(address)
            if fields.get("original_source"):
                raw_text_parts.append(f"Source in original file: {fields['original_source']}")

            candidate = LeadCandidate(
                source="csv_import",
                source_detail=source_detail,
                company=company,
                contact_name=contact_name,
                title=fields.get("category", ""),
                email=fields.get("email", ""),
                phone=fields.get("phone", ""),
                url=fields.get("url", ""),
                raw_text="\n".join(raw_text_parts),
            )
            lead_id, is_new = db.upsert_candidate(candidate, score=score)

            # Only seed stage/notes/follow-up from the file on the lead's
            # first import - same rule upsert_candidate itself already
            # applies to stage/notes on a plain re-fetch (see its
            # docstring): once it's a real lead in this CRM, only you edit
            # it here, so re-importing an updated export later (e.g. the
            # other CRM tool's refreshed dump) can't quietly clobber
            # status changes or notes you've since added.
            if is_new:
                notes_parts = []
                last_contact_iso, last_contact_warning = _parse_date(fields.get("last_contact", ""))
                if last_contact_warning:
                    result.warnings.append(f"line {line_number}: last contact {last_contact_warning}")
                if last_contact_iso:
                    notes_parts.append(f"Last contact: {last_contact_iso}.")
                if fields.get("notes"):
                    notes_parts.append(fields["notes"])
                if fields.get("owner"):
                    notes_parts.append(f"(Owner: {fields['owner']})")
                notes = " ".join(notes_parts) or None

                if stage or notes or next_follow_up:
                    db.update_lead(lead_id, stage=stage, notes=notes, next_follow_up=next_follow_up)

    return result
