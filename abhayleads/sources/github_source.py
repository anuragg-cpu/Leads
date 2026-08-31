"""GitHub repository search, via the free public REST API.

Works with no token (10 requests/min); set GITHUB_TOKEN (a free personal
access token with no scopes) to raise that to 30/min. See docs/SOURCES.md.

Good for: dev-tool / API / infra products - finds repos whose README or
description mentions your problem space, i.e. teams actively building in
that area right now.
"""

import os
from typing import Iterator

import requests

from ..models import LeadCandidate
from .base import USER_AGENT, BaseLeadSource

SEARCH_URL = "https://api.github.com/search/repositories"


class GitHubSource(BaseLeadSource):
    name = "github"

    def fetch(self, keywords: list[str]) -> Iterator[LeadCandidate]:
        token = os.environ.get(self.source_config.get("token_env_var", "GITHUB_TOKEN"), "")
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github+json",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"

        seen_repos: set[str] = set()

        for keyword in keywords:
            resp = requests.get(
                SEARCH_URL,
                params={"q": keyword, "sort": "updated", "order": "desc", "per_page": 20},
                headers=headers,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

            for repo in data.get("items", []):
                full_name = repo.get("full_name", "")
                if not full_name or full_name in seen_repos:
                    continue
                seen_repos.add(full_name)

                owner = repo.get("owner", {}).get("login", "")
                description = repo.get("description") or ""

                yield LeadCandidate(
                    source=self.name,
                    source_detail=repo.get("html_url", full_name),
                    company=full_name,
                    contact_name=owner,
                    title=full_name,
                    url=repo.get("html_url", ""),
                    raw_text=description,
                )
