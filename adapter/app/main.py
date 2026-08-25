"""FastAPI app: exposes the Avian Visitors `/avian/api/*` contract, backed by
BirdNET-Go. The AV frontend talks to this exactly as it talked to the original
PHP facade, so no frontend changes are needed.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from starlette.background import BackgroundTask

from . import __version__, cutout, transform, wiki
from .bng_client import BirdNetGoClient, BNGError
from .config import Settings
from .generate import Generator
from .logging_conf import configure_logging

settings = Settings.load()
log = configure_logging(settings.log_level)

_client: BirdNetGoClient | None = None
_generator: Generator | None = None


def client() -> BirdNetGoClient:
    assert _client is not None, "BirdNET-Go client not initialised"
    return _client


def generator() -> Generator:
    assert _generator is not None, "generator not initialised"
    return _generator


async def _common_name_lookup(sci: str) -> str | None:
    """Resolve a species' common name from BirdNET-Go (for generate --com)."""
    data = await client().get_json("/detections", {"species": sci, "numResults": 1})
    rows = (data or {}).get("data") or []
    return rows[0].get("commonName") if rows else None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _client, _generator
    _client = BirdNetGoClient(
        settings.bng_base_url,
        token=settings.api_token,
        timeout=settings.http_timeout,
        cache_ttl=settings.cache_ttl,
        max_detections=settings.max_detections,
    )
    _generator = Generator(settings, _common_name_lookup)
    log.info(
        "adapter %s ready; upstream=%s; generation=%s",
        __version__, settings.bng_base_url,
        "on" if _generator.available()[0] else "off",
    )
    try:
        yield
    finally:
        await _client.aclose()
        await wiki.aclose()


app = FastAPI(
    title="Avian Visitors ↔ BirdNET-Go adapter",
    version=__version__,
    lifespan=lifespan,
)


def _cache_headers(resp: Response) -> Response:
    resp.headers["Cache-Control"] = f"public, max-age={settings.cache_ttl}"
    return resp


# ---------------------------------------------------------------------------
# health
# ---------------------------------------------------------------------------
@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "version": __version__}


@app.get("/readyz")
async def readyz() -> JSONResponse:
    """Ready only if BirdNET-Go is reachable."""
    try:
        await client().get_json("/analytics/species/summary", {"start_date": "2000-01-01"})
        return JSONResponse({"status": "ready", "upstream": settings.bng_base_url})
    except BNGError as exc:
        return JSONResponse(
            {"status": "unavailable", "error": str(exc)}, status_code=503
        )


# ---------------------------------------------------------------------------
# birdnet-api.php facade
# ---------------------------------------------------------------------------
@app.get("/avian/api/birdnet-api.php")
async def birdnet_api(
    action: str = Query("stats"),
    hours: int = Query(24),
    days: int = Query(30),
    limit: int = Query(10),
    offset: int = Query(0),
    date: str | None = Query(None),
    sci: str | None = Query(None),
) -> Response:
    try:
        if action == "stats":
            data = await transform.stats(client(), date)
        elif action == "recent":
            data = await transform.recent(client(), hours, date)
        elif action == "lifelist":
            data = await transform.lifelist(client())
        elif action == "firstseen":
            data = await transform.firstseen(client(), limit, date)
        elif action == "species":
            if not sci:
                return JSONResponse({"error": "sci= required"}, status_code=400)
            data = await transform.species(client(), sci, limit if limit else 500, offset)
        elif action == "timeseries":
            data = await transform.timeseries(client(), days)
        elif action == "hourly":
            data = await transform.hourly(client(), date, limit if limit else 15)
        elif action == "rhythm":
            data = await transform.rhythm(client(), hours, days if days else 7, date)
        elif action == "calendar":
            data = await transform.calendar(client(), settings.calendar_max_days)
        else:
            return JSONResponse({"error": "unknown action"}, status_code=404)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except BNGError as exc:
        log.error("upstream error for action=%s: %s", action, exc)
        return JSONResponse({"error": str(exc)}, status_code=exc.status_code)

    return _cache_headers(JSONResponse(data))


# ---------------------------------------------------------------------------
# cutout.php  (illustrations — served locally from installed packs)
# ---------------------------------------------------------------------------
# GET serves the image; HEAD is used by the frontend to probe pose availability
# (it decides whether to show the illustration or the egg-nest fallback), so it
# MUST be handled — a 405 there makes every bird fall back to the nest.
@app.api_route("/avian/api/cutout.php", methods=["GET", "HEAD"])
async def cutout_php(request: Request, sci: str = Query(...), pose: int = Query(1)) -> Response:
    pose = 2 if pose == 2 else 1
    path = cutout.resolve(settings.assets_dir, sci, pose)

    if request.method == "HEAD":
        # Report availability only; no body. 404 lets the frontend fall back
        # cleanly for species with no installed illustration.
        status = 200 if path is not None else 404
        return Response(status_code=status, media_type="image/png")

    if path is not None:
        resp = FileResponse(path, media_type="image/png")
        resp.headers["Cache-Control"] = "public, max-age=86400"
        return resp
    return Response(
        content=cutout.PLACEHOLDER_SVG,
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=3600"},
    )


