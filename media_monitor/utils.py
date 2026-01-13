from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dateutil import parser as dtparser


_TAG_RE = re.compile(r"<[^>]+>")
_URL_RE = re.compile(r"https?://\S+")
_WS_RE = re.compile(r"\s+")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def safe_parse_dt(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    try:
        return dtparser.parse(s).astimezone(timezone.utc).isoformat()
    except Exception:
        return None


def parse_gdelt_seendate(seendate: Optional[str]) -> Optional[str]:
    # GDELT seendate often looks like: 20251230T070000Z
    if not seendate:
        return None
    try:
        # Insert separators and parse as UTC
        # 20251230T070000Z -> 2025-12-30T07:00:00Z
        s = seendate.replace("Z", "+00:00")
        if "T" in s and len(s) >= 15:
            dt = dtparser.parse(s)
            return dt.astimezone(timezone.utc).isoformat()
        return safe_parse_dt(seendate)
    except Exception:
        return None


def clean_text(text: Optional[str]) -> str:
    if not text:
        return ""
    t = html.unescape(text)
    t = _TAG_RE.sub(" ", t)
    t = _URL_RE.sub(" ", t)
    t = _WS_RE.sub(" ", t).strip()
    return t


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def json_loads(s: str) -> Any:
    return json.loads(s)


def guess_publisher_from_domain(domain: Optional[str]) -> str:
    if not domain:
        return "unknown"
    d = domain.lower()
    # Minimal mapping; extend as needed
    mapping = {
        "kompas.com": "kompas",
        "nasional.kompas.com": "kompas",
        "tempo.co": "tempo",
        "nasional.tempo.co": "tempo",
        "antaranews.com": "antara",
        "mediaindonesia.com": "mediaindonesia",
        "detik.com": "detik",
        "cnnindonesia.com": "cnnindonesia",
        "cnbcindonesia.com": "cnbcindonesia",
    }
    for k, v in mapping.items():
        if d == k or d.endswith("." + k):
            return v
    # fallback: domain root
    return d.split(".")[-2] if "." in d else d
