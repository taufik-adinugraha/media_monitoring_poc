from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class Enrichment(BaseModel):
    # -------------------------
    # Core semantic tags
    # -------------------------
    topics: List[str] = Field(
        default_factory=list,
        description="List of high-level topics (from allowed taxonomy)."
    )

    actors: List[str] = Field(
        default_factory=list,
        description="Public figures, organizations, institutions mentioned."
    )

    locations: List[str] = Field(
        default_factory=list,
        description="Geographic locations (cities, provinces, countries)."
    )

    # -------------------------
    # Linguistic & framing signals
    # -------------------------
    language: Optional[str] = Field(
        default=None,
        description="ISO-639-1 language code (e.g. 'id', 'en')."
    )

    is_editorial: Optional[bool] = Field(
        default=None,
        description="True if opinion/editorial, False if straight reporting, None if unclear."
    )

    sentiment: Optional[str] = Field(
        default=None,
        description="Overall sentiment: 'positive', 'negative', or 'neutral'."
    )
