from __future__ import annotations

import sys
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse

from media_monitor.settings import load_settings
from media_monitor.config import load_config
from media_monitor.db.store import Store
from media_monitor.analytics.sonar_client import SonarClient
from media_monitor.analytics.report import (
    render_markdown_report,
    select_urls_for_deep_dive,
)
from media_monitor.utils import json_loads


# -----------------------------
# Time helpers
# -----------------------------
def _since_iso(days: int) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return dt.isoformat()


def _since_iso_prev_window(days: int) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=2 * days)
    return dt.isoformat()


# -----------------------------
# Markdown table helper
# -----------------------------
def md_table(headers: List[str], rows: List[List[Any]], align_right: Optional[set] = None) -> str:
    align_right = align_right or set()
    header_line = "| " + " | ".join(headers) + " |"
    sep_cells = []
    for h in headers:
        sep_cells.append("---:" if h in align_right else "---")
    sep_line = "| " + " | ".join(sep_cells) + " |"
    body = []
    for r in rows:
        body.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join([header_line, sep_line] + body)


def pct(x: float) -> str:
    return f"{x*100:.1f}%"


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _strip_think_blocks(s: str) -> str:
    return _THINK_RE.sub("", s).strip()


def get_domain(url: str) -> str:
    try:
        return url.split("//", 1)[-1].split("/", 1)[0].lower()
    except Exception:
        return "unknown"


def safe_day(iso_str: Optional[str]) -> str:
    if not iso_str:
        return "unknown"
    try:
        s = iso_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt.date().isoformat()
    except Exception:
        return "unknown"


