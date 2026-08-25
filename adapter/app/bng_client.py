"""Async client for the BirdNET-Go v2 REST API.

Only the read-only endpoints the visualization needs are used:
  GET /api/v2/detections                     (paginated list, filterable)
  GET /api/v2/detections/recent              (last N detections)
  GET /api/v2/analytics/species/summary      (per-species aggregates)
  GET /api/v2/audio/:id                       (audio clip, proxied)
  GET /api/v2/spectrogram/:id                 (spectrogram image, proxied)
"""
from __future__ import annotations

from typing import Any

import httpx

from .cache import TTLCache
from .logging_conf import get_logger

log = get_logger("bng")


class BNGError(Exception):
    """Raised when BirdNET-Go is unreachable or returns an error status."""

    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


class BirdNetGoClient:
    def __init__(
        self,
        base_url: str,
        *,
        token: str | None,
        timeout: float,
        cache_ttl: int,
        max_detections: int,
        page_size: int = 1000,  # BirdNET-Go caps numResults at 1000
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.max_detections = max_detections
        self.page_size = min(page_size, 1000)

        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=timeout,
            follow_redirects=True,
        )
        self._cache = TTLCache(cache_ttl)
        log.info("BirdNET-Go client -> %s (auth: %s)", self.base_url, "yes" if token else "no")

    async def aclose(self) -> None:
        await self._client.aclose()

    # ---- core GET with short-TTL caching -------------------------------
    async def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        params = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
        cache_key = (path, tuple(sorted(params.items())))
        cached = self._cache.get(cache_key)
        if cached is not None:
            log.debug("cache hit  GET %s %s", path, params)
            return cached

        url = f"/api/v2{path}"
        log.debug("upstream   GET %s %s", url, params)
        try:
            resp = await self._client.get(url, params=params)
        except httpx.RequestError as exc:
            raise BNGError(f"cannot reach BirdNET-Go at {self.base_url}: {exc}") from exc

        if resp.status_code >= 400:
            raise BNGError(
                f"BirdNET-Go {url} returned {resp.status_code}: {resp.text[:200]}",
                status_code=502,
            )
        data = resp.json()
        self._cache.set(cache_key, data)
        return data

    # ---- paginated detection pull --------------------------------------
    async def list_detections(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Page through GET /detections, honouring MAX_DETECTIONS.

        Returns the flat list of DetectionResponse dicts.
        """
        out: list[dict[str, Any]] = []
        offset = 0
        while len(out) < self.max_detections:
            page_params = dict(params)
            page_params["numResults"] = self.page_size
            page_params["offset"] = offset
            data = await self.get_json("/detections", page_params)
            rows = (data or {}).get("data") or []
            out.extend(rows)
            total = int((data or {}).get("total", len(out)))
            offset += self.page_size
            if len(rows) < self.page_size or offset >= total:
                break
        if len(out) >= self.max_detections:
            log.warning(
                "MAX_DETECTIONS=%d reached for params=%s; results truncated. "
                "Raise MAX_DETECTIONS if you need wider windows.",
                self.max_detections,
                params,
            )
        return out[: self.max_detections]

    async def species_summary(
        self, start_date: str | None = None, end_date: str | None = None
    ) -> list[dict[str, Any]]:
        """GET /analytics/species/summary -> list of per-species aggregates."""
        data = await self.get_json(
            "/analytics/species/summary",
            {"start_date": start_date, "end_date": end_date},
        )
        if isinstance(data, list):
            return data
        # Some builds may wrap it; be defensive.
        return (data or {}).get("data") or []

    # ---- media streaming (proxied, not redirected) ---------------------
    async def open_stream(self, path: str) -> httpx.Response:
        """Open a streaming GET against BirdNET-Go for media proxying.

        Caller MUST close the returned response (aclose) once the body is
        consumed. We proxy bytes (rather than 302-redirect) so the browser
        never needs direct network access to BirdNET-Go — the adapter can sit
        on an internal Docker network the browser can't see.
        """
        url = f"/api/v2{path}"
        log.debug("proxy      GET %s", url)
        request = self._client.build_request("GET", url)
        try:
            return await self._client.send(request, stream=True)
        except httpx.RequestError as exc:
            raise BNGError(f"cannot reach BirdNET-Go at {self.base_url}: {exc}") from exc
