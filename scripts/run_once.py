from __future__ import annotations

import sys
from pathlib import Path

# Allow running without installing package
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse

from media_monitor.settings import load_settings
from media_monitor.config import load_config
from media_monitor.db.store import Store
from media_monitor.pipeline import ingest_once
from media_monitor.preprocess.enrich import enrich_pending


def main():
    ap = argparse.ArgumentParser(description="Run one monitoring cycle: ingest -> store -> enrich")
    ap.add_argument("--config", type=str, default="monitor_config.json")
    ap.add_argument("--offline-fixtures", action="store_true", help="Use tests/fixtures instead of calling external APIs")
    ap.add_argument("--enrich-only", action="store_true", help="Skip ingestion, run enrichment only")
    args = ap.parse_args()

    settings = load_settings()
    cfg = load_config(Path(args.config))
    store = Store(settings.db_url)
    store.init_db()

    if not args.enrich_only:
        ingest_stats = ingest_once(cfg, store, settings, offline_fixtures=args.offline_fixtures)
        print("Ingest stats:", ingest_stats)
    else:
        print("Skipping ingestion (enrich-only).")

    pre_cfg = cfg.get("preprocess", {}) or {}
    if bool(pre_cfg.get("enabled", True)):
        tax = cfg.get("taxonomy", {}) or {}
        enrich_stats = enrich_pending(
            store=store,
            taxonomy=tax,
            gemini_api_key=settings.gemini_api_key,
            gemini_model=str(pre_cfg.get("gemini_model") or settings.gemini_model),
            batch_size=int(pre_cfg.get("batch_size", 20)),
            max_retries=int(pre_cfg.get("max_retries", 2)),
        )
        print("Enrichment stats:", enrich_stats)
    else:
        print("Preprocess/enrichment disabled in config.")


if __name__ == "__main__":
    main()