def uniq_preserve(xs: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in xs:
        if not x:
            continue
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


# -----------------------------
# Health / Risk heuristic
# -----------------------------
def compute_health_and_risk(n_mentions: int, n_prev_mentions: int, critical_issue_count: int) -> Tuple[int, str, str]:
    delta = 0.0
    if n_prev_mentions > 0:
        delta = (n_mentions - n_prev_mentions) / float(n_prev_mentions)

    if delta > 0.10:
        reputation = "Improving"
    elif delta < -0.10:
        reputation = "Declining"
    else:
        reputation = "Stable"

    risk_points = 0
    risk_points += 2 if critical_issue_count >= 2 else (1 if critical_issue_count == 1 else 0)
    if delta > 0.50:
        risk_points += 1

    if risk_points >= 3:
        risk = "High"
    elif risk_points == 2:
        risk = "Medium"
    else:
        risk = "Low"

    health = 80
    health -= 10 * critical_issue_count
    if delta > 0.50:
        health -= 5
    if delta < -0.30:
        health -= 3
    return int(clamp(health, 0, 100)), reputation, risk


# -----------------------------
# Sonar Deep Research infographic prompt
# -----------------------------
def build_infographic_prompt(
    title: str,
    topic: str,
    time_window: str,
    seed_urls: List[str],
    language: str = "id",
) -> str:
    url_block = "\n".join([f"- {u}" for u in seed_urls])

    return (
        f"You are a senior media intelligence analyst. Write in {language}.\n\n"
        f"GOAL:\n"
        f"- Produce an Indonesian infographic-style media monitoring brief (Markdown text).\n"
        f"- The seed URLs below are starting points; you MAY search and use additional related credible sources.\n"
        f"- Every key claim must be supported by sources and citations.\n\n"
        f"RULES:\n"
        f"- Do NOT invent numbers, names, dates, or quotes.\n"
        f"- If a numeric detail is not available in sources, write: 'Belum tersedia dari sumber'.\n"
        f"- If sources disagree, mention the discrepancy.\n"
        f"- Output Markdown only. Do not output JSON. Do not output <think> blocks.\n\n"
        f"TOPIC:\n- {topic}\n\n"
        f"TIME WINDOW:\n- {time_window}\n\n"
        f"OUTPUT STRUCTURE (must follow):\n"
        f"🌿 **INFOGRAFIS: {title}**\n\n"
        f"📍 **RINGKASAN SITUASI** (1 paragraf)\n\n"
        f"📊 **DATA & FAKTA TERKINI**\n"
        f"- Bullet points with numbers/dates/locations if available\n"
        f"- Breakdown per provinsi/kota bila ada\n\n"
        f"👤 **AKTOR KUNCI & POSISI MEREKA**\n"
        f"- Who did what; include framing differences if present\n\n"
        f"⚖️ **KEJADIAN / KEBIJAKAN / TINDAKAN HUKUM (urut waktu)**\n"
        f"- Mini timeline (tanggal → kejadian)\n\n"
        f"🎯 **KONTROVERSI UTAMA & RISIKO REPUTASI**\n"
        f"- 3–8 bullets; who criticized/who supported; why it matters\n\n"
        f"✅ **PELUANG NARASI (PR)**\n"
        f"- 3–6 safe, fact-grounded narrative angles\n\n"
        f"📋 **REKOMENDASI STRATEGIS (PR)**\n"
        f"- Jangka pendek (1–2 minggu)\n"
        f"- Jangka menengah (1–3 bulan)\n"
        f"- Jangka panjang (3–12 bulan)\n\n"
        f"🧾 **DAFTAR SUMBER**\n"
        f"- List all URLs you used (seed + any discovered)\n\n"
        f"SEED URLS:\n{url_block}\n"
    )


def main():
    ap = argparse.ArgumentParser(description="Generate report from DB; deep research infographic + tables.")
    ap.add_argument("--config", type=str, default="monitor_config.json")
    ap.add_argument("--since-days", type=int, default=7)
    ap.add_argument("--topics", type=str, default="", help="Comma-separated topics to generate infographics (default: all configured).")
    ap.add_argument("--out", type=str, default="reports/report_latest.md")
    args = ap.parse_args()

    settings = load_settings()
    cfg = load_config(Path(args.config))
    store = Store(settings.db_url)
    store.init_db()

    since_iso = _since_iso(args.since_days)
    since_iso_prev = _since_iso_prev_window(args.since_days)

    # Fetch 2 windows and split (no until_iso dependency)
    items_2w = store.query_items(since_iso=since_iso_prev, limit=5000)
    items = [it for it in items_2w if (it.published_at or it.ingested_at) >= since_iso]
    prev_items = [it for it in items_2w if (it.published_at or it.ingested_at) < since_iso]

    n_mentions = len(items)
    n_prev_mentions = len(prev_items)
    mention_delta = (n_mentions - n_prev_mentions) / float(n_prev_mentions) if n_prev_mentions else 0.0

    by_pub = Counter()
    by_domain = Counter()
    by_topic = Counter()
    by_day = Counter()
    actor_counts = Counter()

    # Sentiment from DB (single column)
    sent_bucket = Counter()
    pub_sent_bucket = defaultdict(lambda: Counter())
    topic_sent_bucket = defaultdict(lambda: Counter())
    day_sent_bucket = defaultdict(lambda: Counter())

    for it in items:
        pub = getattr(it, "publisher_or_author", None) or "unknown"
        url = getattr(it, "url", None) or ""
        dom = get_domain(url) if url else "unknown"
        by_pub[pub] += 1
        by_domain[dom] += 1

        topics = []
        try:
            topics = json_loads(it.topics) if it.topics else []
        except Exception:
            topics = []

        actors = []
        try:
            actors = json_loads(it.actors) if it.actors else []
        except Exception:
            actors = []

        for t in topics:
            by_topic[t] += 1
        for a in actors:
            actor_counts[a] += 1

        day = safe_day(getattr(it, "published_at", None) or getattr(it, "ingested_at", None))
        by_day[day] += 1

        # sentiment from DB column
        s = (getattr(it, "sentiment", None) or "").strip().lower()
        if s in ("positive", "neutral", "negative"):
            sent_bucket[s] += 1
            pub_sent_bucket[pub][s] += 1
            day_sent_bucket[day][s] += 1
            for t in topics:
                topic_sent_bucket[t][s] += 1

    report_cfg = cfg.get("report", {}) or {}
    sonar_model = str(report_cfg.get("sonar_model") or settings.sonar_model)
    max_urls = int(report_cfg.get("max_urls_per_topic", 12))
    briefing_language = str(report_cfg.get("briefing_language", "id"))

    critical_topics = set((report_cfg.get("critical_topics") or []))
    critical_issue_count = 0
    if critical_topics:
        critical_issue_count = sum(by_topic.get(t, 0) > 0 for t in critical_topics)

    health_score, reputation, risk = compute_health_and_risk(n_mentions, n_prev_mentions, critical_issue_count)

    # topics selection
    topics_cfg = (cfg.get("taxonomy", {}) or {}).get("topics", {}) or {}
    topics_all = list(topics_cfg.keys())
    if args.topics.strip():
        requested = [t.strip() for t in args.topics.split(",") if t.strip()]
        topics_for_brief = [t for t in requested if (not topics_cfg) or (t in topics_cfg)]
        if not topics_for_brief:
            topics_for_brief = requested
    else:
        topics_for_brief = topics_all if topics_all else ["general"]

    infographic_sections = []
    if settings.sonar_api_key:

        sonar_timeout_s = int(report_cfg.get("sonar_timeout_s", 180))
        sonar_retries = int(report_cfg.get("sonar_retries", 3))
        sonar_backoff_s = int(report_cfg.get("sonar_backoff_s", 8))
        sonar_max_tokens = int(report_cfg.get("sonar_max_tokens", 8000))

        client = SonarClient(
            api_key=settings.sonar_api_key,
            model=sonar_model,
            timeout_s=sonar_timeout_s,
            retries=sonar_retries,
            backoff_s=sonar_backoff_s
        )

        time_window_str = f"{args.since_days} hari terakhir"

        for t in topics_for_brief:
            seed_urls = select_urls_for_deep_dive(items, t, max_urls=max_urls)
            seed_urls = [u for u in seed_urls if u]
            if not seed_urls:
                continue

            title = f"Update {t.replace('_', ' ').title()}"
            prompt = build_infographic_prompt(
                title=title,
                topic=t,
                time_window=time_window_str,
                seed_urls=seed_urls,
                language=briefing_language,
            )

            resp = client.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=sonar_max_tokens,
                search_recency_filter="week" if args.since_days <= 7 else "month",
                search_domain_filter=None,  # allow discovery
            )
            text, citations = client.extract_text_and_citations(resp)
            text = _strip_think_blocks(text)
            infographic_sections.append((t, text, citations))

    # Build report
    lines: List[str] = []
    lines.append("# Media Monitoring Report")
    lines.append("")
    lines.append(f"Time window: last **{args.since_days} days** (since `{since_iso}`)")
    lines.append("")

    lines.append("## Health & Risk Overview")
    lines.append("")
    lines.append(
        f"- **Health Score:** {health_score}\n"
        f"- **Reputation:** {reputation}\n"
        f"- **Risk:** {risk}\n"
        f"- **Alerts:** {critical_issue_count} critical issue(s)"
    )
    lines.append("")

    lines.append("## Key Metrics")
    lines.append("")
    lines.append(md_table(
        headers=["Metric", "Value"],
        rows=[
            ["Mentions", f"{n_mentions} ({'+' if mention_delta>=0 else ''}{pct(mention_delta)}) vs prev window"],
            ["Top Issue (by topic frequency)", (by_topic.most_common(1)[0][0] if by_topic else "coverage")],
            ["Top Publisher", (by_pub.most_common(1)[0][0] if by_pub else "unknown")],
        ],
    ))
    lines.append("")

    lines.append("## Top Publishers")
    lines.append("")
    lines.append(md_table(
        headers=["Publisher", "Articles"],
        rows=[[p, n] for p, n in by_pub.most_common(15)],
        align_right={"Articles"},
    ))
    lines.append("")

    lines.append("## Topic Counts")
    lines.append("")
    if by_topic:
        lines.append(md_table(
            headers=["Topic", "Articles"],
            rows=[[t, n] for t, n in by_topic.most_common(30)],
            align_right={"Articles"},
        ))
    else:
        lines.append("_No topic tags found (check enrichment/taxonomy)._")
    lines.append("")

    lines.append("## Coverage Over Time")
    lines.append("")
    days_sorted = sorted([d for d in by_day.keys() if d != "unknown"])
    lines.append(md_table(
        headers=["Date", "Mentions"],
        rows=[[d, by_day[d]] for d in days_sorted[-31:]],
        align_right={"Mentions"},
    ))
    lines.append("")

    lines.append("## Sentiment (from DB column)")
    lines.append("")
    total_scored = sum(sent_bucket.values())
    if total_scored == 0:
        lines.append("_No sentiment present in `media_items.sentiment` for this window._")
        lines.append("")
    else:
        lines.append(md_table(
            headers=["Label", "Count", "Share"],
            rows=[
                ["positive", sent_bucket.get("positive", 0), pct(sent_bucket.get("positive", 0) / total_scored)],
                ["neutral", sent_bucket.get("neutral", 0), pct(sent_bucket.get("neutral", 0) / total_scored)],
                ["negative", sent_bucket.get("negative", 0), pct(sent_bucket.get("negative", 0) / total_scored)],
            ],
            align_right={"Count", "Share"},
        ))
        lines.append("")

        # Sentiment by publisher (top 15 pubs)
        pub_rows = []
        for p, _n in by_pub.most_common(15):
            c = pub_sent_bucket.get(p, {})
            denom = sum(c.values())
            if denom == 0:
                continue
            pub_rows.append([p, c.get("positive", 0), c.get("neutral", 0), c.get("negative", 0), denom])
        if pub_rows:
            lines.append("### Sentiment by publisher (counts)")
            lines.append("")
            lines.append(md_table(
                headers=["Publisher", "Positive", "Neutral", "Negative", "N scored"],
                rows=pub_rows,
                align_right={"Positive", "Neutral", "Negative", "N scored"},
            ))
            lines.append("")

        # Topic x sentiment (top 15 topics)
        if topic_sent_bucket:
            heat_rows = []
            for t, _n in by_topic.most_common(15):
                c = topic_sent_bucket.get(t, {})
                heat_rows.append([t, c.get("positive", 0), c.get("neutral", 0), c.get("negative", 0)])
            lines.append("### Topic × sentiment (counts)")
            lines.append("")
            lines.append(md_table(
                headers=["Topic", "Positive", "Neutral", "Negative"],
                rows=heat_rows,
                align_right={"Positive", "Neutral", "Negative"},
            ))
            lines.append("")

        # Sentiment over time
        srows = []
        for d in days_sorted[-31:]:
            c = day_sent_bucket.get(d, {})
            denom = sum(c.values())
            srows.append([d, c.get("positive", 0), c.get("neutral", 0), c.get("negative", 0), denom])
        lines.append("### Sentiment over time (counts)")
        lines.append("")
        lines.append(md_table(
            headers=["Date", "Positive", "Neutral", "Negative", "N scored"],
            rows=srows,
            align_right={"Positive", "Neutral", "Negative", "N scored"},
        ))
        lines.append("")

    lines.append("## Top Domains")
    lines.append("")
    lines.append(md_table(
        headers=["Domain", "Articles"],
        rows=[[d, n] for d, n in by_domain.most_common(15)],
        align_right={"Articles"},
    ))
    lines.append("")

    lines.append("## Top Actors (from enrichment)")
    lines.append("")
    if actor_counts:
        lines.append(md_table(
            headers=["Actor", "Mentions"],
            rows=[[a, n] for a, n in actor_counts.most_common(25)],
            align_right={"Mentions"},
        ))
    else:
        lines.append("_No actors detected yet._")
    lines.append("")

    # Infographic briefings
    if infographic_sections:
        lines.append("---")
        lines.append("")
        lines.append("# Infographic Briefings (Sonar Deep Research)")
        lines.append("")
        for t, text, citations in infographic_sections:
            lines.append(f"## {t}")
            lines.append("")
            lines.append(text)
            lines.append("")
            if citations:
                lines.append("_Citations:_")
                lines.extend([f"- {c}" for c in citations])
                lines.append("")
    else:
        if not settings.sonar_api_key:
            lines.append("---")
            lines.append("")
            lines.append("_[INFO] SONAR_API_KEY not set; infographic sections were skipped._")
            lines.append("")

    # Appendix
    lines.append("---")
    lines.append("")
    lines.append("# Appendix: Item Listing Summary")
    lines.append("")
    lines.append(render_markdown_report(items, deep_sections=[]))

    report_md = "\n".join(lines)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report_md, encoding="utf-8")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out2 = out.parent / f"report_{ts}.md"
    out2.write_text(report_md, encoding="utf-8")

    print("Wrote:", out)
    print("Wrote:", out2)


if __name__ == "__main__":
    main()
