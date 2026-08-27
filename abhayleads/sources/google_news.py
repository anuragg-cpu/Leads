"""Google News, via its free public RSS search feed. No API key needed.

Good for: press mentions, funding announcements, "X launches" stories -
signals that a company is growing/spending and might be a buyer.

Two knobs to keep results relevant to your actual market, both applied
only to *what gets searched* - your configured product.keywords (what
scoring.py matches against) are untouched, so this can't cause a real
match to silently stop scoring:

- `query_suffix` is appended to every search query (e.g. "India"), to
  bias results toward that market without requiring the exact phrase.
- `edition` picks which Google News regional edition to search (hl/gl/
  ceid) - defaults to the US edition, which is why an unconfigured setup
  skews toward US news even for a clearly non-US product.
"""

from urllib.parse import quote_plus

import feedparser
import requests

from ..models import LeadCandidate
from .base import USER_AGENT, BaseLeadSource

FEED_URL = "https://news.google.com/rss/search?q={query}&hl={hl}&gl={gl}&ceid={ceid}"

DEFAULT_EDITION = {"hl": "en-US", "gl": "US", "ceid": "US:en"}


class GoogleNewsSource(BaseLeadSource):
    name = "google_news"

    def fetch(self, keywords: list[str]) -> list[LeadCandidate]:
        query_suffix = (self.source_config.get("query_suffix") or "").strip()
        edition = {**DEFAULT_EDITION, **(self.source_config.get("edition") or {})}

        candidates: list[LeadCandidate] = []
        seen_links: set[str] = set()

        for keyword in keywords:
            query = f"{keyword} {query_suffix}".strip() if query_suffix else keyword
            url = FEED_URL.format(
                query=quote_plus(query),
                hl=edition["hl"],
                gl=edition["gl"],
                ceid=quote_plus(edition["ceid"]),
            )
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)

            for entry in feed.entries[:25]:
                link = entry.get("link", "")
                if not link or link in seen_links:
                    continue
                seen_links.add(link)

                title = entry.get("title", "")
                summary = entry.get("summary", "")
                source_name = entry.get("source", {}).get("title", "") if hasattr(entry, "get") else ""

                candidates.append(
                    LeadCandidate(
                        source=self.name,
                        source_detail=link,
                        company=source_name,
                        title=title,
                        url=link,
                        raw_text=f"{title}\n{summary}",
                    )
                )

        return candidates
