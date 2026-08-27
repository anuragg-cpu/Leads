import tempfile
from pathlib import Path

import pytest

from abhayleads.db import Database
from abhayleads.models import LeadCandidate


@pytest.fixture
def db():
    with tempfile.TemporaryDirectory() as tmp:
        database = Database(Path(tmp) / "test.db")
        yield database
        database.close()


def make_candidate(**overrides):
    defaults = dict(
        source="hackernews",
        source_detail="https://news.ycombinator.com/item?id=1",
        company="Acme",
        contact_name="jdoe",
        title="Looking for a tool",
        raw_text="Looking for a tool to do X",
    )
    defaults.update(overrides)
    return LeadCandidate(**defaults)


def test_upsert_inserts_new_lead(db):
    lead_id, is_new = db.upsert_candidate(make_candidate(), score=50)
    assert is_new is True

    lead = db.get_lead(lead_id)
    assert lead["company"] == "Acme"
    assert lead["stage"] == "New"
    assert lead["score"] == 50


def test_upsert_same_candidate_twice_does_not_duplicate(db):
    candidate = make_candidate()
    id1, is_new1 = db.upsert_candidate(candidate, score=50)
    id2, is_new2 = db.upsert_candidate(candidate, score=60)

    assert id1 == id2
    assert is_new1 is True
    assert is_new2 is False

    leads = db.list_leads()
    assert len(leads) == 1
    assert leads[0]["score"] == 60  # kept the higher score


def test_upsert_preserves_user_edits_on_reseen_lead(db):
    candidate = make_candidate()
    lead_id, _ = db.upsert_candidate(candidate, score=50)
    db.update_lead(lead_id, stage="Contacted", notes="called them")

    db.upsert_candidate(candidate, score=70)

    lead = db.get_lead(lead_id)
    assert lead["stage"] == "Contacted"
    assert lead["notes"] == "called them"


def test_update_lead_records_stage_history(db):
    lead_id, _ = db.upsert_candidate(make_candidate(), score=50)
    db.update_lead(lead_id, stage="Contacted")
    db.update_lead(lead_id, stage="Replied")

    history = db.stage_history(lead_id)
    stages = [row["stage"] for row in history]
    assert stages == ["New", "Contacted", "Replied"]


def test_update_lead_rejects_unknown_stage(db):
    lead_id, _ = db.upsert_candidate(make_candidate(), score=50)
    with pytest.raises(ValueError):
        db.update_lead(lead_id, stage="NotAStage")


def test_list_leads_filters_by_stage_and_score(db):
    db.upsert_candidate(make_candidate(source_detail="a"), score=10)
    id_b, _ = db.upsert_candidate(make_candidate(source_detail="b"), score=90)
    db.update_lead(id_b, stage="Qualified")

    high_score = db.list_leads(min_score=50)
    assert len(high_score) == 1
    assert high_score[0]["id"] == id_b

    qualified = db.list_leads(stage="Qualified")
    assert len(qualified) == 1
    assert qualified[0]["id"] == id_b


def test_stats_counts_by_stage_and_source(db):
    db.upsert_candidate(make_candidate(source_detail="a", source="hackernews"), score=10)
    db.upsert_candidate(make_candidate(source_detail="b", source="reddit"), score=20)

    stats = db.stats()
    assert stats["total"] == 2
    assert stats["by_stage"]["New"] == 2
    assert stats["by_source"]["hackernews"] == 1
    assert stats["by_source"]["reddit"] == 1


def test_fetch_run_lifecycle(db):
    run_id = db.start_fetch_run(["hackernews", "reddit"])
    db.finish_fetch_run(run_id, new_leads=3, updated_leads=1, errors=[])

    last_run = db.last_fetch_run()
    assert last_run["id"] == run_id
    assert last_run["new_leads"] == 3
    assert last_run["updated_leads"] == 1
