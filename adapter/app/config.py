"""Environment-driven configuration.

Everything is configurable via environment variables so the same image runs
for anyone without code changes. The only required setting is where to reach
your BirdNET-Go instance.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _get_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _build_base_url() -> str:
    """Resolve the BirdNET-Go base URL.

    Precedence:
      1. BIRDNETGO_URL  (full base URL, e.g. http://192.168.1.50:8080)
      2. BIRDNETGO_SCHEME + BIRDNETGO_HOST + BIRDNETGO_PORT
    """
    url = (os.getenv("BIRDNETGO_URL") or "").strip()
    if url:
        return url.rstrip("/")

    host = (os.getenv("BIRDNETGO_HOST") or "").strip()
    if not host:
        raise RuntimeError(
            "BirdNET-Go location not configured. Set BIRDNETGO_URL "
            "(e.g. http://192.168.1.50:8080) or BIRDNETGO_HOST (+ optional "
            "BIRDNETGO_PORT / BIRDNETGO_SCHEME)."
        )
    scheme = (os.getenv("BIRDNETGO_SCHEME") or "http").strip() or "http"
    port = (os.getenv("BIRDNETGO_PORT") or "8080").strip() or "8080"
    return f"{scheme}://{host}:{port}".rstrip("/")


@dataclass(frozen=True)
class Settings:
    bng_base_url: str
    api_token: str | None
    http_timeout: float
    cache_ttl: int
    max_detections: int
    assets_dir: str
    log_level: str
    calendar_max_days: int
    wiki_lang: str
    wiki_enabled: bool
    gemini_api_key: str | None
    generate_enabled: bool
    gen_dir: str
    generate_hourly_cap: int

    @staticmethod
    def load() -> "Settings":
        return Settings(
            bng_base_url=_build_base_url(),
            api_token=(os.getenv("BIRDNETGO_API_TOKEN") or "").strip() or None,
            http_timeout=float(os.getenv("HTTP_TIMEOUT", "10")),
            cache_ttl=int(os.getenv("CACHE_TTL", "30")),
            max_detections=int(os.getenv("MAX_DETECTIONS", "5000")),
            assets_dir=(os.getenv("ASSETS_DIR") or "/data/assets/illustrations"),
            log_level=(os.getenv("LOG_LEVEL") or "INFO").upper(),
            calendar_max_days=int(os.getenv("CALENDAR_MAX_DAYS", "365")),
            wiki_lang=(os.getenv("WIKI_LANG") or "en").strip() or "en",
            wiki_enabled=_get_bool("WIKI_ENABLED", True),
            gemini_api_key=(os.getenv("GEMINI_API_KEY") or "").strip() or None,
            # Generation is on only when explicitly enabled AND a key is present.
            generate_enabled=_get_bool("GENERATE_ENABLED", False),
            gen_dir=(os.getenv("GEN_DIR") or "/data/gen"),
            generate_hourly_cap=int(os.getenv("GENERATE_HOURLY_CAP", "6")),
        )
