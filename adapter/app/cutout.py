"""Illustration resolver — the cutout.php replacement.

Serves bundled pack illustrations from the shared assets volume, keyed by the
slugified scientific name. Pose 2 = flight (<slug>-2.png), pose 1 = perched
(<slug>.png). Missing species fall back to a neutral SVG silhouette so the
frontend never shows a broken image.

Unlike AV's cutout.php we deliberately do NOT reach out to Wikipedia/rembg at
request time — illustrations come only from installed packs, keeping the
adapter fast, offline-friendly, and dependency-light.
"""
from __future__ import annotations

from pathlib import Path

from .logging_conf import get_logger
from .slug import slugify

log = get_logger("cutout")

# Neutral placeholder shown when no illustration is installed for a species.
PLACEHOLDER_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" '
    'width="200" height="200"><rect width="200" height="200" fill="none"/>'
    '<path d="M60 120c0-25 18-45 44-45 10 0 19 3 26 9l14-9-6 16c4 6 6 13 6 20 '
    "0 26-21 44-47 44s-37-16-37-35z\" fill=\"#c9c4b8\" opacity=\"0.55\"/>"
    '<circle cx="112" cy="96" r="4" fill="#6b6459"/></svg>'
)


def resolve(assets_dir: str, sci: str, pose: int) -> Path | None:
    slug = slugify(sci)
    if not slug:
        return None
    candidates: list[str] = []
    if pose == 2:
        candidates.append(f"{slug}-2.png")
    candidates.append(f"{slug}.png")  # perched, and pose-2 fallback
    base = Path(assets_dir)
    for name in candidates:
        p = base / name
        try:
            if p.is_file() and p.stat().st_size > 1024:
                return p
        except OSError:
            continue
    log.debug("no illustration for %s (slug=%s, pose=%s)", sci, slug, pose)
    return None
