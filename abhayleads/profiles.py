"""Multi-profile support.

A "profile" is one product/company: its own config.yaml (keywords,
sources, scoring) and its own leads.db, so running Abhay Leads for a
second, unrelated product never mixes its keywords or its leads with
the first. Profiles live under <app_data_dir>/profiles/<name>/, tracked
by a small registry file (profiles.json) that also remembers which one
is "active" (what the GUI opens, and what the CLI uses when you don't
pass --profile).

If you're upgrading from before profiles existed, your existing
config.yaml and leads.db (directly under the app data dir) are copied
into a profile called "default" the first time this runs - nothing is
deleted, and the originals are left in place untouched.
"""

import json
import re
import shutil
from pathlib import Path
from typing import Optional

from .config import default_paths

REGISTRY_FILENAME = "profiles.json"
DEFAULT_PROFILE_NAME = "default"
_INVALID_NAME_CHARS = re.compile(r'[\\/:*?"<>|]')


def profiles_root() -> Path:
    _, app_data_dir = default_paths()
    root = app_data_dir / "profiles"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _registry_path() -> Path:
    _, app_data_dir = default_paths()
    return app_data_dir / REGISTRY_FILENAME


def _load_registry() -> dict:
    path = _registry_path()
    if not path.exists():
        return {"active": None, "profiles": []}
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {"active": None, "profiles": []}
    data.setdefault("active", None)
    data.setdefault("profiles", [])
    return data


def _save_registry(registry: dict):
    _registry_path().write_text(json.dumps(registry, indent=2))


def _migrate_legacy_single_profile(registry: dict) -> dict:
    """One-time: wrap a pre-profiles install's config.yaml/leads.db into
    a "default" profile, if one hasn't already been set up."""
    if registry["profiles"]:
        return registry

    _, app_data_dir = default_paths()
    legacy_config = app_data_dir / "config" / "config.yaml"
    legacy_db = app_data_dir / "leads.db"
    if not legacy_config.exists() and not legacy_db.exists():
        return registry

    profile_dir = profiles_root() / DEFAULT_PROFILE_NAME
    profile_dir.mkdir(parents=True, exist_ok=True)
    new_config, new_db = profile_paths(DEFAULT_PROFILE_NAME)
    if legacy_config.exists() and not new_config.exists():
        shutil.copy2(legacy_config, new_config)
    if legacy_db.exists() and not new_db.exists():
        shutil.copy2(legacy_db, new_db)

    registry["profiles"] = [DEFAULT_PROFILE_NAME]
    registry["active"] = DEFAULT_PROFILE_NAME
    _save_registry(registry)
    return registry


def _validate_name(name: str):
    name = name.strip()
    if not name:
        raise ValueError("Profile name can't be empty")
    if _INVALID_NAME_CHARS.search(name):
        raise ValueError('Profile name can\'t contain \\ / : * ? " < > |')
    return name


def profile_paths(name: str) -> tuple[Path, Path]:
    """Returns (config_path, db_path) for a profile - doesn't require the
    profile to exist yet or to be registered."""
    profile_dir = profiles_root() / name
    return profile_dir / "config.yaml", profile_dir / "leads.db"


def list_profiles() -> list[str]:
    registry = _migrate_legacy_single_profile(_load_registry())
    return sorted(registry["profiles"])


def get_active_profile() -> Optional[str]:
    registry = _migrate_legacy_single_profile(_load_registry())
    return registry["active"]


def set_active_profile(name: str):
    registry = _load_registry()
    if name not in registry["profiles"]:
        raise ValueError(f"No such profile: {name!r}")
    registry["active"] = name
    _save_registry(registry)


def create_profile(name: str) -> tuple[Path, Path]:
    """Creates a new profile with a fresh config.yaml (copied from the
    packaged template) and an empty leads.db (created on first use).
    Returns (config_path, db_path). Becomes the active profile if this
    is the first one."""
    name = _validate_name(name)

    registry = _migrate_legacy_single_profile(_load_registry())
    if name in registry["profiles"]:
        raise ValueError(f"Profile {name!r} already exists")

    config_path, db_path = profile_paths(name)
    config_path.parent.mkdir(parents=True, exist_ok=True)

    if not config_path.exists():
        example = Path(__file__).resolve().parent.parent / "config" / "config.example.yaml"
        if example.exists():
            template_text = example.read_text()
        else:
            template_text = 'product:\n  name: ""\n  keywords: []\n  exclude_keywords: []\n'
        config_path.write_text(template_text)

    registry["profiles"].append(name)
    if not registry["active"]:
        registry["active"] = name
    _save_registry(registry)

    return config_path, db_path


def delete_profile(name: str, delete_files: bool = False):
    registry = _load_registry()
    if name not in registry["profiles"]:
        raise ValueError(f"No such profile: {name!r}")

    registry["profiles"].remove(name)
    if registry["active"] == name:
        registry["active"] = registry["profiles"][0] if registry["profiles"] else None
    _save_registry(registry)

    if delete_files:
        profile_dir = profiles_root() / name
        if profile_dir.exists():
            shutil.rmtree(profile_dir)
