from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from ..db.models import MediaItem
from ..utils import clean_text, json_loads


def _topics(item: MediaItem) -> List[str]:
    try:
        return json_loads(item.topics) if item.topics else []
    except Exception:
        return []


def build_summary_tables(items: List[MediaItem]) -> Dict[str, pd.DataFrame]:
    by_platform = Counter([i.platform for i in items])
    by_pub = Counter([i.publisher_or_author or "unknown" for i in items])

    # topic counts (using enriched topics if available)
    topic_c = Counter()
    for it in items:
        for t in _topics(it):
            topic_c[t] += 1

    df_platform = pd.DataFrame(by_platform.most_common(), columns=["Platform", "Items"]).set_index("Platform")
    df_pub = pd.DataFrame(by_pub.most_common(20), columns=["Publisher/Author", "Items"]).set_index("Publisher/Author")
    df_topic = pd.DataFrame(topic_c.most_common(30), columns=["Topic", "Items"]).set_index("Topic") if topic_c else pd.DataFrame()

    return {"by_platform": df_platform, "top_publishers": df_pub, "topic_counts": df_topic}


def select_urls_for_deep_dive(
    items: List[MediaItem],
    topic: str,
    max_urls: int = 8,
) -> List[str]:
    # prefer recent items with the topic and a URL
    selected = []
    for it in sorted(items, key=lambda x: (x.published_at or ""), reverse=True):
        if topic not in _topics(it):
            continue
        if not it.url:
            continue
        selected.append(it.url)
        if len(selected) >= max_urls:
            break
    # de-dup preserve order
    out = []
    seen = set()
    for u in selected:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def render_markdown_report(
    items: List[MediaItem],
    deep_sections: Optional[List[Tuple[str, str, List[str]]]] = None,
) -> str:
    # deep_sections: list of (topic, sonar_text, citations)
    tables = build_summary_tables(items)

    lines: List[str] = []
    lines.append("# Media Monitoring Report")
    lines.append("")
    lines.append(f"- Total items: **{len(items)}**")
    lines.append("")

    lines.append("## Volume by platform")
    lines.append("")
    lines.append(tables["by_platform"].to_markdown())
    lines.append("")

    lines.append("## Top publishers / authors")
    lines.append("")
    lines.append(tables["top_publishers"].to_markdown())
    lines.append("")

    lines.append("## Topic counts (enriched)")
    lines.append("")
    if not tables["topic_counts"].empty:
        lines.append(tables["topic_counts"].to_markdown())
    else:
        lines.append("_No enriched topic tags found yet (or enrichment not enabled)._")
    lines.append("")

    if deep_sections:
        lines.append("## Deep dive (Sonar)")
        lines.append("")
        for topic, text, citations in deep_sections:
            lines.append(f"### {topic}")
            lines.append("")
            lines.append(text.strip() or "_No Sonar output._")
            if citations:
                lines.append("")
                lines.append("**Citations (from Sonar):**")
                for c in citations[:20]:
                    lines.append(f"- {c}")
            lines.append("")

    return "\n".join(lines)
