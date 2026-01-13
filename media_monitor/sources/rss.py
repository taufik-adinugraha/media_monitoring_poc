from __future__ import annotations

import socket
from typing import Dict, List, Any

import feedparser


def fetch_rss_feed(url: str, user_agent: str | None = None) -> List[dict]:
    if user_agent:
        feedparser.USER_AGENT = user_agent
    try:
        feed = feedparser.parse(url)

        if getattr(feed, "bozo", False):
            # bozo_exception may exist; don't crash
            return []

        return feed.entries or []

    except (socket.timeout, ConnectionResetError):
        return []
    except Exception:
        return []


def fetch_rss_feeds(feeds: Dict[str, str], user_agent: str | None = None) -> Dict[str, List[dict]]:
    out: Dict[str, List[dict]] = {}
    for name, url in feeds.items():
        entries = fetch_rss_feed(url, user_agent=user_agent)
        # annotate for downstream normalization
        for e in entries:
            if isinstance(e, dict):
                e["_ingested_from"] = "rss"
                e["_feed_name"] = name
                e["_feed_url"] = url
        out[name] = entries
    return out
