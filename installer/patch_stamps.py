#!/usr/bin/env python3
"""Patch AvianVisitors' stamps.js with a British-birds taxonomy overlay.

AV keys each species' Atlas stamp *template* and its family label off three
hard-coded tables in stamps.js:
    GENUS_GROUP  genus  -> group          (drives template + family)
    GROUP_LATIN  group  -> Latin family   (the label shown, e.g. "PARIDAE")
    GROUP_STYLE  group  -> template id     (the stamp design)
These are North-America-centric, so most GB genera fall through to a generic
silhouette stamp and a "Family: Other" label — and naive genus->US-group
mappings mislabel the family (e.g. a Robin as Turdidae instead of Muscicapidae).

This overlay is keyed by the *true Latin family*: for each GB family we add a
group (named by the family) -> its Latin name + a sensible existing template,
and map GB genera into it. Result: correct family labels AND a styled stamp.

Entries are appended at the END of each table literal so they override AV's
where a genus is shared (JS object literal: last key wins). Idempotent; only
edits when the exact `<TABLE> = {` anchors are found. Validated with `node
--check` in the installer build/test.
"""
from __future__ import annotations

import sys
from pathlib import Path

MARKER = "GB-TAXONOMY-PATCH"

# family (also used as the group key) -> (template id, [genera])
# template ids must exist in AV's TPL (values seen in GROUP_STYLE).
GB: dict[str, tuple[str, list[str]]] = {
    "Paridae":        ("terraplana", ["Cyanistes", "Parus", "Periparus", "Poecile", "Lophophanes"]),
    "Aegithalidae":   ("terraplana", ["Aegithalos"]),
    "Panuridae":      ("terraplana", ["Panurus"]),
    "Sittidae":       ("terraplana", ["Sitta"]),
    "Certhiidae":     ("terraplana", ["Certhia"]),
    "Regulidae":      ("terraplana", ["Regulus"]),
    "Troglodytidae":  ("mexico",     ["Troglodytes"]),
    "Fringillidae":   ("editorial",  ["Fringilla", "Chloris", "Linaria", "Spinus", "Carduelis",
                                       "Pyrrhula", "Loxia", "Coccothraustes", "Acanthis", "Serinus"]),
    "Emberizidae":    ("field",      ["Emberiza"]),
    "Calcariidae":    ("field",      ["Plectrophenax"]),
    "Passeridae":     ("field",      ["Passer"]),
    "Prunellidae":    ("field",      ["Prunella"]),
    "Motacillidae":   ("field",      ["Motacilla", "Anthus"]),
    "Corvidae":       ("mono",       ["Corvus", "Pica", "Coloeus", "Garrulus", "Pyrrhocorax", "Nucifraga"]),
    "Sturnidae":      ("dither",     ["Sturnus"]),
    "Turdidae":       ("mexico",     ["Turdus"]),
    "Muscicapidae":   ("zurichpink", ["Erithacus", "Luscinia", "Phoenicurus", "Saxicola",
                                       "Oenanthe", "Muscicapa", "Ficedula"]),
    "Cinclidae":      ("mexico",     ["Cinclus"]),
    "Sylviidae":      ("field",      ["Sylvia", "Curruca"]),
    "Phylloscopidae": ("field",      ["Phylloscopus"]),
    "Acrocephalidae": ("field",      ["Acrocephalus", "Hippolais"]),
    "Locustellidae":  ("field",      ["Locustella"]),
    "Cettiidae":      ("field",      ["Cettia"]),
    "Hirundinidae":   ("field",      ["Hirundo", "Delichon", "Riparia"]),
    "Alaudidae":      ("field",      ["Alauda", "Lullula"]),
    "Columbidae":     ("minimal",    ["Columba", "Streptopelia"]),
    "Anatidae":       ("linescreen", ["Cygnus", "Tadorna", "Anas", "Anser", "Branta", "Aythya",
                                       "Mareca", "Spatula", "Somateria", "Melanitta", "Bucephala",
                                       "Mergus", "Aix"]),
    "Podicipedidae":  ("linescreen", ["Podiceps", "Tachybaptus"]),
    "Ardeidae":       ("flock",      ["Ardea", "Egretta", "Botaurus", "Ardeola", "Nycticorax"]),
    "Laridae":        ("kieler",     ["Larus", "Chroicocephalus", "Rissa", "Sterna", "Sternula",
                                       "Thalasseus", "Hydrocoloeus"]),
    "Accipitridae":   ("raptor",     ["Buteo", "Accipiter", "Milvus", "Circus", "Pernis"]),
    "Pandionidae":    ("raptor",     ["Pandion"]),
    "Falconidae":     ("raptor",     ["Falco"]),
    "Strigidae":      ("opart",      ["Strix", "Asio", "Athene", "Bubo"]),
    "Tytonidae":      ("opart",      ["Tyto"]),
    "Picidae":        ("field",      ["Dendrocopos", "Picus", "Dryobates", "Jynx"]),
    "Apodidae":       ("geo",        ["Apus"]),
    "Alcedinidae":    ("geo",        ["Alcedo"]),
    "Bombycillidae":  ("nzplate",    ["Bombycilla"]),
    "Scolopacidae":   ("field",      ["Scolopax", "Gallinago", "Numenius", "Tringa", "Actitis", "Calidris"]),
    "Rallidae":       ("field",      ["Rallus", "Gallinula", "Fulica"]),
    "Phasianidae":    ("field",      ["Phasianus", "Perdix", "Alectoris", "Coturnix"]),
}


