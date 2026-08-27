"""Config loading with sane defaults, so the app runs even before
config.yaml exists (it just won't match anything useful yet)."""

import copy
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG: dict[str, Any] = {
    "product": {
        "name": "Abhay",
        "description": "",
        "keywords": [],
        "exclude_keywords": [],
        "target_locations": [],
    },
    "sources": {
        "hackernews": {"enabled": True},
        "google_news": {"enabled": True},
        "github": {"enabled": False, "token_env_var": "GITHUB_TOKEN"},
        "reddit": {
            "enabled": True,
            "subreddits": ["startups", "smallbusiness", "Entrepreneur"],
            "client_id_env_var": "REDDIT_CLIENT_ID",
            "client_secret_env_var": "REDDIT_CLIENT_SECRET",
        },
    },
    "scoring": {
        "points_per_keyword": 20,
        "title_match_bonus": 15,
        "source_weights": {
            "hackernews": 1.0,
            "google_news": 0.8,
            "github": 0.9,
            "reddit": 1.0,
        },
    },
    "follow_up": {"default_days": 3},
}


def _deep_merge(base: dict, override: dict) -> dict:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def default_paths() -> tuple[Path, Path]:
    """Returns (config_dir, app_data_dir).

    Both live next to the project when run from source, or in the user's
    home folder when run as a frozen .exe (so the packaged app doesn't try
    to write inside its own install directory).
    """
    import sys

    if getattr(sys, "frozen", False):
        base = Path.home() / "AbhayLeads"
    else:
        base = Path(__file__).resolve().parent.parent
    base.mkdir(parents=True, exist_ok=True)
    return base / "config", base


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    config_dir, _ = default_paths()
    if config_path is None:
        config_path = config_dir / "config.yaml"

    if not config_path.exists():
        example = Path(__file__).resolve().parent.parent / "config" / "config.example.yaml"
        return copy.deepcopy(DEFAULT_CONFIG) if not example.exists() else _deep_merge(
            DEFAULT_CONFIG, yaml.safe_load(example.read_text()) or {}
        )

    with open(config_path, "r", encoding="utf-8") as f:
        user_config = yaml.safe_load(f) or {}
    return _deep_merge(DEFAULT_CONFIG, user_config)
