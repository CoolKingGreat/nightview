"""
Data access layer.

If `data/processed/trends.parquet` exists, all queries hit the real per-city
dataset produced by `scripts/ingest_seed.py` (or, when it ships, the
GEE-based per-pixel ingestion in `scripts/ingest_gee.py`). If the Parquet is
missing the layer falls back to a 10-city mock so the backend stays runnable
during fresh checkouts.

The Parquet schema mirrors `schemas.PlaceResult` plus two list-of-float
columns (`history_monthly_nw`, `forecast_monthly_nw`) for the time-series tool.
"""
from __future__ import annotations

import os
import random
from pathlib import Path
from typing import Literal

from .schemas import (
    Granularity,
    PlaceResult,
    TimeSeriesPoint,
    TimeSeriesResult,
)

Direction = Literal["brightening", "darkening"]

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PARQUET = REPO_ROOT / "data" / "processed" / "trends.parquet"
PARQUET_PATH = Path(os.environ.get("TREND_PARQUET_PATH") or DEFAULT_PARQUET)

# Falchi (2016) — must match scripts/ingest_seed.py.
NATURAL_NIGHT_RADIANCE = 0.171

_HISTORY_START_YEAR = 2012
_HISTORY_START_MONTH = 4

# ISO-2 country code aliases the agent might pass through `region`.
COUNTRY_ALIAS: dict[str, str] = {
    "us": "US", "usa": "US", "united states": "US", "america": "US",
    "canada": "CA", "mexico": "MX", "cuba": "CU",
    "uk": "GB", "united kingdom": "GB", "britain": "GB", "england": "GB",
    "france": "FR", "germany": "DE", "spain": "ES", "italy": "IT",
    "netherlands": "NL", "austria": "AT", "sweden": "SE", "denmark": "DK",
    "norway": "NO", "finland": "FI", "ireland": "IE", "poland": "PL",
    "czechia": "CZ", "czech republic": "CZ", "hungary": "HU",
    "russia": "RU", "turkey": "TR", "iceland": "IS", "greece": "GR",
    "egypt": "EG", "morocco": "MA", "tunisia": "TN", "algeria": "DZ",
    "kenya": "KE", "south africa": "ZA", "nigeria": "NG",
    "drc": "CD", "congo": "CD", "ethiopia": "ET", "ghana": "GH",
    "senegal": "SN",
    "saudi arabia": "SA", "uae": "AE", "qatar": "QA", "iran": "IR",
    "iraq": "IQ", "syria": "SY",
    "india": "IN", "pakistan": "PK", "bangladesh": "BD", "nepal": "NP",
    "sri lanka": "LK",
    "thailand": "TH", "singapore": "SG", "malaysia": "MY", "indonesia": "ID",
    "philippines": "PH", "vietnam": "VN",
    "china": "CN", "hong kong": "HK", "taiwan": "TW",
    "japan": "JP", "korea": "KR", "south korea": "KR",
    "australia": "AU", "new zealand": "NZ", "namibia": "NA",
    "brazil": "BR", "argentina": "AR", "chile": "CL", "peru": "PE",
    "colombia": "CO", "venezuela": "VE",
}


def _viirs_to_sqm(radiance_nw: float) -> float:
    import math
    if radiance_nw <= 0:
        return 22.0
    ratio = (radiance_nw / NATURAL_NIGHT_RADIANCE) + 1.0
    return 22.0 - 2.5 * math.log10(ratio)


# ---------------------------------------------------------------------------
# Real-data layer (Parquet → pandas)
# ---------------------------------------------------------------------------
_REAL_DF = None  # type: ignore[var-annotated]


def _load_real() -> None:
    global _REAL_DF
    if not PARQUET_PATH.exists():
        return
    try:
        import pandas as pd
        _REAL_DF = pd.read_parquet(PARQUET_PATH)
    except Exception as e:
        print(f"[data] failed to load {PARQUET_PATH}: {e}")
        _REAL_DF = None


_load_real()


