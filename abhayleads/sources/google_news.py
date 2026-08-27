"""Google News, via its free public RSS search feed. No API key needed.

Good for: press mentions, funding announcements, "X launches" stories -
signals that a company is growing/spending and might be a buyer.
"""

from urllib.parse import quote_plus

import feedparser
import requests

from ..models import LeadCandidate
from .base import USER_AGENT, BaseLeadSource

FEED_URL = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"


class GoogleNewsSource(BaseLeadSource):
    name = "google_news"

    def fetch(self, keywords: list[str]) -> list[LeadCandidate]:
        candidates: list[LeadCandidate] = []
        seen_links: set[str] = set()

        for keyword in keywords:
            url = FEED_URL.format(query=quote_plus(keyword))
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
