from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..utils import clean_text, now_iso
from ..db.store import Store
from ..db.models import MediaItem
from .schema import Enrichment
from .gemini_client import GeminiClient, default_enrichment_schema


def _build_prompt(item: MediaItem, topics_allowed: List[str], actors_seed: List[str]) -> str:
    title = clean_text(item.title or "")
    summary = clean_text(item.summary or "")

    # Keep the prompt small (cheap model).
    # Provide allowed topics list, and a seed list of actors you care about.
    topics_str = ", ".join(topics_allowed)
    actors_str = ", ".join(actors_seed)

    return f"""You are an information extraction engine for media monitoring.
Return ONLY JSON that matches this schema:
{{
  "topics": [string],
  "actors": [string],
  "locations": [string],
  "language": string,
  "is_editorial": boolean
}}

Rules:
- topics MUST be chosen ONLY from this allowed list: [{topics_str}]. If none match, return empty list.
- actors: include organizations and public figures mentioned or strongly implied. Prefer canonical names if obvious.
- locations: Indonesian provinces/cities if mentioned (e.g., Jakarta, Jawa Barat, Konawe Utara). If none, empty list.
- language: use ISO code like "id" or "en". If uncertain, null.
- is_editorial: true if opinion/analysis/editorial, false if straight reporting; if unclear, null.

Metadata:
Platform: {item.platform}
Source type: {item.source_type}
Publisher/Author: {item.publisher_or_author}
URL: {item.url}

Title: {title}
Summary: {summary}
"""


def _fallback_keyword_enrichment(item: MediaItem, taxonomy: Dict[str, Any]) -> Enrichment:
    """No-key fallback (very rough)."""
    text = (clean_text(item.title or "") + " " + clean_text(item.summary or "")).lower()
    topics = []
    for name, spec in (taxonomy.get("topics", {}) or {}).items():
        kws = [k.lower() for k in (spec.get("keywords") or [])]
        locs = [l.lower() for l in (spec.get("locations") or [])]
        if kws and not any(k in text for k in kws):
            continue
        if locs and not any(l in text for l in locs):
            continue
        topics.append(name)

    actors_seed = taxonomy.get("actors", []) or []
    actors = [a for a in actors_seed if a.lower() in text]

    # Very naive: if contains many opinion markers
    is_editorial = None
    if any(x in text for x in ["opini", "menurut saya", "seharusnya", "kritik tajam"]):
        is_editorial = True

    # language guess
    language = "id" if any(w in text for w in ["yang","dan","tidak","dengan"]) else None
    return Enrichment(topics=topics, actors=actors, locations=[], language=language, is_editorial=is_editorial)


def enrich_pending(
    store: Store,
    taxonomy: Dict[str, Any],
    gemini_api_key: Optional[str],
    gemini_model: str,
    batch_size: int = 20,
    max_retries: int = 2,
) -> Dict[str, int]:
    """Enrich items where enriched_at is NULL."""
    pending = store.list_unenriched(limit=batch_size)
    if not pending:
        return {"pending": 0, "enriched_ok": 0, "enriched_error": 0, "skipped": 0}

    topics_allowed = list((taxonomy.get("topics", {}) or {}).keys())
    actors_seed = taxonomy.get("actors", []) or []

    schema = default_enrichment_schema()

    client = None
    if gemini_api_key:
        client = GeminiClient(api_key=gemini_api_key, model=gemini_model)

    ok = 0
    err = 0
    skipped = 0

    for it in pending:
        # If no gemini key, fallback to cheap keyword tagging
        if client is None:
            enr = _fallback_keyword_enrichment(it, taxonomy)
            store.update_enrichment(
                item_id=it.id,
                topics=enr.topics,
                actors=enr.actors,
                locations=enr.locations,
                language=enr.language,
                is_editorial=enr.is_editorial,
                tags_json=enr.model_dump(),
                model="fallback_keyword",
                status="skipped",
                error="GEMINI_API_KEY not set; used fallback keyword enrichment.",
                enriched_at=now_iso(),
            )
            skipped += 1
            continue

        prompt = _build_prompt(it, topics_allowed, actors_seed)

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                enr = client.enrich(prompt=prompt, response_schema=schema, temperature=0.1)
                store.update_enrichment(
                    item_id=it.id,
                    topics=enr.topics,
                    actors=enr.actors,
                    locations=enr.locations,
                    language=enr.language,
                    is_editorial=enr.is_editorial,
                    tags_json=enr.model_dump(),
                    model=gemini_model,
                    status="ok",
                    error=None,
                    enriched_at=now_iso(),
                )
                ok += 1
                last_error = None
                break
            except Exception as e:
                last_error = str(e)
        if last_error:
            store.update_enrichment(
                item_id=it.id,
                topics=[],
                actors=[],
                locations=[],
                language=None,
                is_editorial=None,
                tags_json={},
                model=gemini_model,
                status="error",
                error=last_error,
                enriched_at=now_iso(),
            )
            err += 1

    return {"pending": len(pending), "enriched_ok": ok, "enriched_error": err, "skipped": skipped}
