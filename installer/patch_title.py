#!/usr/bin/env python3
"""Set the browser-tab title of the AvianVisitors frontend.

Upstream ships `<title>your birds</title>`. This rewrites just the document
`<title>` (the browser-tab / bookmark name) to the value of the SITE_TITLE
environment variable, defaulting to "Avian Visitors".

Only the `<title>` element is touched — the visible in-page "your birds"
headings are left alone. Idempotent and update-safe: it always sets the title
to the current SITE_TITLE, so re-running with a new value just updates it.
Anchors on the `<title>` tag; skips cleanly if none is found.
"""
from __future__ import annotations

import html
import os
import re
import sys
from pathlib import Path

DEFAULT_TITLE = "Avian Visitors"
TITLE_RE = re.compile(r"<title\b[^>]*>.*?</title>", re.IGNORECASE | re.DOTALL)


def patch(path: Path, title: str) -> int:
    src = path.read_text(encoding="utf-8")
    replacement = f"<title>{html.escape(title, quote=False)}</title>"

    new, n = TITLE_RE.subn(replacement, src, count=1)
    if n == 0:
        print(f"[patch_title] WARNING: no <title> found in {path}; skipping")
        return 0
    if new == src:
        print(f"[patch_title] title already {title!r} in {path}")
        return 0
    path.write_text(new, encoding="utf-8")
    print(f"[patch_title] set browser-tab title to {title!r} in {path}")
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: patch_title.py <path-to-index.html>", file=sys.stderr)
        return 2
    p = Path(sys.argv[1])
    if not p.is_file():
        print(f"[patch_title] not found: {p}; skipping")
        return 0
    title = (os.environ.get("SITE_TITLE") or DEFAULT_TITLE).strip() or DEFAULT_TITLE
    return patch(p, title)


if __name__ == "__main__":
    raise SystemExit(main())
