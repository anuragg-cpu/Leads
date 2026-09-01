"""Picks a local Database or a RemoteDatabase based on config - shared by
the CLI and the GUI so both behave identically once remote_server.base_url
is set in a profile's config.yaml. See docs/SERVER_SETUP.md.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any, Union

from .db import Database

if TYPE_CHECKING:
    from .remote_db import RemoteDatabase


def open_db(db_path: Path, config: dict[str, Any]) -> Union[Database, "RemoteDatabase"]:
    remote = config.get("remote_server", {}) or {}
    if remote.get("base_url"):
        from .remote_db import RemoteDatabase

        return RemoteDatabase(remote["base_url"], remote.get("token", ""))
    return Database(db_path)
