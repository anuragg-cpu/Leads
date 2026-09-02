import tempfile
import threading
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


def make_osm_candidate(company: str, locality: str, source_detail: str):
    return LeadCandidate(
        source="osm_places",
        source_detail=source_detail,
        company=company,
        title=f"Housing society / apartment complex: {company} ({locality})",
        raw_text=f"Housing society near {locality}",
    )


def test_merge_exact_duplicate_osm_leads_collapses_same_name_same_locality(db):
    id1, _ = db.upsert_candidate(
        make_osm_candidate("Prakrtii CHS G Block", "Baner", "https://osm/way/1"), score=30
    )
    id2, _ = db.upsert_candidate(
        make_osm_candidate("Prakrtii CHS G Block", "Baner", "https://osm/node/2"), score=30
    )

    summaries = db.merge_exact_duplicate_osm_leads()

    assert len(summaries) == 1
    assert summaries[0]["kept_id"] == min(id1, id2)
    assert summaries[0]["removed_ids"] == [max(id1, id2)]
    assert db.get_lead(max(id1, id2)) is None
    assert len(db.list_leads(source="osm_places")) == 1


def test_merge_exact_duplicate_osm_leads_keeps_different_names_and_localities(db):
    db.upsert_candidate(make_osm_candidate("Prakrtii CHS G Block", "Baner", "https://osm/way/1"), score=30)
    db.upsert_candidate(make_osm_candidate("Prakrtii CHS F Block", "Baner", "https://osm/way/2"), score=30)
    db.upsert_candidate(make_osm_candidate("Prakrtii CHS G Block", "Aundh", "https://osm/way/3"), score=30)

    summaries = db.merge_exact_duplicate_osm_leads()

    assert summaries == []
    assert len(db.list_leads(source="osm_places")) == 3


def test_merge_exact_duplicate_osm_leads_preserves_the_worked_one(db):
    id1, _ = db.upsert_candidate(
        make_osm_candidate("Prakrtii CHS G Block", "Baner", "https://osm/way/1"), score=30
    )
    id2, _ = db.upsert_candidate(
        make_osm_candidate("Prakrtii CHS G Block", "Baner", "https://osm/node/2"), score=30
    )
    db.update_lead(id2, stage="Contacted", notes="spoke to the secretary")

    summaries = db.merge_exact_duplicate_osm_leads()

    assert summaries[0]["kept_id"] == id2
    remaining = db.get_lead(id2)
    assert remaining["stage"] == "Contacted"
    assert remaining["notes"] == "spoke to the secretary"
    assert db.get_lead(id1) is None


def test_fetch_run_lifecycle(db):
    run_id = db.start_fetch_run(["hackernews", "reddit"])
    db.finish_fetch_run(run_id, new_leads=3, updated_leads=1, errors=[])

    last_run = db.last_fetch_run()
    assert last_run["id"] == run_id
    assert last_run["new_leads"] == 3
    assert last_run["updated_leads"] == 1


def test_update_lead_can_edit_contact_fields(db):
    lead_id, _ = db.upsert_candidate(make_candidate(), score=50)

    db.update_lead(
        lead_id,
        company="Acme Corp",
        contact_name="Jane Doe",
        title="Facilities Manager",
        email="jane@acme.example",
        phone="+91 98765 43210",
        url="https://acme.example",
    )

    lead = db.get_lead(lead_id)
    assert lead["company"] == "Acme Corp"
    assert lead["contact_name"] == "Jane Doe"
    assert lead["title"] == "Facilities Manager"
    assert lead["email"] == "jane@acme.example"
    assert lead["phone"] == "+91 98765 43210"
    assert lead["url"] == "https://acme.example"


def test_update_lead_contact_fields_default_to_untouched(db):
    lead_id, _ = db.upsert_candidate(make_candidate(company="Original"), score=50)
    db.update_lead(lead_id, notes="just a note")

    lead = db.get_lead(lead_id)
    assert lead["company"] == "Original"  # untouched when not passed


def test_delete_all_leads_wipes_leads_history_and_runs(db):
    id1, _ = db.upsert_candidate(make_candidate(source_detail="a"), score=10)
    db.upsert_candidate(make_candidate(source_detail="b"), score=20)
    db.update_lead(id1, stage="Contacted")
    run_id = db.start_fetch_run(["hackernews"])
    db.finish_fetch_run(run_id, new_leads=2, updated_leads=0, errors=[])

    removed = db.delete_all_leads()

    assert removed == 2
    assert db.list_leads() == []
    assert db.stage_history(id1) == []
    assert db.last_fetch_run() is None


