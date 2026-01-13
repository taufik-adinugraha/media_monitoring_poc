from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .utils import (
    clean_text,
    guess_publisher_from_domain,
    json_dumps,
    now_iso,
    parse_gdelt_seendate,
    safe_parse_dt,
    sha256_text,
)
from .db.store import Store

from .sources.gdelt import fetch_gdelt_artlist
from .sources.mediastack import fetch_mediastack_news
from .sources.rss import fetch_rss_feeds
from .sources.youtube import fetch_youtube_channels, fetch_youtube_video_stats


def _make_id(platform: str, url: str) -> str:
    return sha256_text(platform + "|" + (url or ""))


def _content_hash(title: str, summary: str) -> str:
    return sha256_text((title or "")[:200] + "||" + (summary or "")[:200])


def normalize_gdelt(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for a in articles:
        url = a.get("url") or ""
        domain = a.get("domain") or ""
        pub = guess_publisher_from_domain(domain) if domain else "unknown"
        title = clean_text(a.get("title") or "")
        summary = None
        published = parse_gdelt_seendate(a.get("seendate"))

        signals = {
            "domain": domain,
            "sourcecountry": a.get("sourcecountry"),
            "language": a.get("language"),
            "socialimage": a.get("socialimage"),
            "url_mobile": a.get("url_mobile"),
        }

        rid = _make_id("gdelt", url)
        out.append({
            "id": rid,
            "platform": "gdelt",
            "source_type": "news",
            "publisher_or_author": pub,
            "url": url,
            "title": title or None,
            "summary": summary,
            "published_at": published,
            "ingested_at": now_iso(),
            "topics": None,
            "actors": None,
            "locations": None,
            "language": None,
            "is_editorial": None,
            "tags_json": None,
            "signals_json": json_dumps(signals),
            "raw_json": json_dumps(a),
            "content_hash": _content_hash(title, summary or ""),
            "enriched_at": None,
            "enrich_model": None,
            "enrich_status": None,
            "enrich_error": None,
        })
    return out


def normalize_mediastack(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for a in rows:
        url = a.get("url") or ""
        pub = (a.get("source") or a.get("author") or "unknown").strip() or "unknown"
        title = clean_text(a.get("title") or "")
        summary = clean_text(a.get("description") or "")
        published = safe_parse_dt(a.get("published_at"))

        signals = {
            "category": a.get("category"),
            "country": a.get("country"),
            "language": a.get("language"),
            "image": a.get("image"),
        }

        rid = _make_id("mediastack", url)
        out.append({
            "id": rid,
            "platform": "mediastack",
            "source_type": "news",
            "publisher_or_author": pub,
            "url": url,
            "title": title or None,
            "summary": summary or None,
            "published_at": published,
            "ingested_at": now_iso(),
            "topics": None,
            "actors": None,
            "locations": None,
            "language": None,
            "is_editorial": None,
            "tags_json": None,
            "signals_json": json_dumps(signals),
            "raw_json": json_dumps(a),
            "content_hash": _content_hash(title, summary),
            "enriched_at": None,
            "enrich_model": None,
            "enrich_status": None,
            "enrich_error": None,
        })
    return out


def normalize_rss(feed_payload: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    out = []
    for feed_name, entries in feed_payload.items():
        for e in entries:
            url = e.get("link") or ""
            pub = feed_name.split("_")[0] if isinstance(feed_name, str) else "unknown"
            title = clean_text(e.get("title") or "")
            summary = clean_text(e.get("summary") or e.get("description") or "")
            published = safe_parse_dt(e.get("published") or e.get("updated"))

            signals = {
                "feed_name": e.get("_feed_name") or feed_name,
                "feed_url": e.get("_feed_url"),
            }

            rid = _make_id("rss", url)
            out.append({
                "id": rid,
                "platform": "rss",
                "source_type": "news",
                "publisher_or_author": pub,
                "url": url,
                "title": title or None,
                "summary": summary or None,
                "published_at": published,
                "ingested_at": now_iso(),
                "topics": None,
                "actors": None,
                "locations": None,
                "language": None,
                "is_editorial": None,
                "tags_json": None,
                "signals_json": json_dumps(signals),
                "raw_json": json_dumps(e),
                "content_hash": _content_hash(title, summary),
                "enriched_at": None,
                "enrich_model": None,
                "enrich_status": None,
                "enrich_error": None,
            })
    return out


def normalize_youtube(payload: Dict[str, List[Dict[str, Any]]], stats_map: Dict[str, Dict[str, int]] | None = None) -> List[Dict[str, Any]]:
    out = []
    stats_map = stats_map or {}
    for channel_name, entries in payload.items():
        for e in entries:
            url = e.get("link") or ""
            title = clean_text(e.get("title") or "")
            summary = clean_text(e.get("summary") or "")
            published = safe_parse_dt(e.get("published") or e.get("updated"))
            vid = e.get("video_id")
            metrics = stats_map.get(vid, {}) if vid else {}

            signals = {
                "channel_name": e.get("_channel_name") or channel_name,
                "channel_id": e.get("_channel_id"),
                "video_id": vid,
                "metrics": metrics,
            }

            rid = _make_id("youtube", url)
            out.append({
                "id": rid,
                "platform": "youtube",
                "source_type": "social",
                "publisher_or_author": str(channel_name),
                "url": url,
                "title": title or None,
                "summary": summary or None,
                "published_at": published,
                "ingested_at": now_iso(),
                "topics": None,
                "actors": None,
                "locations": None,
                "language": None,
                "is_editorial": None,
                "tags_json": None,
                "signals_json": json_dumps(signals),
                "raw_json": json_dumps(e),
                "content_hash": _content_hash(title, summary),
                "enriched_at": None,
                "enrich_model": None,
                "enrich_status": None,
                "enrich_error": None,
            })
    return out


def ingest_once(cfg: Dict[str, Any], store: Store, settings: Any, offline_fixtures: bool = False) -> Dict[str, Any]:
    """Fetch from enabled sources, normalize, upsert to DB."""
    store.init_db()
    raw_root = settings.data_dir / "raw"
    raw_root.mkdir(parents=True, exist_ok=True)

    inserted_total = 0
    updated_total = 0
    details: Dict[str, Any] = {}

    # --- GDELT ---
    gd_cfg = (cfg.get("sources", {}) or {}).get("gdelt", {}) or {}
    if gd_cfg.get("enabled"):
        if offline_fixtures:
            articles = json.loads((settings.repo_root / "tests/fixtures/gdelt_sample.json").read_text(encoding="utf-8"))
        else:
            articles = fetch_gdelt_artlist(
                query=str(gd_cfg.get("query", "Indonesia")),
                max_records=int(gd_cfg.get("max_records", 250)),
                sourcelang=str(gd_cfg.get("sourcelang", "ind")),
                timespan=str(gd_cfg.get("timespan") or "" ) or None,
                user_agent=settings.http_user_agent,
            )
        items = normalize_gdelt(articles)
        ins, upd = store.upsert_items(items)
        inserted_total += ins
        updated_total += upd
        details["gdelt"] = {"raw": len(articles), "inserted": ins, "updated": upd}

    # --- MediaStack ---
    ms_cfg = (cfg.get("sources", {}) or {}).get("mediastack", {}) or {}
    if ms_cfg.get("enabled"):
        if not settings.mediastack_key and not offline_fixtures:
            raise SystemExit("MEDIASTACK_KEY is required when sources.mediastack.enabled=true")
        if offline_fixtures:
            rows = json.loads((settings.repo_root / "tests/fixtures/mediastack_sample.json").read_text(encoding="utf-8"))
        else:
            rows = fetch_mediastack_news(
                access_key=settings.mediastack_key,
                countries=str(ms_cfg.get("countries", "id")),
                keywords=str(ms_cfg.get("keywords") or "") or None,
                categories=str(ms_cfg.get("categories") or "") or None,
                languages=str(ms_cfg.get("languages") or "") or None,
                limit=int(ms_cfg.get("limit", 100)),
                user_agent=settings.http_user_agent,
            )
        items = normalize_mediastack(rows)
        ins, upd = store.upsert_items(items)
        inserted_total += ins
        updated_total += upd
        details["mediastack"] = {"raw": len(rows), "inserted": ins, "updated": upd}

    # --- RSS ---
    rss_cfg = (cfg.get("sources", {}) or {}).get("rss", {}) or {}
    if rss_cfg.get("enabled"):
        if offline_fixtures:
            feed_payload = json.loads((settings.repo_root / "tests/fixtures/rss_sample.json").read_text(encoding="utf-8"))
        else:
            feeds = rss_cfg.get("feeds", {}) or {}
            feed_payload = fetch_rss_feeds(feeds, user_agent=settings.http_user_agent)
        items = normalize_rss(feed_payload)
        ins, upd = store.upsert_items(items)
        inserted_total += ins
        updated_total += upd
        details["rss"] = {"raw": sum(len(v) for v in feed_payload.values()), "inserted": ins, "updated": upd}

    # --- YouTube ---
    yt_cfg = (cfg.get("sources", {}) or {}).get("youtube", {}) or {}
    if yt_cfg.get("enabled"):
        if offline_fixtures:
            payload = json.loads((settings.repo_root / "tests/fixtures/youtube_sample.json").read_text(encoding="utf-8"))
            stats_map = {}
        else:
            channels = yt_cfg.get("channels", {}) or {}
            payload = fetch_youtube_channels(channels, user_agent=settings.http_user_agent)

            stats_map = {}
            if bool(yt_cfg.get("fetch_stats", False)) and settings.youtube_api_key:
                video_ids = []
                for _, entries in payload.items():
                    for e in entries:
                        vid = e.get("video_id")
                        if vid:
                            video_ids.append(vid)
                # de-dup
                video_ids = list(dict.fromkeys(video_ids))
                stats_map = fetch_youtube_video_stats(settings.youtube_api_key, video_ids)

        items = normalize_youtube(payload, stats_map=stats_map)
        ins, upd = store.upsert_items(items)
        inserted_total += ins
        updated_total += upd
        details["youtube"] = {"raw": sum(len(v) for v in payload.values()), "inserted": ins, "updated": upd}

    return {"inserted_total": inserted_total, "updated_total": updated_total, "details": details}
