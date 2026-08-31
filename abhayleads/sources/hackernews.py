"""Hacker News, via the free public Algolia HN Search API.

No API key needed, no rate-limit headaches for occasional runs.
Docs: https://hn.algolia.com/api

Good for: catching people publicly discussing a problem your product
solves, or posting "Show HN" launches of adjacent tools (worth watching
as competitors, or as partnership/backlink opportunities).
"""

from typing import Iterator

import requests

from ..models import LeadCandidate
from .base import USER_AGENT, BaseLeadSource

SEARCH_URL = "https://hn.algolia.com/api/v1/search"


class HackerNewsSource(BaseLeadSource):
    name = "hackernews"

    def fetch(self, keywords: list[str]) -> Iterator[LeadCandidate]:
        seen_ids: set[str] = set()

        for keyword in keywords:
            resp = requests.get(
                SEARCH_URL,
                params={"query": keyword, "tags": "story", "hitsPerPage": 25},
                headers={"User-Agent": USER_AGENT},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

            for hit in data.get("hits", []):
                object_id = hit.get("objectID")
                if not object_id or object_id in seen_ids:
                    continue
                seen_ids.add(object_id)

                title = hit.get("title") or hit.get("story_title") or ""
                body = hit.get("story_text") or hit.get("comment_text") or ""
                url = hit.get("url") or f"https://news.ycombinator.com/item?id={object_id}"
                author = hit.get("author") or ""

                yield LeadCandidate(
                    source=self.name,
                    source_detail=f"https://news.ycombinator.com/item?id={object_id}",
                    contact_name=author,
                    title=title,
                    url=url,
                    raw_text=f"{title}\n{body}",
                )