def _row_to_place(row) -> PlaceResult:
    sqm = row.get("sqm_current") if hasattr(row, "get") else row["sqm_current"]
    return PlaceResult(
        name=str(row["name"]),
        country=str(row["country"]) if row["country"] else None,
        lat=float(row["lat"]),
        lon=float(row["lon"]),
        trend_pct_per_yr=float(row["trend_pct_per_yr"]),
        forecast_2035_pct_vs_2012=float(row["forecast_2035_pct_vs_2012"]),
        sqm_current=float(sqm) if sqm is not None else None,
        milky_way_lost_year=_int_or_none(row.get("milky_way_lost_year")),
        milky_way_regained_year=_int_or_none(row.get("milky_way_regained_year")),
        brightness_doubled_year=_int_or_none(row.get("brightness_doubled_year")),
        brightness_halved_year=_int_or_none(row.get("brightness_halved_year")),
    )


def _int_or_none(v) -> int | None:
    if v is None:
        return None
    try:
        import math
        if isinstance(v, float) and math.isnan(v):
            return None
        return int(v)
    except (TypeError, ValueError):
        return None


_ABBREVIATIONS = [
    ("st. ", "saint "), ("st.", "saint "),
    ("mt. ", "mount "), ("mt.", "mount "),
    ("ft. ", "fort "), ("ft.", "fort "),
]


def _normalize_place(s: str) -> str:
    out = s.lower().strip()
    for short, long_ in _ABBREVIATIONS:
        out = out.replace(short, long_)
    # Also handle bare "st louis" / "mt fuji" / "ft worth" without punctuation.
    parts = out.split()
    if parts and parts[0] == "st":
        parts[0] = "saint"
    if parts and parts[0] == "mt":
        parts[0] = "mount"
    if parts and parts[0] == "ft":
        parts[0] = "fort"
    return " ".join(parts)


def _filter_real_by_region(region: str):
    if _REAL_DF is None:
        return None
    code = COUNTRY_ALIAS.get(region.lower().strip())
    if code:
        return _REAL_DF[_REAL_DF["country"] == code]
    needle = _normalize_place(region)
    mask = _REAL_DF["name"].apply(lambda n: needle in _normalize_place(str(n)))
    return _REAL_DF[mask]


# ---------------------------------------------------------------------------
# Mock fallback (used only when the Parquet is missing)
# ---------------------------------------------------------------------------
_MOCK_PLACES: list[PlaceResult] = [
    PlaceResult(name="Lagos", country="NG", lat=6.5244, lon=3.3792,
                trend_pct_per_yr=8.7, forecast_2035_pct_vs_2012=312.0,
                milky_way_lost_year=2018, brightness_doubled_year=2022),
    PlaceResult(name="Houston", country="US", lat=29.7604, lon=-95.3698,
                trend_pct_per_yr=3.9, forecast_2035_pct_vs_2012=189.0,
                milky_way_lost_year=2017),
    PlaceResult(name="Mumbai", country="IN", lat=19.0760, lon=72.8777,
                trend_pct_per_yr=7.4, forecast_2035_pct_vs_2012=287.0,
                milky_way_lost_year=2015, brightness_doubled_year=2020),
    PlaceResult(name="Riyadh", country="SA", lat=24.7136, lon=46.6753,
                trend_pct_per_yr=9.1, forecast_2035_pct_vs_2012=341.0,
                milky_way_lost_year=2016, brightness_doubled_year=2021),
    PlaceResult(name="São Paulo", country="BR", lat=-23.5505, lon=-46.6333,
                trend_pct_per_yr=2.8, forecast_2035_pct_vs_2012=142.0,
                milky_way_lost_year=2014),
    PlaceResult(name="Cherry Springs State Park", country="US",
                lat=41.6573, lon=-77.8252,
                trend_pct_per_yr=-0.3, forecast_2035_pct_vs_2012=96.0),
    PlaceResult(name="Cairo", country="EG", lat=30.0444, lon=31.2357,
                trend_pct_per_yr=4.1, forecast_2035_pct_vs_2012=198.0,
                milky_way_lost_year=2013),
    PlaceResult(name="Manila", country="PH", lat=14.5995, lon=120.9842,
                trend_pct_per_yr=5.6, forecast_2035_pct_vs_2012=234.0,
                milky_way_lost_year=2016),
    PlaceResult(name="St. Louis", country="US", lat=38.6270, lon=-90.1994,
                trend_pct_per_yr=2.4, forecast_2035_pct_vs_2012=131.0,
                milky_way_lost_year=2019),
    PlaceResult(name="Reykjavík", country="IS", lat=64.1466, lon=-21.9426,
                trend_pct_per_yr=-0.8, forecast_2035_pct_vs_2012=88.0,
                brightness_halved_year=2021),
]

