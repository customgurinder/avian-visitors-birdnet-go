"""Translate BirdNET-Go API data into the Avian Visitors JSON contract.

Each function returns the exact shape the AV frontend's `birdnet-api.php`
consumer expects, so the frontend runs unmodified. See the original contract
in AvianVisitors/avian/api/birdnet-api.php.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from .bng_client import BirdNetGoClient
from .logging_conf import get_logger
from . import timeutil as T

log = get_logger("transform")

# Treat "all time" as this earliest date when calling analytics with a range.
_EPOCH_DATE = "2000-01-01"


def _iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().replace(microsecond=0).isoformat()


def _row_dt(row: dict[str, Any]) -> datetime | None:
    """Best datetime for a DetectionResponse row."""
    ts = row.get("timestamp")
    dt = T.parse_dt(ts) if ts else None
    if dt:
        return dt
    date = row.get("date")
    time = row.get("time")
    if date and time:
        return T.parse_dt(f"{date} {time}")
    return None


def _summary_index(summary: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {r.get("scientific_name", ""): r for r in summary}


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------
async def stats(client: BirdNetGoClient, date_param: str | None) -> dict[str, Any]:
    ctx = T.date_context(date_param)
    date = ctx["date"]
    anchor: datetime = ctx["anchor"]

    all_time = await client.species_summary(_EPOCH_DATE, date)
    today = await client.species_summary(date, date)
    week = await client.species_summary(T.days_ago(anchor, 6), date)

    total_det = sum(int(r.get("count", 0)) for r in all_time)
    total_spec = len([r for r in all_time if int(r.get("count", 0)) > 0])
    day_det = sum(int(r.get("count", 0)) for r in today)
    day_spec = len([r for r in today if int(r.get("count", 0)) > 0])
    week_det = sum(int(r.get("count", 0)) for r in week)
    week_spec = len([r for r in week if int(r.get("count", 0)) > 0])

    # last hour: pull the day's recent rows and count those within 60 min of anchor.
    last_hour = 0
    rows = await client.list_detections(
        {"start_date": date, "end_date": date, "sortBy": "date_desc"}
    )
    cutoff = anchor.timestamp() - 3600
    for r in rows:
        dt = _row_dt(r)
        if dt and cutoff < dt.timestamp() <= anchor.timestamp():
            last_hour += 1

    started = None
    first_dates = [T.date_of(r.get("first_heard")) for r in all_time if r.get("first_heard")]
    first_dates = [d for d in first_dates if d]
    if first_dates:
        started = min(first_dates)

    return {
        "totals": {"detections": total_det, "species": total_spec},
        "today": {"detections": day_det, "species": day_spec},
        "last_hour": {"detections": last_hour},
        "week": {"detections": week_det, "species": week_spec},
        "started": started,
        "date": date,
        "station_date": ctx["today"],
        "is_today": ctx["is_today"],
        "anchor": anchor.strftime(T.FMT_DT),
        "as_of": _iso_now(),
    }


# ---------------------------------------------------------------------------
# recent  (the "recently heard" collage)
# ---------------------------------------------------------------------------
async def recent(client: BirdNetGoClient, hours: int, date_param: str | None) -> dict[str, Any]:
    hours = max(1, min(1_000_000, hours))
    ctx = T.date_context(date_param)
    anchor: datetime = ctx["anchor"]
    start_ts = anchor.timestamp() - hours * 3600
    start_date = datetime.fromtimestamp(start_ts).strftime(T.FMT_DATE)
    end_date = ctx["date"]

    rows = await client.list_detections(
        {"start_date": start_date, "end_date": end_date, "sortBy": "date_desc"}
    )

    # Group by species within the exact time window.
    groups: dict[str, dict[str, Any]] = {}
    for r in rows:
        dt = _row_dt(r)
        if not dt or not (start_ts < dt.timestamp() <= anchor.timestamp()):
            continue
        sci = r.get("scientificName") or ""
        if not sci:
            continue
        conf = float(r.get("confidence", 0) or 0)
        g = groups.get(sci)
        if g is None:
            g = groups[sci] = {
                "sci": sci,
                "com": r.get("commonName") or "",
                "n": 0,
                "best_conf": 0.0,
                "last_seen": None,
                "_last_ts": 0.0,
                "top_file": None,
                "top_id": None,
                "top_at": None,
                "_top_conf": -1.0,
            }
        g["n"] += 1
        if conf > g["best_conf"]:
            g["best_conf"] = conf
        ts = dt.timestamp()
        if ts > g["_last_ts"]:
            g["_last_ts"] = ts
            g["last_seen"] = dt.strftime(T.FMT_DT)
        # top detection = highest confidence (prefer one that has a clip)
        has_clip = bool(r.get("clipName"))
        better = conf > g["_top_conf"] or (conf == g["_top_conf"] and has_clip and not g["top_file"])
        if better:
            g["_top_conf"] = conf
            g["top_file"] = r.get("clipName") or None
            g["top_id"] = r.get("id")
            g["top_at"] = dt.strftime(T.FMT_DT)

    species = []
    for g in groups.values():
        g.pop("_last_ts", None)
        g.pop("_top_conf", None)
        species.append(g)
    species.sort(key=lambda s: s["last_seen"] or "", reverse=True)

    return {
        "hours": hours,
        "date": ctx["date"],
        "station_date": ctx["today"],
        "is_today": ctx["is_today"],
        "anchor": anchor.strftime(T.FMT_DT),
        "species": species,
        "as_of": _iso_now(),
    }


# ---------------------------------------------------------------------------
# lifelist
# ---------------------------------------------------------------------------
async def lifelist(client: BirdNetGoClient) -> dict[str, Any]:
    summary = await client.species_summary(_EPOCH_DATE, T.now().strftime(T.FMT_DATE))
    species = []
    for r in summary:
        species.append(
            {
                "sci": r.get("scientific_name"),
                "com": r.get("common_name"),
                "first_seen": T.normalize_dt(r.get("first_heard")),
                "last_seen": T.normalize_dt(r.get("last_heard")),
                "n": int(r.get("count", 0)),
                "best_conf": float(r.get("max_confidence", 0) or 0),
            }
        )
    species.sort(key=lambda s: s["first_seen"] or "")
    return {"species": species, "as_of": _iso_now()}


# ---------------------------------------------------------------------------
# firstseen
# ---------------------------------------------------------------------------
async def firstseen(client: BirdNetGoClient, limit: int, date_param: str | None) -> dict[str, Any]:
    limit = max(1, min(50, limit))
    ctx = T.date_context(date_param)
    summary = await client.species_summary(_EPOCH_DATE, ctx["date"])
    rows = [
        {
            "sci": r.get("scientific_name"),
            "com": r.get("common_name"),
            "first_seen": T.normalize_dt(r.get("first_heard")),
            "total": int(r.get("count", 0)),
        }
        for r in summary
        if r.get("first_heard")
    ]
    rows.sort(key=lambda s: s["first_seen"] or "", reverse=True)
    return {
        "date": ctx["date"],
        "station_date": ctx["today"],
        "is_today": ctx["is_today"],
        "species": rows[:limit],
        "as_of": _iso_now(),
    }


# ---------------------------------------------------------------------------
# species detail
# ---------------------------------------------------------------------------
async def species(client: BirdNetGoClient, sci: str, limit: int, offset: int) -> dict[str, Any]:
    limit = max(1, min(1000, limit))
    offset = max(0, offset)
    data = await client.get_json(
        "/detections",
        {"species": sci, "numResults": limit, "offset": offset, "sortBy": "date_desc"},
    )
    rows = (data or {}).get("data") or []
    # `file` is an opaque handle the frontend round-trips to recording.php /
    # spectrogram.php. We hand back the BirdNET-Go detection id (as a string):
    # its media is reliably served by /api/v2/audio/:id and /spectrogram/:id,
    # whereas clip filenames don't resolve via the media-by-filename routes.
    detections = [
        {
            "d": r.get("date"),
            "t": r.get("time"),
            "file": str(r["id"]) if r.get("id") is not None else (r.get("clipName") or None),
            "conf": float(r.get("confidence", 0) or 0),
            "id": r.get("id"),
        }
        for r in rows
    ]
    summary = await client.species_summary(_EPOCH_DATE, T.now().strftime(T.FMT_DATE))
    match = _summary_index(summary).get(sci)
    summary_out = None
    if match:
        summary_out = {
            "com": match.get("common_name"),
            "total": int(match.get("count", 0)),
            "first_seen": T.normalize_dt(match.get("first_heard")),
            "last_seen": T.normalize_dt(match.get("last_heard")),
            "best_conf": float(match.get("max_confidence", 0) or 0),
        }
    return {
        "sci": sci,
        "summary": summary_out,
        "detections": detections,
        "page": {"limit": limit, "offset": offset, "returned": len(detections)},
    }


# ---------------------------------------------------------------------------
# timeseries / hourly / rhythm / calendar  (computed from windowed rows)
# ---------------------------------------------------------------------------
async def timeseries(client: BirdNetGoClient, days: int) -> dict[str, Any]:
    days = max(1, min(90, days))
    span = max(days, 30)
    anchor = T.now()
    start = T.days_ago(anchor, span - 1)
    end = anchor.strftime(T.FMT_DATE)
    rows = await client.list_detections({"start_date": start, "end_date": end, "sortBy": "date_asc"})

    per_day_det: dict[str, int] = defaultdict(int)
    per_day_spec: dict[str, set] = defaultdict(set)
    per_hour: dict[int, int] = defaultdict(int)
    for r in rows:
        d = r.get("date")
        if not d:
            continue
        per_day_det[d] += 1
        per_day_spec[d].add(r.get("scientificName"))
        dt = _row_dt(r)
        if dt:
            per_hour[dt.hour] += 1

    daily = [
        {"date": d, "detections": per_day_det[d], "species": len(per_day_spec[d])}
        for d in sorted(per_day_det)
    ]
    by_hour = [{"hour": h, "detections": per_hour[h]} for h in sorted(per_hour)]
    return {"days": days, "daily": daily, "by_hour": by_hour, "as_of": _iso_now()}


async def hourly(client: BirdNetGoClient, date_param: str | None, limit: int) -> dict[str, Any]:
    limit = max(1, min(30, limit))
    ctx = T.date_context(date_param)
    date = ctx["date"]
    rows = await client.list_detections({"start_date": date, "end_date": date})

    totals: dict[str, int] = defaultdict(int)
    per_species_hour: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    common: dict[str, str] = {}
    for r in rows:
        sci = r.get("scientificName")
        if not sci or r.get("date") != date:
            continue
        common.setdefault(sci, r.get("commonName") or "")
        dt = _row_dt(r)
        if not dt:
            continue
        totals[sci] += 1
        per_species_hour[sci][dt.hour] += 1

    top = sorted(totals, key=lambda s: (-totals[s], s))[:limit]
    species_out = []
    for sci in top:
        hours = [{"hour": h, "n": per_species_hour[sci][h]} for h in sorted(per_species_hour[sci])]
        species_out.append(
            {"sci": sci, "com": common.get(sci, ""), "total": totals[sci], "hours": hours}
        )
    species_out.sort(key=lambda s: (-s["total"], s["sci"]))

    anchor_hour = T.now().hour if ctx["is_today"] else 23
    return {
        "date": date,
        "station_date": ctx["today"],
        "is_today": ctx["is_today"],
        "anchor_hour": anchor_hour,
        "species": species_out,
        "as_of": _iso_now(),
    }


def _slot_counts(rows: list[dict[str, Any]], on_date: str | None = None) -> dict[int, int]:
    counts: dict[int, int] = defaultdict(int)
    for r in rows:
        if on_date is not None and r.get("date") != on_date:
            continue
        dt = _row_dt(r)
        if dt:
            counts[dt.hour * 60 + dt.minute] += 1
    return counts


async def rhythm(
    client: BirdNetGoClient, hours: int, days: int, date_param: str | None
) -> dict[str, Any]:
    days = max(1, min(30, days))
    hours = max(1, min(1_000_000, hours))
    ctx = T.date_context(date_param)
    date = ctx["date"]
    anchor: datetime = ctx["anchor"]
    is_today = ctx["is_today"]
    mode = "week" if hours == 168 else ("all-day" if hours >= 1_000_000 else "day")

    if mode == "week":
        cur_rows = await client.list_detections(
            {"start_date": T.days_ago(anchor, 7), "end_date": date, "sortBy": "date_asc"}
        )
        prev_rows = await client.list_detections(
            {"start_date": T.days_ago(anchor, 14), "end_date": T.days_ago(anchor, 7), "sortBy": "date_asc"}
        )
        cur = _slot_counts(cur_rows)
        prev = _slot_counts(prev_rows)
        today_series = [{"slot": s, "detections": round(cur[s] / 7, 2)} for s in sorted(cur)]
        avg_series = [{"slot": s, "avg": round(prev[s] / 7, 2)} for s in sorted(prev)]
    else:
        day_rows = await client.list_detections({"start_date": date, "end_date": date})
        prior_rows = await client.list_detections(
            {"start_date": T.days_ago(datetime.strptime(date, T.FMT_DATE), days),
             "end_date": date, "sortBy": "date_asc"}
        )
        cur = _slot_counts(day_rows, on_date=date)
        # prior excludes the selected day
        prior = defaultdict(int)
        for r in prior_rows:
            if r.get("date") == date:
                continue
            dt = _row_dt(r)
            if dt:
                prior[dt.hour * 60 + dt.minute] += 1
        today_series = [{"slot": s, "detections": cur[s]} for s in sorted(cur)]
        avg_series = [{"slot": s, "avg": round(prior[s] / days, 2)} for s in sorted(prior)]

    now_slot = (T.now().hour * 60 + T.now().minute) if (is_today and mode != "week") else 1439
    if hours <= 1:
        range_start = max(0, now_slot - 59)
    elif hours <= 12:
        range_start = max(0, now_slot - 719)
    else:
        range_start = 0
    range_end = now_slot if hours <= 12 else 1439

    return {
        "days": days,
        "hours": hours,
        "mode": mode,
        "date": date,
        "station_date": ctx["today"],
        "is_today": is_today,
        "slots": 1440,
        "today": today_series,
        "avg": avg_series,
        "now_slot": now_slot,
        "now_hour": now_slot // 60,
        "range_start_slot": range_start,
        "range_end_slot": range_end,
        "as_of": _iso_now(),
    }


async def calendar(client: BirdNetGoClient, max_days: int) -> dict[str, Any]:
    anchor = T.now()
    today = anchor.strftime(T.FMT_DATE)
    start = T.days_ago(anchor, max(1, max_days) - 1)
    rows = await client.list_detections({"start_date": start, "end_date": today, "sortBy": "date_asc"})

    per_day_det: dict[str, int] = defaultdict(int)
    per_day_spec: dict[str, set] = defaultdict(set)
    for r in rows:
        d = r.get("date")
        if not d:
            continue
        per_day_det[d] += 1
        per_day_spec[d].add(r.get("scientificName"))

    days_list = [
        {"date": d, "detections": per_day_det[d], "species": len(per_day_spec[d])}
        for d in sorted(per_day_det)
    ]
    return {
        "station_date": today,
        "first_date": days_list[0]["date"] if days_list else None,
        "last_date": days_list[-1]["date"] if days_list else None,
        "days": days_list,
        "as_of": _iso_now(),
    }
