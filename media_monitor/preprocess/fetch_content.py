# media_monitor/preprocess/fetch_content.py

import trafilatura
import requests

def fetch_article_text(url: str) -> str | None:
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return None

        text = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=False
        )
        return text.strip() if text else None

    except Exception:
        return None