# ---------------------------------------------------------------------------
# Public API — same signatures the tool dispatcher in tools.py calls.
# ---------------------------------------------------------------------------


def dark_sky_locations(
    n: int = 10,
    region: str | None = None,
    min_sqm: float = 19.5,
) -> list[PlaceResult]:
    """
    Places where the night sky is still meaningfully dark — SQM ≥ 19.5
    (Bortle 4-5, "rural / dark suburban"). Default threshold is 19.5 rather
    than the strict 21.0 because the dataset's Falchi-derived SQM caps
    around 20.3 even for pristine reserves; 19.5 surfaces the genuinely
    dark places (observatories, dark-sky reserves) without false negatives.
    Sorted by darkest sky first.
    """
    if _REAL_DF is not None:
        df = _REAL_DF
        global_aliases = {"", "global", "world", "earth", "everywhere", "anywhere"}
        if region and region.lower().strip() not in global_aliases:
            filtered = _filter_real_by_region(region)
            if filtered is None or filtered.empty:
                return []
            df = filtered
        df = df[df["sqm_current"] >= min_sqm]
        if df.empty:
            return []
        df = df.sort_values("sqm_current", ascending=False).head(n)
        return [_row_to_place(r) for _, r in df.iterrows()]

    # Mock fallback: filter the 10-city mock by computed SQM.
    candidates = list(_MOCK_PLACES)
    if region:
        code = COUNTRY_ALIAS.get(region.lower().strip())
        if code:
            candidates = [p for p in candidates if p.country == code]
    # Mock places don't carry sqm; estimate from trend as a stand-in.
    return [p for p in candidates if p.trend_pct_per_yr < 0][:n]


def top_changers(
    direction: Direction,
    n: int = 5,
    scope_country: str | None = None,
    granularity: Granularity = "place",
) -> list[PlaceResult]:
    if _REAL_DF is not None:
        df = _REAL_DF
        if scope_country:
            code = COUNTRY_ALIAS.get(scope_country.lower().strip(), scope_country.upper())
            df = df[df["country"] == code]
        ascending = direction == "darkening"
        df = df.sort_values("trend_pct_per_yr", ascending=ascending).head(n)
        return [_row_to_place(r) for _, r in df.iterrows()]

    filtered = [p for p in _MOCK_PLACES if not scope_country or p.country == scope_country]
    reverse = direction == "brightening"
    ranked = sorted(filtered, key=lambda p: p.trend_pct_per_yr, reverse=reverse)
    return ranked[:n]


def query_region(
    region: str,
    granularity: Granularity = "place",
    n: int = 5,
) -> list[PlaceResult]:
    if _REAL_DF is not None:
        df = _filter_real_by_region(region)
        if df is None or df.empty:
            return []
        df = df.sort_values("trend_pct_per_yr", ascending=False).head(n)
        return [_row_to_place(r) for _, r in df.iterrows()]

    region_lower = region.lower().strip()
    code = COUNTRY_ALIAS.get(region_lower)
    if code:
        matches = [p for p in _MOCK_PLACES if p.country == code]
        return matches[:n]
    matches = [p for p in _MOCK_PLACES if region_lower in p.name.lower()]
    return matches[:n]


