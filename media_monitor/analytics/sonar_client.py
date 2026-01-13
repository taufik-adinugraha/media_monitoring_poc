from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import requests


class SonarClient:
    """Perplexity Sonar client (OpenAI-compatible Chat Completions).

    Base URL: https://api.perplexity.ai
    Endpoint: POST /chat/completions
    """

    def __init__(self, api_key: str, model: str = "sonar-pro", timeout_s: int = 60):
        self.api_key = api_key
        self.model = model
        self.timeout_s = timeout_s
        self.base_url = "https://api.perplexity.ai"

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 1400,
        search_recency_filter: Optional[str] = None,
        search_domain_filter: Optional[List[str]] = None,
        search_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if search_recency_filter:
            payload["search_recency_filter"] = search_recency_filter
        if search_domain_filter:
            payload["search_domain_filter"] = search_domain_filter
        if search_mode:
            payload["search_mode"] = search_mode

        r = requests.post(url, headers=headers, json=payload, timeout=self.timeout_s)
        r.raise_for_status()
        return r.json()

    @staticmethod
    def extract_text_and_citations(resp: Dict[str, Any]) -> Tuple[str, List[str]]:
        text = ""
        citations: List[str] = []
        try:
            text = resp["choices"][0]["message"]["content"] or ""
        except Exception:
            text = ""
        # Some Sonar responses include citations at top-level or per-choice
        if isinstance(resp.get("citations"), list):
            citations = [str(x) for x in resp["citations"]]
        return text, citations
