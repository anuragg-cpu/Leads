"""Push notifications to your phone via ntfy (https://ntfy.sh).

Why ntfy: it's free, needs no account/signup on either end, and a
message is just one plain HTTP POST - no SDK, no API key to protect.
You pick a topic name, install the free "ntfy" app on your phone and
subscribe to that same topic, and anything posted to it shows up as a
push notification within seconds. See docs/NOTIFICATIONS.md for the
full setup walkthrough.

The one thing to know: by default ntfy.sh topics are public by
obscurity - anyone who knows (or guesses) your topic name can read your
messages and post their own to it. Pick something long and random, not
"abhayleads". docs/NOTIFICATIONS.md covers self-hosting or a paid ntfy
plan for real privacy if that matters to you.
"""

import requests

DEFAULT_NTFY_BASE_URL = "https://ntfy.sh"


def send_ntfy(
    topic: str,
    message: str,
    title: str = "",
    priority: str = "default",
    base_url: str = DEFAULT_NTFY_BASE_URL,
) -> None:
    """Posts one push notification to the given ntfy topic. Raises on
    failure (network error, bad topic) - callers decide how to surface
    that; this doesn't swallow errors itself since a silently-failed
    notification defeats the point of having one.
    """
    if not topic:
        raise ValueError("No ntfy topic given - set notifications.ntfy_topic in config.yaml first.")

    headers = {"Priority": priority}
    if title:
        # HTTP headers must be Latin-1/ASCII; requests would raise deep
        # inside itself on a non-ASCII title (unlikely - titles here are
        # just "Abhay Leads" plus a profile name - but strip rather than
        # crash the notification over it). The message body is unaffected
        # and sent as full UTF-8.
        headers["Title"] = title.encode("ascii", errors="ignore").decode("ascii") or "Abhay Leads"

    resp = requests.post(
        f"{base_url.rstrip('/')}/{topic}",
        data=message.encode("utf-8"),
        headers=headers,
        timeout=15,
    )
    resp.raise_for_status()
