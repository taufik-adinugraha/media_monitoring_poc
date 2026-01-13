from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

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


def _since_iso(days: int) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return dt.isoformat()


def main():
    ap = argparse.ArgumentParser(description="Generate report from DB; optional deep dive with Sonar.")
    ap.add_argument("--config", type=str, default="monitor_config.json")
    ap.add_argument("--since-days", type=int, default=7)
    ap.add_argument("--topics", type=str, default="", help="Comma-separated topics to deep dive (default: all configured topics).")
    ap.add_argument("--out", type=str, default="reports/report_latest.md")
    args = ap.parse_args()

    settings = load_settings()
    cfg = load_config(Path(args.config))
    store = Store(settings.db_url)
    store.init_db()

    since_iso = _since_iso(args.since_days)
    items = store.query_items(since_iso=since_iso, limit=5000)

    # Deep dive selection
    report_cfg = cfg.get("report", {}) or {}
    max_urls = int(report_cfg.get("max_urls_per_topic", 8))
    sonar_model = str(report_cfg.get("sonar_model") or settings.sonar_model)

    topics_cfg = (cfg.get("taxonomy", {}) or {}).get("topics", {}) or {}
    topics_all = list(topics_cfg.keys())

    if args.topics.strip():
        requested = [t.strip() for t in args.topics.split(",") if t.strip()]
        topics = [t for t in requested if t in topics_cfg]
    else:
        topics = topics_all

    deep_sections = []
    if settings.sonar_api_key and topics:
        client = SonarClient(api_key=settings.sonar_api_key, model=sonar_model)
        for t in topics:
            urls = select_urls_for_deep_dive(items, t, max_urls=max_urls)
            if not urls:
                continue

            # Domain filter (optional): use domains extracted from urls
            domains = []
            for u in urls:
                try:
                    dom = u.split("//", 1)[-1].split("/", 1)[0].lower()
                    domains.append(dom)
                except Exception:
                    continue
            domains = list(dict.fromkeys(domains))

            prompt = (
                f"You are generating a media monitoring deep-dive report.\n\n"
                f"Topic: {t}\n\n"
                f"Instructions:\n"
                f"- Use ONLY the sources in the URL list below as evidence.\n"
                f"- Summarize key developments, controversies, and important facts.\n"
                f"- Compare framing differences across publishers when possible.\n"
                f"- Provide concise bullet points and a short narrative paragraph.\n\n"
                f"URL list:\n" + "\n".join([f"- {u}" for u in urls])
            )

            resp = client.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=1400,
                search_recency_filter="week",
                search_domain_filter=domains,
            )
            text, citations = client.extract_text_and_citations(resp)
            deep_sections.append((t, text, citations))

    report_md = render_markdown_report(items, deep_sections=deep_sections)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report_md, encoding="utf-8")

    # Also write a timestamped copy
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out2 = out.parent / f"report_{ts}.md"
    out2.write_text(report_md, encoding="utf-8")

    print("Wrote:", out)
    print("Wrote:", out2)
    if not settings.sonar_api_key:
        print("[INFO] SONAR_API_KEY not set; report generated without deep-dive section.")


if __name__ == "__main__":
    main()
