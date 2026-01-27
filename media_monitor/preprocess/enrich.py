from __future__ import annotations

from typing import Any, Dict, List, Optional

from .fetch_content import fetch_article_text

from ..utils import clean_text, now_iso
from ..db.store import Store
from ..db.models import MediaItem
from .schema import Enrichment
from .gemini_client import GeminiClient, default_enrichment_schema


MAX_CONTENT_CHARS = 4000  # keep Gemini cheap & safe


def _build_prompt(
    item: MediaItem,
    topic_specs: Dict[str, Dict[str, Any]],
    actors_seed: List[str],
    content_text: Optional[str],
) -> str:
    title = clean_text(item.title or "")
    summary = clean_text(item.summary or "")
    content = clean_text(content_text or "")[:MAX_CONTENT_CHARS]

    # Build taxonomy block with descriptions + keywords
    topic_blocks = []
    allowed_topic_names = []

    for topic_name, spec in topic_specs.items():
        allowed_topic_names.append(topic_name)

        desc = clean_text(spec.get("description", "")).strip()
        keywords = spec.get("keywords") or []
        kw_str = ", ".join(keywords)

        block = f"""
- {topic_name}
  Description:
  {desc}
"""
        if kw_str:
            block += f"  Indicative keywords: {kw_str}\n"

        topic_blocks.append(block.strip())

    topics_allowed_str = ", ".join(allowed_topic_names)
    actors_str = ", ".join(actors_seed)

    return f"""You are an information extraction and classification engine for media monitoring.

Your task is to analyze the article and return structured metadata.

IMPORTANT RULES FOR TOPICS:
- Topics are semantic concepts defined by their descriptions.
- Keywords are ONLY indicative signals and must NOT be used alone.
- Assign a topic ONLY if the article clearly fits the topic description.
- One article MAY belong to multiple topics.
- Topics MUST be chosen ONLY from this allowed list: [{topics_allowed_str}].
- If none apply, return an empty list.

ACTOR RULES:
- Actors include public figures, government bodies, political parties, companies, and organizations.
- Use full names where possible.
- If an actor is implied but not explicitly named, include it only if highly confident.

OUTPUT FORMAT:
Return ONLY valid JSON that matches this schema:
{{
  "topics": [string],
  "actors": [string],
  "locations": [string],
  "language": string | null,
  "is_editorial": boolean | null,
  "sentiment": "positive" | "negative" | "neutral",
  "actor_quotes": [
    {{
      "actor": string,
      "quote": string,
      "context": string
    }}
  ]
}}

NOTES:
- Extract actor_quotes ONLY if there are direct quotations (verbatim).
- Do NOT paraphrase quotes.
- If no direct quotes exist, return an empty list for actor_quotes.

TAXONOMY:
{chr(10).join(topic_blocks)}

SEED ACTORS (for reference only, not exhaustive):
{actors_str}

ARTICLE METADATA:
Platform: {item.platform}
Source type: {item.source_type}
Publisher/Author: {item.publisher_or_author}
URL: {item.url}

ARTICLE CONTENT:
Title: {title}

Summary:
{summary}

Full Content:
{content}
"""


def _fallback_keyword_enrichment(
    item: MediaItem,
    taxonomy: Dict[str, Any],
) -> Enrichment:
    text = (
        clean_text(item.title or "")
        + " "
        + clean_text(item.summary or "")
    ).lower()

    topics: List[str] = []
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

    is_editorial = None
    if any(x in text for x in ["opini", "menurut saya", "seharusnya", "kritik"]):
        is_editorial = True

    sentiment = "neutral"
    if any(x in text for x in ["positif", "baik", "bagus", "apresiasi"]):
        sentiment = "positive"
    elif any(x in text for x in ["negatif", "buruk", "jelek", "korupsi", "skandal"]):
        sentiment = "negative"

    language = "id" if any(w in text for w in ["yang", "dan", "tidak", "dengan"]) else None

    return Enrichment(
        topics=topics,
        actors=actors,
        locations=[],
        language=language,
        is_editorial=is_editorial,
        sentiment=sentiment,
    )


def enrich_pending(
    store: Store,
    taxonomy: Dict[str, Any],
    gemini_api_key: Optional[str],
    gemini_model: str,
    batch_size: int = 20,
    max_retries: int = 2,
) -> Dict[str, int]:
    pending = store.list_unenriched(limit=batch_size)
    if not pending:
        return {"pending": 0, "enriched_ok": 0, "enriched_error": 0, "skipped": 0}

    topic_specs = taxonomy.get("topics", {}) or {}
    actors_seed = taxonomy.get("actors", []) or []
    schema = default_enrichment_schema()

    client = (
        GeminiClient(api_key=gemini_api_key, model=gemini_model)
        if gemini_api_key
        else None
    )

    ok = err = skipped = 0

    for it in pending:
        content_text = getattr(it, "content_text", None)

        if not content_text:
            content = fetch_article_text(it.url)
            if content:
                store.update_content(
                    item_id=it.id,
                    content_text=content,
                    fetched_at=now_iso(),
                    status="ok",
                )
                content_text = content


        # ---- fallback path ----
        if client is None:
            enr = _fallback_keyword_enrichment(it, taxonomy)
            store.update_enrichment(
                item_id=it.id,
                topics=enr.topics,
                actors=enr.actors,
                locations=enr.locations,
                language=enr.language,
                is_editorial=enr.is_editorial,
                sentiment=enr.sentiment,
                tags_json=enr.model_dump(),
                model="fallback_keyword",
                status="ok",
                error=None,
                enriched_at=now_iso(),
            )
            skipped += 1
            continue

        prompt = _build_prompt(it, topic_specs, actors_seed, content_text)

        last_error = None
        for _ in range(max_retries + 1):
            try:
                enr = client.enrich(
                    prompt=prompt,
                    response_schema=schema,
                    temperature=0.1,
                )

                store.update_enrichment(
                    item_id=it.id,
                    topics=enr.topics,
                    actors=enr.actors,
                    locations=enr.locations,
                    language=enr.language,
                    is_editorial=enr.is_editorial,
                    sentiment=enr.sentiment,
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
                sentiment=None,
                tags_json={},
                model=gemini_model,
                status="error",
                error=last_error,
                enriched_at=now_iso(),
            )
            err += 1

    return {
        "pending": len(pending),
        "enriched_ok": ok,
        "enriched_error": err,
        "skipped": skipped,
    }
