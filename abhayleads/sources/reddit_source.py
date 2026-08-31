"""Reddit search across a configurable list of subreddits.

Two modes, both free:

1. OAuth (recommended) - register a free "script" app at
   https://www.reddit.com/prefs/apps, set REDDIT_CLIENT_ID and
   REDDIT_CLIENT_SECRET (see docs/SOURCES.md), and this uses Reddit's
   official API within its published rate limits.

2. Fallback - if no credentials are set, this reads the public
   `.json` endpoint of each subreddit's search page directly, at a
   deliberately slow pace (1 request/2s) and with an identifying
   User-Agent. This is lower-volume, unauthenticated, read-only access
   and is only intended for occasional personal use - if you plan to
   run this often, set up OAuth instead.

Good for: people describing a problem or asking for recommendations in
communities your buyers hang out in.
"""

import os
import time
from typing import Iterator

import requests

from ..models import LeadCandidate
from .base import USER_AGENT, BaseLeadSource

OAUTH_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
OAUTH_SEARCH_URL = "https://oauth.reddit.com/r/{subreddit}/search"
PUBLIC_SEARCH_URL = "https://www.reddit.com/r/{subreddit}/search.json"


class RedditSource(BaseLeadSource):
    name = "reddit"

    def _get_oauth_token(self) -> str | None:
        client_id = os.environ.get(self.source_config.get("client_id_env_var", "REDDIT_CLIENT_ID"), "")
        client_secret = os.environ.get(
            self.source_config.get("client_secret_env_var", "REDDIT_CLIENT_SECRET"), ""
        )
        if not client_id or not client_secret:
            return None

        resp = requests.post(
            OAUTH_TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=(client_id, client_secret),
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("access_token")

    def fetch(self, keywords: list[str]) -> Iterator[LeadCandidate]:
        subreddits = self.source_config.get("subreddits", []) or []
        if not subreddits:
            return

        token = self._get_oauth_token()
        seen_ids: set[str] = set()

        for subreddit in subreddits:
            for keyword in keywords:
                posts = self._search_one(subreddit, keyword, token)
                for post in posts:
                    post_id = post.get("id", "")
                    if not post_id or post_id in seen_ids:
                        continue
                    seen_ids.add(post_id)

                    title = post.get("title", "")
                    body = post.get("selftext", "")
                    permalink = f"https://www.reddit.com{post.get('permalink', '')}"

                    yield LeadCandidate(
                        source=self.name,
                        source_detail=permalink,
                        contact_name=post.get("author", ""),
                        company=f"r/{subreddit}",
                        title=title,
                        url=permalink,
                        raw_text=f"{title}\n{body}",
                    )

                # Be a polite, low-volume client either way.
                time.sleep(2 if not token else 0.5)

    def _search_one(self, subreddit: str, keyword: str, token: str | None) -> list[dict]:
        params = {"q": keyword, "restrict_sr": "1", "sort": "new", "limit": 25}
        headers = {"User-Agent": USER_AGENT}

        if token:
            headers["Authorization"] = f"Bearer {token}"
            url = OAUTH_SEARCH_URL.format(subreddit=subreddit)
        else:
            url = PUBLIC_SEARCH_URL.format(subreddit=subreddit)

        resp = requests.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return [child.get("data", {}) for child in data.get("data", {}).get("children", [])]
