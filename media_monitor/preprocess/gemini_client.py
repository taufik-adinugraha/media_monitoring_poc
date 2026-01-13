from __future__ import annotations

import json
from typing import Any, Dict, Optional

import requests

from .schema import Enrichment


class GeminiClient:
    """Minimal REST client for Gemini generateContent.

    Uses Gemini API endpoint:
      POST https://generativelanguage.googleapis.com/v1beta/{model=models/*}:generateContent?key=...
    """

    def __init__(self, api_key: str, model: str = "models/gemini-2.0-flash-lite", timeout_s: int = 30):
        self.api_key = api_key
        self.model = model
        self.timeout_s = timeout_s

    def enrich(
        self,
        prompt: str,
        response_schema: Optional[Dict[str, Any]] = None,
        temperature: float = 0.1,
    ) -> Enrichment:
        url = f"https://generativelanguage.googleapis.com/v1beta/{self.model}:generateContent"
        params = {"key": self.api_key}

        generation_config: Dict[str, Any] = {
            "temperature": temperature,
            "responseMimeType": "application/json",
        }
        if response_schema:
            generation_config["responseSchema"] = response_schema

        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": generation_config,
        }

        r = requests.post(url, params=params, json=payload, timeout=self.timeout_s)
        r.raise_for_status()
        data = r.json()

        # Gemini responses include candidates[0].content.parts[0].text
        text = None
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception:
            # fallback: some responses have 'text' convenience field in SDKs, not REST
            text = None

        if not text:
            raise ValueError(f"Gemini returned no text. Raw={data}")

        # Parse JSON
        try:
            obj = json.loads(text)
        except Exception as e:
            raise ValueError(f"Gemini output was not valid JSON: {e}. Text={text[:200]}")

        return Enrichment.model_validate(obj)


def default_enrichment_schema() -> Dict[str, Any]:
    """Schema in Gemini's OpenAPI-like subset (JSON schema-ish)."""
    return {
        "type": "OBJECT",
        "properties": {
            "topics": {"type": "ARRAY", "items": {"type": "STRING"}},
            "actors": {"type": "ARRAY", "items": {"type": "STRING"}},
            "locations": {"type": "ARRAY", "items": {"type": "STRING"}},
            "language": {"type": "STRING"},
            "is_editorial": {"type": "BOOLEAN"},
        },
        "required": ["topics", "actors", "locations"],
    }
