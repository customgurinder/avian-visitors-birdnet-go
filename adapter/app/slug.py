"""Scientific-name slugify, matching Avian Visitors' convention exactly.

AV (cutout.php / apt.js) and the illustration packs all key images by:
    lowercase, non-alphanumeric runs -> '-', trimmed of leading/trailing '-'
e.g. "Turdus migratorius" -> "turdus-migratorius"
"""
from __future__ import annotations

import re

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(scientific_name: str) -> str:
    return _NON_ALNUM.sub("-", (scientific_name or "").strip().lower()).strip("-")
