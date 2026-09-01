"""Tests for db_factory.open_db - the local-vs-remote switch shared by the
CLI and the GUI."""

import tempfile
from pathlib import Path

from abhayleads.db import Database
from abhayleads.db_factory import open_db
from abhayleads.remote_db import RemoteDatabase


def test_open_db_returns_local_database_when_remote_server_not_set():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "leads.db"
        db = open_db(db_path, {})
        try:
            assert isinstance(db, Database)
            assert db_path.exists()
        finally:
            db.close()


def test_open_db_returns_local_database_when_remote_server_base_url_blank():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "leads.db"
        db = open_db(db_path, {"remote_server": {"base_url": "", "token": ""}})
        try:
            assert isinstance(db, Database)
        finally:
            db.close()


def test_open_db_returns_remote_database_when_base_url_set():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "leads.db"
        db = open_db(
            db_path, {"remote_server": {"base_url": "http://example.com", "token": "tok"}}
        )
        try:
            assert isinstance(db, RemoteDatabase)
            assert not db_path.exists(), "remote mode must never create a local db file"
        finally:
            db.close()
