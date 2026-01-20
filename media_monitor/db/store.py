from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from ..utils import json_dumps, json_loads
from .models import Base, MediaItem, IngestState


class Store:
    """A minimal store abstraction (SQLite now, swappable via DATABASE_URL)."""

    def __init__(self, db_url: str):
        self.engine = create_engine(db_url, future=True)

    def init_db(self) -> None:
        Base.metadata.create_all(self.engine)

    @contextmanager
    def session(self) -> Iterable[Session]:
        with Session(self.engine) as s:
            yield s

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------
    def upsert_items(self, items: List[Dict[str, Any]]) -> Tuple[int, int]:
        """Insert new items; update existing if same id.
        Returns (inserted, updated).
        """
        inserted = 0
        updated = 0

        protected_fields = {
            "topics",
            "actors",
            "locations",
            "language",
            "is_editorial",
            "sentiment",
            "tags_json",
            "signals_json",
            "content_text",
            "content_fetched_at",
            "content_status",
            "content_hash",
            "enriched_at",
            "enrich_model",
            "enrich_status",
            "enrich_error",
        }

        with self.session() as s:
            for it in items:
                obj = s.get(MediaItem, it["id"])
                if obj is None:
                    s.add(MediaItem(**it))
                    inserted += 1
                else:
                    for k, v in it.items():
                        if k in protected_fields:
                            continue
                        setattr(obj, k, v)
                    updated += 1
            s.commit()

        return inserted, updated

    # ------------------------------------------------------------------
    # Enrichment helpers
    # ------------------------------------------------------------------
    def list_unenriched(self, limit: int = 200) -> List[MediaItem]:
        with self.session() as s:
            q = (
                select(MediaItem)
                .where(MediaItem.enriched_at.is_(None))
                .limit(limit)
            )
            return list(s.scalars(q).all())

    def update_enrichment(
        self,
        item_id: str,
        topics: List[str],
        actors: List[str],
        locations: List[str],
        language: Optional[str],
        is_editorial: Optional[bool],
        sentiment: Optional[str],
        tags_json: Dict[str, Any],
        model: str,
        status: str,
        error: Optional[str] = None,
        enriched_at: Optional[str] = None,
    ) -> None:
        with self.session() as s:
            obj = s.get(MediaItem, item_id)
            if obj is None:
                return

            obj.topics = json_dumps(topics)
            obj.actors = json_dumps(actors)
            obj.locations = json_dumps(locations)
            obj.language = language
            obj.is_editorial = is_editorial
            obj.sentiment = sentiment

            obj.tags_json = json_dumps(tags_json)
            obj.enrich_model = model
            obj.enrich_status = status
            obj.enrich_error = error
            obj.enriched_at = enriched_at

            s.commit()

    # ------------------------------------------------------------------
    # Content crawling helpers (NEW)
    # ------------------------------------------------------------------
    def update_content(
        self,
        item_id: str,
        content_text: str,
        fetched_at: Optional[str],
        status: str = "ok",
        content_hash: Optional[str] = None,
    ) -> None:
        with self.session() as s:
            obj = s.get(MediaItem, item_id)
            if obj is None:
                return

            obj.content_text = content_text
            obj.content_fetched_at = fetched_at
            obj.content_status = status

            if content_hash:
                obj.content_hash = content_hash

            s.commit()

    # ------------------------------------------------------------------
    # Ingest state
    # ------------------------------------------------------------------
    def get_state(self, source: str) -> Optional[IngestState]:
        with self.session() as s:
            return s.get(IngestState, source)

    def set_state(
        self,
        source: str,
        last_run_at: Optional[str],
        cursor: Optional[str] = None,
    ) -> None:
        with self.session() as s:
            obj = s.get(IngestState, source)
            if obj is None:
                s.add(
                    IngestState(
                        source=source,
                        last_run_at=last_run_at,
                        cursor=cursor,
                    )
                )
            else:
                obj.last_run_at = last_run_at
                obj.cursor = cursor
            s.commit()

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------
    def query_items(
        self,
        since_iso: Optional[str] = None,
        topics_any: Optional[List[str]] = None,
        platform: Optional[str] = None,
        publisher: Optional[str] = None,
        limit: int = 2000,
    ) -> List[MediaItem]:
        """Simple query helper. For larger scale, use dedicated analytics DB."""
        with self.session() as s:
            q = select(MediaItem)
            if since_iso:
                q = q.where(MediaItem.published_at >= since_iso)
            if platform:
                q = q.where(MediaItem.platform == platform)
            if publisher:
                q = q.where(MediaItem.publisher_or_author == publisher)
            q = q.limit(limit)
            rows = list(s.scalars(q).all())

        if topics_any:
            out = []
            for r in rows:
                try:
                    t = json_loads(r.topics) if r.topics else []
                except Exception:
                    t = []
                if any(x in t for x in topics_any):
                    out.append(r)
            return out

        return rows
