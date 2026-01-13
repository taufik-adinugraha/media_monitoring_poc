from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import json

from media_monitor.settings import load_settings
from media_monitor.sources.mediastack import fetch_mediastack_sources


def main():
    ap = argparse.ArgumentParser(description="List MediaStack sources (requires MEDIASTACK_KEY).")
    ap.add_argument("--search", type=str, default="")
    ap.add_argument("--countries", type=str, default="id")
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--offset", type=int, default=0)
    args = ap.parse_args()

    settings = load_settings()
    if not settings.mediastack_key:
        raise SystemExit("MEDIASTACK_KEY env var required.")

    payload = fetch_mediastack_sources(
        access_key=settings.mediastack_key,
        search=args.search or None,
        countries=args.countries or None,
        limit=args.limit,
        offset=args.offset,
        user_agent=settings.http_user_agent,
    )

    print(json.dumps(payload, ensure_ascii=False, indent=2)[:5000])


if __name__ == "__main__":
    main()
