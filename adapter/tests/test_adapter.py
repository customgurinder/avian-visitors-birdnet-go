"""Pure-function tests (no network). Run: cd adapter && python -m pytest"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.slug import slugify  # noqa: E402
from app import timeutil as T  # noqa: E402
from app.cutout import resolve, PLACEHOLDER_SVG  # noqa: E402


def test_slugify_matches_av_convention():
    assert slugify("Turdus migratorius") == "turdus-migratorius"
    assert slugify("  Erithacus  rubecula ") == "erithacus-rubecula"
    assert slugify("Anas platyrhynchos platyrhynchos") == "anas-platyrhynchos-platyrhynchos"
    assert slugify("") == ""


def test_normalize_dt_variants():
    assert T.normalize_dt("2024-05-01T06:12:33+01:00") == "2024-05-01 06:12:33"
    assert T.normalize_dt("2024-05-01 06:12:33") == "2024-05-01 06:12:33"
    assert T.normalize_dt("2024-05-01T06:12:33.512Z") == "2024-05-01 06:12:33"
    assert T.normalize_dt("2024-05-01") == "2024-05-01 00:00:00"
    assert T.normalize_dt(None) is None


def test_date_context_rejects_future_and_bad():
    import pytest

    with pytest.raises(ValueError):
        T.date_context("2999-01-01")
    with pytest.raises(ValueError):
        T.date_context("not-a-date")
    ctx = T.date_context(None)
    assert ctx["is_today"] is True
    assert len(ctx["date"]) == 10


def test_cutout_resolve_and_placeholder(tmp_path):
    # missing -> None, placeholder is valid-ish svg
    assert resolve(str(tmp_path), "Turdus migratorius", 1) is None
    assert PLACEHOLDER_SVG.startswith("<svg")

    # create a perched illustration > 1KB and resolve it
    img = tmp_path / "turdus-migratorius.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 2048)
    assert resolve(str(tmp_path), "Turdus migratorius", 1) == img
    # pose 2 falls back to perched when no -2 file exists
    assert resolve(str(tmp_path), "Turdus migratorius", 2) == img
