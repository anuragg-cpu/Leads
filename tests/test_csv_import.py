import tempfile
from pathlib import Path

import pytest

from abhayleads.csv_import import import_csv
from abhayleads.db import Database


@pytest.fixture
def db():
    with tempfile.TemporaryDirectory() as tmp:
        database = Database(Path(tmp) / "test.db")
        yield database
        database.close()


def write_csv(tmp_path: Path, header: str, *rows: str) -> Path:
    path = tmp_path / "leads.csv"
    path.write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return path


def test_imports_a_simple_generic_csv(db, tmp_path):
    path = write_csv(
        tmp_path,
        "company,contact_name,email,phone,notes",
        "Acme Security,Jane Doe,jane@acme.example,+91 98765 43210,Met at expo",
    )
    result = import_csv(db, path)

    assert result.imported == 1
    assert result.skipped == 0
    leads = db.list_leads()
    assert len(leads) == 1
    assert leads[0]["company"] == "Acme Security"
    assert leads[0]["contact_name"] == "Jane Doe"
    assert leads[0]["email"] == "jane@acme.example"
    assert leads[0]["notes"] == "Met at expo"
    assert leads[0]["source"] == "csv_import"


def test_recognizes_real_world_crm_export_column_aliases(db, tmp_path):
    # Mirrors the shape of an actual export from another CRM tool -
    # different header names than this app's own field names.
    path = write_csv(
        tmp_path,
        "Lead ID,Segment,Org/Society Name,Contact Person,Phone,Email,Area/Zone,City,Source,Lead Score,Status,Last Contact,Next Follow-up,Notes,Owner",
        'L100,System Integrator/Dealer,Test Security Systems,Ravi Kumar,9998887777,ravi@test.example,"Some Street, Baner",Pune,Places-Auto,4,Contacted,06/07/2026,15/07/2026,Will call back,Ravi',
    )
    result = import_csv(db, path)

    assert result.imported == 1
    lead = db.list_leads()[0]
    assert lead["company"] == "Test Security Systems"
    assert lead["contact_name"] == "Ravi Kumar"
    assert lead["title"] == "System Integrator/Dealer"  # Segment -> title
    assert lead["score"] == 4
    assert lead["stage"] == "Contacted"  # Status -> stage
    assert lead["next_follow_up"] == "2026-07-15"  # DD/MM/YYYY -> ISO
    assert "Baner" in lead["raw_text"]
    assert "Will call back" in lead["notes"]
    assert "Last contact: 2026-07-06" in lead["notes"]


def test_skips_rows_with_no_company_or_contact_name(db, tmp_path):
    path = write_csv(
        tmp_path,
        "company,contact_name,notes",
        ",,No company or contact here",
        "Real Co,,",
    )
    result = import_csv(db, path)

    assert result.imported == 1
    assert result.skipped == 1
    assert result.skipped_lines == [2]  # header is line 1, first data row is line 2


def test_warns_on_unrecognized_stage_but_still_imports_as_new(db, tmp_path):
    path = write_csv(tmp_path, "company,status", "Acme,Conatcted")
    result = import_csv(db, path)

    assert result.imported == 1
    lead = db.list_leads()[0]
    assert lead["stage"] == "Contacted"  # known typo fix
    assert not any("unknown status" in w for w in result.warnings)

    path2 = write_csv(tmp_path, "company,status", "Other Co,Definitely Not A Stage")
    result2 = import_csv(db, path2)
    assert result2.imported == 1
    lead2 = [l for l in db.list_leads() if l["company"] == "Other Co"][0]
    assert lead2["stage"] == "New"
    assert any("unknown status" in w and "Definitely Not A Stage" in w for w in result2.warnings)


def test_warns_on_unparseable_date_and_leaves_follow_up_unset(db, tmp_path):
    path = write_csv(tmp_path, "company,next_follow_up", "Acme,not-a-date")
    result = import_csv(db, path)

    assert result.imported == 1
    lead = db.list_leads()[0]
    assert lead["next_follow_up"] is None
    assert any("unrecognized date" in w for w in result.warnings)


def test_dry_run_writes_nothing(db, tmp_path):
    path = write_csv(tmp_path, "company", "Acme")
    result = import_csv(db, path, dry_run=True)

    assert result.imported == 1
    assert db.list_leads() == []


def test_reimporting_same_file_with_external_id_updates_rather_than_duplicates(db, tmp_path):
    path = write_csv(tmp_path, "id,company,score", "L1,Acme,3")
    import_csv(db, path)
    assert len(db.list_leads()) == 1

    # Re-import the same id with a higher score, as a refreshed export
    # from the source CRM might have.
    path2 = write_csv(tmp_path, "id,company,score", "L1,Acme,7")
    result = import_csv(db, path2)

    leads = db.list_leads()
    assert len(leads) == 1  # still just one lead, not two
    assert leads[0]["score"] == 7
    assert result.imported == 1


def test_reimport_never_overwrites_notes_or_stage_the_user_already_set(db, tmp_path):
    path = write_csv(tmp_path, "id,company,status,notes", "L1,Acme,New,from file")
    import_csv(db, path)
    lead_id = db.list_leads()[0]["id"]

    # user works the lead in Abhay Leads
    db.update_lead(lead_id, stage="Qualified", notes="Had a great call, sending quote")

    # a refreshed export comes in with different status/notes for the same id
    path2 = write_csv(tmp_path, "id,company,status,notes", "L1,Acme,Contacted,stale note from CRM")
    import_csv(db, path2)

    lead = db.get_lead(lead_id)
    assert lead["stage"] == "Qualified"
    assert lead["notes"] == "Had a great call, sending quote"


def test_bom_prefixed_header_is_handled(db, tmp_path):
    path = tmp_path / "leads.csv"
    path.write_bytes("﻿company,notes\nAcme,hi\n".encode("utf-8"))
    result = import_csv(db, path)
    assert result.imported == 1
    assert db.list_leads()[0]["company"] == "Acme"


def test_missing_header_row_reports_a_warning_and_imports_nothing(db, tmp_path):
    path = tmp_path / "leads.csv"
    path.write_text("", encoding="utf-8")
    result = import_csv(db, path)
    assert result.imported == 0
    assert result.warnings