def test_get_last_digest_at_defaults_to_none(db):
    assert db.get_last_digest_at() is None


def test_set_and_get_last_digest_at(db):
    db.set_last_digest_at("2026-08-31T08:00:00+00:00")
    assert db.get_last_digest_at() == "2026-08-31T08:00:00+00:00"

    db.set_last_digest_at("2026-09-01T08:00:00+00:00")  # a second call updates, doesn't error
    assert db.get_last_digest_at() == "2026-09-01T08:00:00+00:00"


def test_summarize_since_none_counts_everything(db):
    db.upsert_candidate(make_candidate(source_detail="a"), score=10)
    db.upsert_candidate(make_candidate(source_detail="b"), score=20)

    summary = db.summarize_since(None)

    assert summary["new_leads"] == 2
    assert summary["updated_leads"] == 0


def test_summarize_since_a_future_cutoff_excludes_leads_created_now(db):
    db.upsert_candidate(make_candidate(source_detail="a"), score=10)

    summary = db.summarize_since("2099-01-01T00:00:00+00:00")

    assert summary["new_leads"] == 0


def test_summarize_since_a_past_cutoff_includes_leads_created_now(db):
    db.upsert_candidate(make_candidate(source_detail="a"), score=10)

    summary = db.summarize_since("2000-01-01T00:00:00+00:00")

    assert summary["new_leads"] == 1


def test_summarize_since_does_not_double_count_a_lead_in_the_same_second_as_the_cutoff(db):
    # Regression test: timestamps only have second precision, and `since`
    # is normally exactly what the previous digest stamped right after
    # counting a lead as new. If a lead's created_at lands in that same
    # second, it must not be reported as new again on the next digest.
    lead_id, _ = db.upsert_candidate(make_candidate(source_detail="a"), score=10)
    created_at = db.get_lead(lead_id)["created_at"]

    summary = db.summarize_since(created_at)  # same instant as the lead's own creation

    assert summary["new_leads"] == 0


def test_summarize_since_counts_a_lead_updated_after_the_cutoff(db, monkeypatch):
    lead_id, _ = db.upsert_candidate(make_candidate(source_detail="a"), score=10)
    since = db.get_lead(lead_id)["created_at"]

    # Force a distinct, later updated_at - real usage always has this
    # naturally, but a fast test could otherwise land in the same second
    # as `since` and make this assertion timing-dependent.
    monkeypatch.setattr("abhayleads.db.utcnow_iso", lambda: "2099-01-01T00:00:00+00:00")
    db.update_lead(lead_id, notes="called them")

    summary = db.summarize_since(since)

    assert summary["new_leads"] == 0
    assert summary["updated_leads"] == 1


def test_connection_usable_across_threads():
    # Regression test: `abhayleads serve` opens one Database per HTTP
    # request via a sync FastAPI dependency. The thread pool FastAPI runs
    # sync dependencies on doesn't guarantee the same worker thread
    # handles both the "before yield" (open) and "after yield" (close)
    # halves of a request - without check_same_thread=False in
    # Database.__init__, that mismatch raised "SQLite objects created in
    # a thread can only be used in that same thread" under real
    # concurrent load, live-tested against a running `abhayleads serve`.
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        holder: dict = {}
        opened = threading.Event()
        # Keeps thread A alive (and thus its native thread id un-recycled)
        # until thread B is done - joining thread A before starting thread
        # B would let the OS/interpreter hand thread B the very same
        # thread id thread A just freed up, making this pass even without
        # the fix (found the hard way: the first version of this test did
        # exactly that and passed regardless of check_same_thread).
        thread_b_done = threading.Event()

        def open_on_thread_a():
            holder["db"] = Database(db_path)
            opened.set()
            thread_b_done.wait(timeout=5)

        def use_and_close_on_thread_b():
            opened.wait(timeout=5)
            try:
                holder["db"].upsert_candidate(make_candidate(source_detail="thread-b"), score=10)
                holder["db"].stats()
                holder["db"].close()
            except Exception as exc:  # noqa: BLE001 - re-raised on the main thread below
                holder["error"] = exc
            finally:
                thread_b_done.set()

        t1 = threading.Thread(target=open_on_thread_a)
        t2 = threading.Thread(target=use_and_close_on_thread_b)
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        if "error" in holder:
            raise holder["error"]


