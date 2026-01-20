from __future__ import annotations

from typing import Optional

from sqlalchemy import String, Text, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class MediaItem(Base):
    __tablename__ = "media_items"

    # -------------------------
    # Identity & provenance
    # -------------------------
    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256
    platform: Mapped[str] = mapped_column(String(32), index=True)  # rss|gdelt|youtube
    source_type: Mapped[str] = mapped_column(String(16), index=True)  # news|social
    publisher_or_author: Mapped[str] = mapped_column(String(128), index=True)
    url: Mapped[str] = mapped_column(Text, index=True)

    # -------------------------
    # Basic metadata
    # -------------------------
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    published_at: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True, index=True
    )
    ingested_at: Mapped[str] = mapped_column(String(40), index=True)

    # -------------------------
    # Crawled content (NEW)
    # -------------------------
    content_text: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    content_fetched_at: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True, index=True
    )
    content_status: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True
    )  # ok|blocked|error|skipped

    content_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True
    )

    # -------------------------
    # Enriched tags (LLM)
    # -------------------------
    topics: Mapped[Optional[str]] = mapped_column(Text, nullable=True)      # JSON list
    actors: Mapped[Optional[str]] = mapped_column(Text, nullable=True)      # JSON list
    locations: Mapped[Optional[str]] = mapped_column(Text, nullable=True)   # JSON list
    language: Mapped[Optional[str]] = mapped_column(
        String(16), nullable=True, index=True
    )

    is_editorial: Mapped[Optional[bool]] = mapped_column(
        Boolean, nullable=True, index=True
    )

    sentiment: Mapped[Optional[str]] = mapped_column(
        String(16), nullable=True, index=True
    )  # positive|negative|neutral

    # -------------------------
    # Raw & structured blobs
    # -------------------------
    tags_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    signals_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_json: Mapped[str] = mapped_column(Text)

    # -------------------------
    # Enrichment bookkeeping
    # -------------------------
    enriched_at: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True, index=True
    )
    enrich_model: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True
    )
    enrich_status: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True, index=True
    )  # ok|error
    enrich_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class IngestState(Base):
    __tablename__ = "ingest_state"

    source: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_run_at: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    cursor: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
