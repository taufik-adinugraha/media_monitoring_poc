from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests


MEDIASTACK_NEWS_ENDPOINT_HTTPS = "https://api.mediastack.com/v1/news"
MEDIASTACK_NEWS_ENDPOINT_HTTP = "http://api.mediastack.com/v1/news"
MEDIASTACK_SOURCES_ENDPOINT_HTTPS = "https://api.mediastack.com/v1/sources"
MEDIASTACK_SOURCES_ENDPOINT_HTTP = "http://api.mediastack.com/v1/sources"

# Based on MediaStack docs: supported language codes are limited and do not include 'id' (Indonesian).
SUPPORTED_LANGUAGES = {"ar","de","en","es","fr","he","it","nl","no","pt","ru","se","zh"}


def _clean_languages(languages: Optional[str]) -> Optional[str]:
    if not languages:
        return None
    parts = [p.strip() for p in languages.split(",") if p.strip()]
    parts = [p for p in parts if p.lstrip("-") in SUPPORTED_LANGUAGES]
    if not parts:
        return None
    return ",".join(parts)


def fetch_mediastack_news(
    access_key: str,
    countries: str = "id",
    keywords: Optional[str] = None,
    categories: Optional[str] = None,
    languages: Optional[str] = None,
    limit: int = 100,
    sort: str = "published_desc",
    timeout_s: int = 30,
    user_agent: str | None = None,
    allow_http_fallback: bool = True,
) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {
        "access_key": access_key,
        "countries": countries,
        "limit": limit,
        "sort": sort,
    }
    if keywords:
        params["keywords"] = keywords
    if categories:
        params["categories"] = categories

    languages_clean = _clean_languages(languages)
    if languages and not languages_clean:
        # user asked for unsupported languages -> drop silently but mark in response
        pass
    if languages_clean:
        params["languages"] = languages_clean

    headers = {}
    if user_agent:
        headers["User-Agent"] = user_agent

    def _do(url: str) -> requests.Response:
        return requests.get(url, params=params, headers=headers, timeout=timeout_s)

    r = _do(MEDIASTACK_NEWS_ENDPOINT_HTTPS)

    # If HTTPS is restricted or errors, try HTTP (some plans historically restricted HTTPS).
    if allow_http_fallback and (r.status_code in (401,403,404,422) or r.status_code >= 500):
        try:
            j = r.json()
            if isinstance(j, dict) and j.get("error", {}).get("code") == "https_access_restricted":
                r = _do(MEDIASTACK_NEWS_ENDPOINT_HTTP)
        except Exception:
            # if non-json or something else, still optionally fallback for resilience
            r = _do(MEDIASTACK_NEWS_ENDPOINT_HTTP)

    # MediaStack returns JSON errors with 200 sometimes; handle both.
    try:
        payload = r.json()
    except Exception:
        r.raise_for_status()
        return []

    if isinstance(payload, dict) and payload.get("error"):
        # surface error context in an exception for logs
        err = payload.get("error", {})
        raise ValueError(f"MediaStack error: {err.get('code')} {err.get('message')} context={err.get('context')}")

    r.raise_for_status()
    return payload.get("data", []) or []


def fetch_mediastack_sources(
    access_key: str,
    search: Optional[str] = None,
    countries: Optional[str] = None,
    languages: Optional[str] = None,
    categories: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    timeout_s: int = 30,
    user_agent: str | None = None,
    allow_http_fallback: bool = True,
) -> Dict[str, Any]:
    params: Dict[str, Any] = {"access_key": access_key, "limit": limit, "offset": offset}
    if search:
        params["search"] = search
    if countries:
        params["countries"] = countries
    if categories:
        params["categories"] = categories
    languages_clean = _clean_languages(languages)
    if languages_clean:
        params["languages"] = languages_clean

    headers = {}
    if user_agent:
        headers["User-Agent"] = user_agent

    def _do(url: str) -> requests.Response:
        return requests.get(url, params=params, headers=headers, timeout=timeout_s)

    r = _do(MEDIASTACK_SOURCES_ENDPOINT_HTTPS)
    if allow_http_fallback and r.status_code >= 400:
        r = _do(MEDIASTACK_SOURCES_ENDPOINT_HTTP)

    payload = r.json()
    if isinstance(payload, dict) and payload.get("error"):
        err = payload.get("error", {})
        raise ValueError(f"MediaStack error: {err.get('code')} {err.get('message')} context={err.get('context')}")
    return payload
