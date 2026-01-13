from __future__ import annotations

import feedparser
import socket
from typing import Any, Dict, List

import requests


def channel_feed_url(channel_id: str) -> str:
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


def fetch_youtube_channel_rss(url: str, user_agent: str | None = None) -> List[dict]:
    if user_agent:
        feedparser.USER_AGENT = user_agent
    try:
        feed = feedparser.parse(url)
        if getattr(feed, "bozo", False):
            return []
        return feed.entries or []
    except (socket.timeout, ConnectionResetError):
        return []
    except Exception:
        return []


def fetch_youtube_channels(channels: Dict[str, str], user_agent: str | None = None) -> Dict[str, List[dict]]:
    """channels: mapping name -> channel_id (UC...) OR full feed url."""
    out: Dict[str, List[dict]] = {}
    for name, cid_or_url in channels.items():
        url = cid_or_url if cid_or_url.startswith("http") else channel_feed_url(cid_or_url)
        entries = fetch_youtube_channel_rss(url, user_agent=user_agent)
        for e in entries:
            if isinstance(e, dict):
                e["_ingested_from"] = "youtube"
                e["_channel_name"] = name
                e["_channel_id"] = cid_or_url if not cid_or_url.startswith("http") else None
                link = e.get("link") or ""
                if "watch?v=" in link:
                    e["video_id"] = link.split("watch?v=")[-1].split("&")[0]
        out[name] = entries
    return out


def fetch_youtube_video_stats(api_key: str, video_ids: List[str], timeout_s: int = 30) -> Dict[str, Dict[str, int]]:
    """Optional enrichment via YouTube Data API."""
    if not video_ids:
        return {}
    out: Dict[str, Dict[str, int]] = {}
    base = "https://www.googleapis.com/youtube/v3/videos"
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i:i+50]
        params = {"part": "statistics", "id": ",".join(chunk), "key": api_key}
        r = requests.get(base, params=params, timeout=timeout_s)
        r.raise_for_status()
        payload = r.json()
        for it in payload.get("items", []) or []:
            vid = it.get("id")
            stats = it.get("statistics", {}) or {}
            out[vid] = {
                "views": int(stats.get("viewCount") or 0),
                "likes": int(stats.get("likeCount") or 0),
                "comments": int(stats.get("commentCount") or 0),
            }
    return out
