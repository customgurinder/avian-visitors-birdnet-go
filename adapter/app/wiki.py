"""wiki.php replacement — a Wikipedia summary proxy for the detail modal's
"About" section. Independent of BirdNET-Go; talks to Wikipedia's public REST
API. Returns the shape the AV frontend expects (extract + thumbnail + source);
the frontend paragraph-izes `extract` itself when `paragraphs` is empty.
"""
from __future__ import annotations

from urllib.parse import quote

import httpx

from .logging_conf import get_logger

log = get_logger("wiki")

# Wikimedia asks for a descriptive User-Agent; requests without one may be blocked.
_UA = "AvianVisitors-BirdNETGo-Adapter/1.0 (+https://github.com/tphakala/birdnet-go)"

_client: httpx.AsyncClient | None = None


def _get_client(timeout: float) -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": _UA, "Accept": "application/json"},
            follow_redirects=True,
        )
    return _client


async def aclose() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


_EMPTY = {"extract": None, "paragraphs": [], "distinctive": "", "thumbnail": None,
          "title": None, "source": None}


async def summary(sci: str, lang: str, timeout: float) -> dict:
    """Fetch the Wikipedia lead summary for a scientific name."""
    title = quote(sci.strip().replace(" ", "_"), safe="")
    url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}"
    try:
        resp = await _get_client(timeout).get(url)
    except httpx.RequestError as exc:
        log.warning("wikipedia fetch failed for %s: %s", sci, exc)
        return dict(_EMPTY)
    if resp.status_code != 200:
        log.debug("wikipedia %s -> %s", url, resp.status_code)
        return dict(_EMPTY)

    j = resp.json()
    if j.get("type") == "disambiguation":
        return dict(_EMPTY)
    thumb = (j.get("thumbnail") or {}).get("source")
    page = ((j.get("content_urls") or {}).get("desktop") or {}).get("page")
    return {
        "extract": j.get("extract") or None,
        "paragraphs": [],  # frontend builds paragraphs from `extract`
        "distinctive": "",
        "thumbnail": {"source": thumb} if thumb else None,
        "title": j.get("title"),
        "source": {"name": "Wikipedia", "url": page, "license": "CC BY-SA 4.0"} if page else None,
    }