def _match_close(src: str, open_idx: int) -> int:
    """Index of the `}` matching the `{` at open_idx."""
    depth = 0
    for j in range(open_idx, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return j
    return -1


def _inject_at_end(src: str, table: str, entries: str) -> str:
    anchor = f"{table} = {{"
    a = src.find(anchor)
    if a < 0:
        print(f"[patch_stamps] WARNING: anchor '{anchor}' not found; skipping {table}")
        return src
    open_brace = a + len(anchor) - 1
    close = _match_close(src, open_brace)
    if close < 0:
        print(f"[patch_stamps] WARNING: unbalanced braces for {table}; skipping")
        return src
    # Ensure a separating comma if the last existing entry lacks a trailing one.
    k = close - 1
    while k > open_brace and src[k] in " \t\r\n":
        k -= 1
    lead = "" if src[k] == "," else ","
    block = f"{lead}\n    /* {MARKER} */ {entries}\n"
    return src[:close] + block + src[close:]


def patch(path: Path) -> int:
    src = path.read_text(encoding="utf-8")
    if MARKER in src:
        print(f"[patch_stamps] already patched: {path}")
        return 0

    genus_entries = " ".join(
        f"'{g}':'{fam}'," for fam, (_t, genera) in GB.items() for g in genera
    )
    latin_entries = " ".join(f"'{fam}':'{fam}'," for fam in GB)
    style_entries = " ".join(f"'{fam}':'{tpl}'," for fam, (tpl, _g) in GB.items())

    out = src
    out = _inject_at_end(out, "GENUS_GROUP", genus_entries)
    out = _inject_at_end(out, "GROUP_LATIN", latin_entries)
    out = _inject_at_end(out, "GROUP_STYLE", style_entries)

    if out == src:
        print(f"[patch_stamps] no anchors matched; left {path} unchanged")
        return 0
    path.write_text(out, encoding="utf-8")
    n_genera = sum(len(g) for _t, g in GB.values())
    print(f"[patch_stamps] injected {len(GB)} families / {n_genera} genera into {path}")
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: patch_stamps.py <path-to-stamps.js>", file=sys.stderr)
        return 2
    p = Path(sys.argv[1])
    if not p.is_file():
        print(f"[patch_stamps] not found: {p}; skipping")
        return 0
    return patch(p)


if __name__ == "__main__":
    raise SystemExit(main())
