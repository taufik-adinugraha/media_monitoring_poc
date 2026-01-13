from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class Enrichment(BaseModel):
    topics: List[str] = Field(default_factory=list)
    actors: List[str] = Field(default_factory=list)
    locations: List[str] = Field(default_factory=list)
    language: Optional[str] = None
    is_editorial: Optional[bool] = None
