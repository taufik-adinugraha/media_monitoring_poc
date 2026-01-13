from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

from pathlib import Path


@dataclass(frozen=True)
class Settings:
    repo_root: Path
    data_dir: Path
    reports_dir: Path
    db_url: str

    mediastack_key: str | None
    youtube_api_key: str | None

    gemini_api_key: str | None
    gemini_model: str

    sonar_api_key: str | None
    sonar_model: str

    http_user_agent: str


def _getenv(key: str, default: str | None = None) -> str | None:
    v = os.getenv(key)
    if v is None or v.strip() == "":
        return default
    return v


def load_settings() -> Settings:
    # Load .env automatically (optional)
    if load_dotenv is not None:
        try:
            load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / '.env')
        except Exception:
            pass

    repo_root = Path(__file__).resolve().parents[1]
    data_dir = repo_root / "data"
    reports_dir = repo_root / "reports"
    data_dir.mkdir(exist_ok=True)
    reports_dir.mkdir(exist_ok=True)

    db_url = _getenv("DATABASE_URL", "sqlite:///data/media_monitor.db") or "sqlite:///data/media_monitor.db"

    http_user_agent = _getenv("HTTP_USER_AGENT", "Mozilla/5.0 (compatible; MediaMonitorPOC/1.0)") or "Mozilla/5.0 (compatible; MediaMonitorPOC/1.0)"

    mediastack_key = _getenv("MEDIASTACK_KEY", None)
    youtube_api_key = _getenv("YOUTUBE_API_KEY", None)

    gemini_api_key = _getenv("GEMINI_API_KEY", None)
    gemini_model = _getenv("GEMINI_MODEL", "models/gemini-2.0-flash-lite") or "models/gemini-2.0-flash-lite"

    sonar_api_key = _getenv("SONAR_API_KEY", None)
    sonar_model = _getenv("SONAR_MODEL", "sonar-pro") or "sonar-pro"

    return Settings(
        repo_root=repo_root,
        data_dir=data_dir,
        reports_dir=reports_dir,
        db_url=db_url,
        mediastack_key=mediastack_key,
        youtube_api_key=youtube_api_key,
        gemini_api_key=gemini_api_key,
        gemini_model=gemini_model,
        sonar_api_key=sonar_api_key,
        sonar_model=sonar_model,
        http_user_agent=http_user_agent,
    )