def test_opening_a_pre_existing_db_without_lat_lon_columns_migrates_cleanly():
    # Simulates a leads.db created before lat/lon existed - CREATE TABLE
    # IF NOT EXISTS is a no-op on an already-existing table, so opening
    # one of these needs the explicit ALTER TABLE migration to not crash
    # the moment anything touches the lat/lon columns.
    import sqlite3

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "old.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript(
            """
            CREATE TABLE leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dedup_key TEXT UNIQUE NOT NULL,
                company TEXT DEFAULT '',
                contact_name TEXT DEFAULT '',
                title TEXT DEFAULT '',
                email TEXT DEFAULT '',
                phone TEXT DEFAULT '',
                url TEXT DEFAULT '',
                source TEXT NOT NULL,
                source_detail TEXT DEFAULT '',
                keyword_matched TEXT DEFAULT '',
                raw_text TEXT DEFAULT '',
                score INTEGER DEFAULT 0,
                stage TEXT DEFAULT 'New',
                notes TEXT DEFAULT '',
                next_follow_up TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            );
            CREATE TABLE stage_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
                stage TEXT NOT NULL,
                changed_at TEXT NOT NULL
            );
            """
        )
        conn.commit()
        conn.close()

        database = Database(db_path)
        try:
            lead_id, _ = database.upsert_candidate(make_candidate(lat=1.0, lon=2.0), score=10)
            lead = database.get_lead(lead_id)
            assert lead["lat"] == 1.0
            assert lead["lon"] == 2.0
        finally:
            database.close()


def test_upsert_candidate_stores_coordinates(db):
    lead_id, _ = db.upsert_candidate(make_candidate(lat=18.55, lon=73.78), score=30)
    lead = db.get_lead(lead_id)
    assert lead["lat"] == 18.55
    assert lead["lon"] == 73.78


def test_upsert_candidate_without_coordinates_leaves_them_null(db):
    lead_id, _ = db.upsert_candidate(make_candidate(), score=10)
    lead = db.get_lead(lead_id)
    assert lead["lat"] is None
    assert lead["lon"] is None


def test_upsert_candidate_refreshes_coordinates_on_rediscovery(db):
    candidate = make_candidate(source_detail="same-place", lat=18.55, lon=73.78)
    lead_id, _ = db.upsert_candidate(candidate, score=30)

    moved = make_candidate(source_detail="same-place", lat=18.56, lon=73.79)
    db.upsert_candidate(moved, score=30)

    lead = db.get_lead(lead_id)
    assert lead["lat"] == 18.56
    assert lead["lon"] == 73.79


def test_upsert_candidate_rediscovery_without_coordinates_keeps_existing_ones(db):
    # A re-fetch that doesn't carry a point (e.g. a different source
    # matching the same dedup key) must never blank out a point this
    # lead already had.
    candidate = make_candidate(source_detail="same-place", lat=18.55, lon=73.78)
    lead_id, _ = db.upsert_candidate(candidate, score=30)

    no_point = make_candidate(source_detail="same-place")
    db.upsert_candidate(no_point, score=30)

    lead = db.get_lead(lead_id)
    assert lead["lat"] == 18.55
    assert lead["lon"] == 73.78


def test_leads_with_coordinates_only_returns_leads_that_have_a_point(db):
    db.upsert_candidate(make_candidate(source_detail="a", lat=18.55, lon=73.78), score=30)
    db.upsert_candidate(make_candidate(source_detail="b"), score=10)

    points = db.leads_with_coordinates()

    assert len(points) == 1
    assert points[0]["lat"] == 18.55


def test_leads_with_coordinates_filters_by_stage(db):
    lead_id, _ = db.upsert_candidate(make_candidate(source_detail="a", lat=18.55, lon=73.78), score=30)
    db.upsert_candidate(make_candidate(source_detail="b", lat=1.0, lon=2.0), score=30)
    db.update_lead(lead_id, stage="Contacted")

    points = db.leads_with_coordinates(stage="Contacted")

    assert len(points) == 1
    assert points[0]["id"] == lead_id
