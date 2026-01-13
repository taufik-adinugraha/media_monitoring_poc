from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests

from ..utils import parse_gdelt_seendate


GDELT_DOC_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"


def _wrap_or_terms(query: str) -> str:
    # GDELT requires OR'd terms to be wrapped in parentheses.
    # If the query already contains parentheses, don't overwrap.
    q = query.strip()
    if " OR " in q and "(" not in q:
        return f"({q})"
    return q


def fetch_gdelt_artlist(
    query: str,
    max_records: int = 250,
    sourcelang: str = "ind",
    timespan: Optional[str] = None,
    timeout_s: int = 30,
    user_agent: str | None = None,
) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {
        "query": _wrap_or_terms(query),
        "mode": "artlist",
        "format": "json",
        "maxrecords": max_records,
        "sourcelang": sourcelang,
    }
    if timespan:
        params["timespan"] = timespan

    headers = {}
    if user_agent:
        headers["User-Agent"] = user_agent

    r = requests.get(GDELT_DOC_ENDPOINT, params=params, headers=headers, timeout=timeout_s)

    # GDELT sometimes returns HTML error pages; handle gracefully.
    ctype = (r.headers.get("Content-Type") or "").lower()
    if "application/json" not in ctype:
        preview = (r.text or "")[:200].replace("\n", " ")
        raise ValueError(f"GDELT returned non-JSON response. Content-Type={ctype}. Preview={preview}")

    r.raise_for_status()
    payload = r.json()
    return payload.get("articles", []) or []