# ---------------------------------------------------------------------------
# media proxies: recording.php / spectrogram.php
# ---------------------------------------------------------------------------
async def _proxy_media(path: str, fallback_content_type: str) -> Response:
    try:
        upstream = await client().open_stream(path)
    except BNGError as exc:
        return JSONResponse({"error": str(exc)}, status_code=exc.status_code)
    if upstream.status_code >= 400:
        body = await upstream.aread()
        await upstream.aclose()
        return Response(content=body, status_code=upstream.status_code)
    media_type = upstream.headers.get("content-type", fallback_content_type)
    return StreamingResponse(
        upstream.aiter_bytes(),
        status_code=upstream.status_code,
        media_type=media_type,
        background=BackgroundTask(upstream.aclose),
    )


async def _detection_id_for_species(sci: str) -> int | str | None:
    """Pick a representative detection id for a species (best clip available)."""
    data = await client().get_json(
        "/detections",
        {"species": sci, "numResults": 5, "sortBy": "confidence_desc"},
    )
    rows = (data or {}).get("data") or []
    for r in rows:
        if r.get("clipName"):
            return r.get("id")
    return rows[0].get("id") if rows else None


@app.get("/avian/api/recording.php")
async def recording_php(
    sci: str | None = Query(None),
    file: str | None = Query(None),
    id: str | None = Query(None),
) -> Response:
    # The frontend round-trips `file` from the species action, where we set it
    # to the detection id — so a numeric token resolves via the reliable
    # /audio/:id route. A non-numeric token is treated as a real clip filename.
    try:
        token = id or file
        if token:
            if str(token).isdigit():
                return await _proxy_media(f"/audio/{token}", "audio/mpeg")
            return await _proxy_media(f"/media/audio/{token}", "audio/mpeg")
        if sci:
            det_id = await _detection_id_for_species(sci)
            if det_id is None:
                return JSONResponse({"error": "no recording"}, status_code=404)
            return await _proxy_media(f"/audio/{det_id}", "audio/mpeg")
    except BNGError as exc:
        return JSONResponse({"error": str(exc)}, status_code=exc.status_code)
    return JSONResponse({"error": "sci, file or id required"}, status_code=400)


@app.get("/avian/api/spectrogram.php")
async def spectrogram_php(
    sci: str | None = Query(None),
    file: str | None = Query(None),
    id: str | None = Query(None),
) -> Response:
    try:
        token = id or file
        if token:
            if str(token).isdigit():
                return await _proxy_media(f"/spectrogram/{token}", "image/png")
            return await _proxy_media(f"/media/spectrogram/{token}", "image/png")
        if sci:
            det_id = await _detection_id_for_species(sci)
            if det_id is None:
                return JSONResponse({"error": "no spectrogram"}, status_code=404)
            return await _proxy_media(f"/spectrogram/{det_id}", "image/png")
    except BNGError as exc:
        return JSONResponse({"error": str(exc)}, status_code=exc.status_code)
    return JSONResponse({"error": "sci, file or id required"}, status_code=400)


# ---------------------------------------------------------------------------
# wiki.php — Wikipedia summary proxy for the detail modal's "About" section
# ---------------------------------------------------------------------------
@app.get("/avian/api/wiki.php")
async def wiki_php(sci: str = Query(...), format: str | None = Query(None)) -> Response:
    if not settings.wiki_enabled:
        return _cache_headers(JSONResponse({"extract": None, "thumbnail": None}))
    data = await wiki.summary(sci, settings.wiki_lang, settings.http_timeout)
    resp = JSONResponse(data)
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


# ---------------------------------------------------------------------------
# benign stubs for the admin overlay (station management is intentionally
# disabled — this deployment is visualization-only)
# ---------------------------------------------------------------------------
@app.get("/avian/api/menu.php")
@app.post("/avian/api/menu.php")
async def menu_php() -> JSONResponse:
    return JSONResponse({"enabled": False, "authenticated": False})


@app.get("/avian/api/config.php")
@app.post("/avian/api/config.php")
async def config_php() -> JSONResponse:
    return JSONResponse({"readonly": True})


@app.get("/avian/api/birdnet-status.php")
@app.post("/avian/api/birdnet-status.php")
async def status_php() -> JSONResponse:
    return JSONResponse({"disabled": True})


# On-demand Gemini illustration generation for a species with no installed
# illustration. Enabled only when GENERATE_ENABLED=true and GEMINI_API_KEY is
# set; otherwise `start` returns a clear "not configured" message so the
# postcard's "generate image" button degrades gracefully.
@app.get("/avian/api/generate.php")
@app.post("/avian/api/generate.php")
async def generate_php(
    request: Request,
    action: str = Query("status"),
) -> JSONResponse:
    if action == "start":
        sci = ""
        force = False
        try:
            body = await request.json()
            if isinstance(body, dict):
                sci = str(body.get("sci") or "")
                force = bool(body.get("force"))
        except Exception:  # noqa: BLE001 - fall back to query params
            pass
        sci = sci or request.query_params.get("sci", "")
        code, payload = await generator().start(sci, force=force)
        return JSONResponse(payload, status_code=code)
    # action=status (default)
    return JSONResponse(generator().status())