def point_timeseries(lat: float, lon: float, granularity: Granularity = "place") -> TimeSeriesResult:
    if _REAL_DF is not None and not _REAL_DF.empty:
        df = _REAL_DF
        squared = (df["lat"] - lat) ** 2 + (df["lon"] - lon) ** 2
        idx = squared.idxmin()
        row = df.loc[idx]
        place = _row_to_place(row)
        history = _expand_monthly(row["history_monthly_nw"], _HISTORY_START_YEAR, _HISTORY_START_MONTH)
        forecast_start_month_idx = len(history)
        forecast_start_year = _HISTORY_START_YEAR + (
            _HISTORY_START_MONTH - 1 + forecast_start_month_idx
        ) // 12
        forecast_start_month = ((_HISTORY_START_MONTH - 1 + forecast_start_month_idx) % 12) + 1
        forecast = _expand_monthly(
            row["forecast_monthly_nw"], forecast_start_year, forecast_start_month
        )
        confidence = "high" if abs(place.trend_pct_per_yr) > 2 else "medium"
        return TimeSeriesResult(
            place=place,
            history=history,
            forecast=forecast,
            forecast_confidence=confidence,
        )

    # Mock fallback — synthesize a plausible series.
    closest = min(_MOCK_PLACES, key=lambda p: (p.lat - lat) ** 2 + (p.lon - lon) ** 2)
    rng = random.Random(int((closest.lat * 1000) + (closest.lon * 1000)))
    base = 5.0 + rng.random() * 10
    slope_per_month = (closest.trend_pct_per_yr / 100) / 12
    history: list[TimeSeriesPoint] = []
    for year_idx in range(13):
        for month in range(1, 13):
            if year_idx == 12 and month > 6:
                break
            t = year_idx * 12 + month
            radiance = base * (1 + slope_per_month) ** t + rng.gauss(0, 0.3)
            history.append(TimeSeriesPoint(
                year=2012 + year_idx, month=month,
                radiance_nw=round(max(0.1, radiance), 3),
                sqm_estimated=round(_viirs_to_sqm(max(0.1, radiance)), 2),
            ))
    last = history[-1]
    forecast: list[TimeSeriesPoint] = []
    for years_ahead in range(1, 11):
        year = 2025 + years_ahead - 1
        for month in range(1, 13):
            t = years_ahead * 12 + month
            projected = last.radiance_nw * (1 + slope_per_month) ** t
            forecast.append(TimeSeriesPoint(
                year=year, month=month,
                radiance_nw=round(projected, 3),
                sqm_estimated=round(_viirs_to_sqm(projected), 2),
            ))
    confidence = "high" if abs(closest.trend_pct_per_yr) > 2 else "medium"
    return TimeSeriesResult(
        place=closest, history=history, forecast=forecast, forecast_confidence=confidence,
    )


def _expand_monthly(radiances, start_year: int, start_month: int) -> list[TimeSeriesPoint]:
    points: list[TimeSeriesPoint] = []
    for i, r in enumerate(radiances):
        month_total = (start_month - 1) + i
        year = start_year + month_total // 12
        month = (month_total % 12) + 1
        rf = float(r)
        points.append(TimeSeriesPoint(
            year=year, month=month,
            radiance_nw=round(rf, 3),
            sqm_estimated=round(_viirs_to_sqm(rf), 2),
        ))
    return points


def milestones_in_region(
    region: str,
    milestone_type: Literal["milky_way_lost", "brightness_doubled", "brightness_halved"],
    since_year: int | None = None,
) -> list[PlaceResult]:
    field_map = {
        "milky_way_lost": "milky_way_lost_year",
        "brightness_doubled": "brightness_doubled_year",
        "brightness_halved": "brightness_halved_year",
    }
    field = field_map[milestone_type]

    if _REAL_DF is not None:
        df = _filter_real_by_region(region)
        if df is None or df.empty:
            return []
        df = df[df[field].notna()]
        if since_year is not None:
            df = df[df[field] >= since_year]
        df = df.sort_values(field)
        return [_row_to_place(r) for _, r in df.iterrows()]

    matches = query_region(region, n=100)
    out = []
    for p in matches:
        year = {
            "milky_way_lost": p.milky_way_lost_year,
            "brightness_doubled": p.brightness_doubled_year,
            "brightness_halved": p.brightness_halved_year,
        }[milestone_type]
        if year is not None and (since_year is None or year >= since_year):
            out.append(p)
    return out


def compare_regions(region_a: str, region_b: str, granularity: Granularity = "place") -> dict:
    a = query_region(region_a, n=20)
    b = query_region(region_b, n=20)

    def summarize(places: list[PlaceResult], label: str) -> dict:
        if not places:
            return {
                "region": label,
                "data_status": "no_data",
                "note": f"No data available for {label} in the current dataset.",
                "places": [],
            }
        return {
            "region": label,
            "data_status": "ok",
            "avg_trend_pct_per_yr": round(sum(p.trend_pct_per_yr for p in places) / len(places), 2),
            "milky_way_lost_count": sum(1 for p in places if p.milky_way_lost_year),
            "places_in_data": len(places),
            "places": places[:5],
        }

    return {"a": summarize(a, region_a), "b": summarize(b, region_b)}


# Debug helper — exposed for the /api/health endpoint to confirm which source is live.
def data_source() -> dict:
    return {
        "real_data_loaded": _REAL_DF is not None,
        "parquet_path": str(PARQUET_PATH),
        "row_count": int(len(_REAL_DF)) if _REAL_DF is not None else 0,
    }
