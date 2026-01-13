from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse

from media_monitor.settings import load_settings
from media_monitor.config import load_config
from media_monitor.db.store import Store
from media_monitor.pipeline import ingest_once
from media_monitor.preprocess.enrich import enrich_pending


def main():
    ap = argparse.ArgumentParser(description="Periodic worker: ingest -> store -> enrich (loop)")
    ap.add_argument("--config", type=str, default="monitor_config.json")
    ap.add_argument("--interval-min", type=int, default=30)
    ap.add_argument("--offline-fixtures", action="store_true")
    args = ap.parse_args()

    settings = load_settings()
    cfg = load_config(Path(args.config))
    store = Store(settings.db_url)
    store.init_db()

    interval_s = int(args.interval_min) * 60

    print(f"Worker started. interval_min={args.interval_min}, db={settings.db_url}")

    while True:
        try:
            ingest_stats = ingest_once(cfg, store, settings, offline_fixtures=args.offline_fixtures)
            print("[cycle] ingest:", ingest_stats)

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
                print("[cycle] enrich:", enrich_stats)
            else:
                print("[cycle] enrichment disabled")

        except Exception as e:
            print("[WARN] cycle failed:", e)

        time.sleep(interval_s)


if __name__ == "__main__":
    main()
