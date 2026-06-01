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
    DarkSkyPlace,
    Granularity,
    PlaceResult,
    SkyVisibility,
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

# Sub-national subdivision aliases. Keyed by lowercased subdivision name,
# value is (country_iso2, admin1_code_in_geonames). Covers US states + the
# largest countries' major subdivisions. admin1 codes match what
# scripts/ingest_global.py stores in the parquet's admin1_code column.
#
# US uses the 2-letter postal code; India/Brazil/CN/CA/AU use numeric codes.
SUBDIVISION_ALIAS: dict[str, tuple[str, str]] = {
    # India — 28 states + 8 UTs
    "andhra pradesh": ("IN", "02"),
    "arunachal pradesh": ("IN", "30"),
    "assam": ("IN", "03"),
    "bihar": ("IN", "34"),
    "chandigarh": ("IN", "05"),
    "chhattisgarh": ("IN", "37"),
    "dadra and nagar haveli": ("IN", "39"),
    "daman and diu": ("IN", "38"),
    "delhi": ("IN", "07"),
    "new delhi": ("IN", "07"),
    "goa": ("IN", "33"),
    "gujarat": ("IN", "09"),
    "haryana": ("IN", "10"),
    "himachal pradesh": ("IN", "11"),
    "jammu and kashmir": ("IN", "12"),
    "j&k": ("IN", "12"),
    "jharkhand": ("IN", "36"),
    "karnataka": ("IN", "19"),
    "kerala": ("IN", "13"),
    "ladakh": ("IN", "42"),
    "lakshadweep": ("IN", "14"),
    "madhya pradesh": ("IN", "35"),
    "maharashtra": ("IN", "16"),
    "manipur": ("IN", "17"),
    "meghalaya": ("IN", "18"),
    "mizoram": ("IN", "31"),
    "nagaland": ("IN", "20"),
    "odisha": ("IN", "21"),
    "orissa": ("IN", "21"),
    "puducherry": ("IN", "22"),
    "pondicherry": ("IN", "22"),
    "punjab": ("IN", "23"),
    "rajasthan": ("IN", "24"),
    "sikkim": ("IN", "29"),
    "tamil nadu": ("IN", "25"),
    "telangana": ("IN", "40"),
    "tripura": ("IN", "26"),
    "uttar pradesh": ("IN", "36"),
    "uttarakhand": ("IN", "39"),
    "uttaranchal": ("IN", "39"),
    "west bengal": ("IN", "28"),
    "andaman and nicobar": ("IN", "01"),
    # US — 50 states + DC + PR. Postal codes.
    "alabama": ("US", "AL"), "alaska": ("US", "AK"), "arizona": ("US", "AZ"),
    "arkansas": ("US", "AR"), "california": ("US", "CA"), "colorado": ("US", "CO"),
    "connecticut": ("US", "CT"), "delaware": ("US", "DE"), "florida": ("US", "FL"),
    "georgia": ("US", "GA"), "hawaii": ("US", "HI"), "idaho": ("US", "ID"),
    "illinois": ("US", "IL"), "indiana": ("US", "IN"), "iowa": ("US", "IA"),
    "kansas": ("US", "KS"), "kentucky": ("US", "KY"), "louisiana": ("US", "LA"),
    "maine": ("US", "ME"), "maryland": ("US", "MD"), "massachusetts": ("US", "MA"),
    "michigan": ("US", "MI"), "minnesota": ("US", "MN"), "mississippi": ("US", "MS"),
    "missouri": ("US", "MO"), "montana": ("US", "MT"), "nebraska": ("US", "NE"),
    "nevada": ("US", "NV"), "new hampshire": ("US", "NH"), "new jersey": ("US", "NJ"),
    "new mexico": ("US", "NM"), "new york": ("US", "NY"), "north carolina": ("US", "NC"),
    "north dakota": ("US", "ND"), "ohio": ("US", "OH"), "oklahoma": ("US", "OK"),
    "oregon": ("US", "OR"), "pennsylvania": ("US", "PA"), "rhode island": ("US", "RI"),
    "south carolina": ("US", "SC"), "south dakota": ("US", "SD"), "tennessee": ("US", "TN"),
    "texas": ("US", "TX"), "utah": ("US", "UT"), "vermont": ("US", "VT"),
    "virginia": ("US", "VA"), "washington": ("US", "WA"), "west virginia": ("US", "WV"),
    "wisconsin": ("US", "WI"), "wyoming": ("US", "WY"),
    "district of columbia": ("US", "DC"), "puerto rico": ("US", "PR"),
    # Canada — 10 provinces + 3 territories
    "alberta": ("CA", "01"), "british columbia": ("CA", "02"),
    "manitoba": ("CA", "03"), "new brunswick": ("CA", "04"),
    "newfoundland and labrador": ("CA", "05"), "newfoundland": ("CA", "05"),
    "nova scotia": ("CA", "07"), "ontario": ("CA", "08"),
    "prince edward island": ("CA", "09"), "quebec": ("CA", "10"),
    "saskatchewan": ("CA", "11"), "yukon": ("CA", "12"),
    "northwest territories": ("CA", "13"), "nunavut": ("CA", "14"),
    # Australia — states + territories
    "new south wales": ("AU", "02"), "victoria": ("AU", "07"),
    "queensland": ("AU", "04"), "south australia": ("AU", "05"),
    "western australia": ("AU", "08"), "tasmania": ("AU", "06"),
    "northern territory": ("AU", "03"),
    "australian capital territory": ("AU", "01"),
    # Brazil — 26 states + DF (geonames numeric admin1)
    "acre": ("BR", "01"), "alagoas": ("BR", "02"), "amapa": ("BR", "03"),
    "amazonas": ("BR", "04"), "bahia": ("BR", "05"), "ceara": ("BR", "06"),
    "distrito federal": ("BR", "07"), "espirito santo": ("BR", "08"),
    "goias": ("BR", "29"), "maranhao": ("BR", "10"), "mato grosso": ("BR", "11"),
    "mato grosso do sul": ("BR", "11"), "minas gerais": ("BR", "15"),
    "para": ("BR", "14"), "paraiba": ("BR", "15"), "parana": ("BR", "18"),
    "pernambuco": ("BR", "17"), "piaui": ("BR", "20"),
    "rio de janeiro": ("BR", "21"), "rio grande do norte": ("BR", "22"),
    "rio grande do sul": ("BR", "23"), "rondonia": ("BR", "24"),
    "roraima": ("BR", "25"), "santa catarina": ("BR", "26"),
    "sao paulo": ("BR", "27"), "sergipe": ("BR", "28"), "tocantins": ("BR", "31"),
    # China — major provinces (numeric)
    "beijing": ("CN", "22"), "shanghai": ("CN", "23"), "tianjin": ("CN", "28"),
    "chongqing": ("CN", "33"), "guangdong": ("CN", "30"), "sichuan": ("CN", "32"),
    "jiangsu": ("CN", "04"), "zhejiang": ("CN", "02"), "shandong": ("CN", "25"),
    "henan": ("CN", "09"), "hebei": ("CN", "10"), "hunan": ("CN", "11"),
    "hubei": ("CN", "12"), "anhui": ("CN", "01"), "fujian": ("CN", "07"),
    "yunnan": ("CN", "29"), "jiangxi": ("CN", "03"), "liaoning": ("CN", "19"),
    "heilongjiang": ("CN", "08"), "shaanxi": ("CN", "26"), "shanxi": ("CN", "24"),
    "guizhou": ("CN", "18"), "gansu": ("CN", "15"), "tibet": ("CN", "14"),
    "xinjiang": ("CN", "13"), "inner mongolia": ("CN", "20"),
    "guangxi": ("CN", "16"), "ningxia": ("CN", "21"), "qinghai": ("CN", "06"),
    "hainan": ("CN", "31"), "jilin": ("CN", "05"), "taiwan": ("CN", "34"),
}


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


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


# Bortle class boundaries (zenith SQM in mag/arcsec^2). Standard Bortle (2001)
# thresholds — class number rises as the sky gets brighter.
_BORTLE_THRESHOLDS = [
    (21.99, 1),  # excellent dark — Milky Way casts visible shadows
    (21.89, 2),  # typical truly-dark
    (21.69, 3),  # rural
    (20.49, 4),  # rural / suburban transition
    (19.50, 5),  # suburban
    (18.94, 6),  # bright suburban
    (18.38, 7),  # suburban / urban
    (17.80, 8),  # city
]
# Anything below 17.80 → class 9 (inner-city).


def _sqm_to_bortle(sqm: float) -> int:
    for cutoff, cls in _BORTLE_THRESHOLDS:
        if sqm >= cutoff:
            return cls
    return 9


# Reference points for zenith SQM → naked-eye limiting magnitude. Drawn from
# Crumey (2014) "Human contrast threshold and astronomical visibility" and the
# Bortle (2001) NELM column. Linear interpolation between adjacent rows.
_NELM_TABLE = [
    (22.00, 7.6),
    (21.50, 6.8),
    (21.00, 6.3),
    (20.50, 5.9),
    (20.00, 5.5),
    (19.50, 5.2),
    (19.00, 4.8),
    (18.50, 4.4),
    (18.00, 4.0),
    (17.50, 3.6),
    (17.00, 3.2),
    (16.00, 2.5),
]


def _sqm_to_nelm(sqm: float) -> float:
    if sqm >= _NELM_TABLE[0][0]:
        return _NELM_TABLE[0][1]
    if sqm <= _NELM_TABLE[-1][0]:
        return _NELM_TABLE[-1][1]
    for (s_hi, n_hi), (s_lo, n_lo) in zip(_NELM_TABLE, _NELM_TABLE[1:]):
        if s_lo <= sqm <= s_hi:
            t = (sqm - s_lo) / (s_hi - s_lo)
            return n_lo + t * (n_hi - n_lo)
    return 5.0  # unreachable; satisfies type checker


# Curated list of well-known dark-sky destinations (parks, reserves,
# sanctuaries, observatories). Used by nearest_dark_sky_park() to surface
# a "where to escape to" suggestion in the Inspector.
_DARK_SKY_SITES: list[dict] = []
DEFAULT_DARK_SKY_CSV = REPO_ROOT / "data" / "raw" / "dark_sky_places.csv"
DARK_SKY_CSV = Path(os.environ.get("DARK_SKY_CSV_PATH") or DEFAULT_DARK_SKY_CSV)

# Don't suggest a site that's farther than this — a 6000 km drive is not a
# meaningful escape. Returns None instead.
DARK_SKY_MAX_DISTANCE_KM = 3000.0


def _load_dark_sky_sites() -> None:
    global _DARK_SKY_SITES
    if not DARK_SKY_CSV.exists():
        return
    import csv
    sites: list[dict] = []
    with DARK_SKY_CSV.open() as f:
        for row in csv.DictReader(f):
            try:
                sites.append({
                    "name": row["name"],
                    "country": row.get("country") or None,
                    "type": row["type"],
                    "lat": float(row["lat"]),
                    "lon": float(row["lon"]),
                })
            except (KeyError, ValueError):
                continue
    _DARK_SKY_SITES = sites


_load_dark_sky_sites()


# Standard amateur-astronomy expectations per Bortle class (Bortle 2001).
# Star counts are order-of-magnitude estimates of naked-eye stars visible
# under typical conditions at that class. Notable objects are commonly cited
# in Bortle's original article and amateur references.
_VISIBILITY_BY_BORTLE: dict[int, dict] = {
    1: {
        "stars_visible_estimate": "7,000+",
        "milky_way": "casts visible shadows",
        "notable_objects": [
            "M31 Andromeda Galaxy",
            "M33 Triangulum Galaxy",
            "M42 Orion Nebula",
            "M45 Pleiades",
            "zodiacal light",
            "gegenschein",
            "airglow",
        ],
    },
    2: {
        "stars_visible_estimate": "5,000–7,000",
        "milky_way": "richly structured overhead",
        "notable_objects": [
            "M31 Andromeda Galaxy",
            "M33 Triangulum (with effort)",
            "M42 Orion Nebula",
            "M45 Pleiades",
            "zodiacal light",
        ],
    },
    3: {
        "stars_visible_estimate": "3,000–5,000",
        "milky_way": "detailed except near horizon",
        "notable_objects": [
            "M31 Andromeda",
            "M42 Orion Nebula",
            "M45 Pleiades",
            "zodiacal light (spring/autumn)",
        ],
    },
    4: {
        "stars_visible_estimate": "2,000–3,000",
        "milky_way": "visible at zenith; washed-out near horizon",
        "notable_objects": [
            "M31 Andromeda (obvious)",
            "M42 Orion Nebula",
            "M45 Pleiades",
            "faint zodiacal light",
        ],
    },
    5: {
        "stars_visible_estimate": "1,500",
        "milky_way": "weak and washed-out overhead",
        "notable_objects": [
            "M31 Andromeda (with averted vision)",
            "M42 Orion Nebula",
            "M45 Pleiades",
            "bright planets",
        ],
    },
    6: {
        "stars_visible_estimate": "800",
        "milky_way": "barely visible near zenith on the clearest nights",
        "notable_objects": [
            "M31 (barely, only when high overhead)",
            "M45 Pleiades",
            "M42 Orion Nebula (faintly)",
            "bright planets",
        ],
    },
    7: {
        "stars_visible_estimate": "400–700",
        "milky_way": "not visible",
        "notable_objects": [
            "M45 Pleiades",
            "the brightest stars and major constellations",
            "planets",
        ],
    },
    8: {
        "stars_visible_estimate": "200–400",
        "milky_way": "not visible",
        "notable_objects": [
            "Orion, the Big Dipper, Cassiopeia",
            "the brightest stars (Sirius, Vega, Arcturus, Betelgeuse)",
            "planets",
            "Moon",
        ],
    },
    9: {
        "stars_visible_estimate": "50–150",
        "milky_way": "not visible",
        "notable_objects": [
            "the brightest dozen or so stars (Sirius, Vega, Arcturus)",
            "the brightest planets",
            "Moon",
        ],
    },
}


def visibility_for_bortle(bortle: int) -> SkyVisibility:
    data = _VISIBILITY_BY_BORTLE.get(bortle) or _VISIBILITY_BY_BORTLE[9]
    return SkyVisibility(
        stars_visible_estimate=data["stars_visible_estimate"],
        milky_way=data["milky_way"],
        notable_objects=data["notable_objects"],
    )


def nearest_dark_sky_park(lat: float, lon: float) -> DarkSkyPlace | None:
    if not _DARK_SKY_SITES:
        return None
    best = None
    best_d = float("inf")
    for site in _DARK_SKY_SITES:
        d = _haversine_km(lat, lon, site["lat"], site["lon"])
        if d < best_d:
            best_d = d
            best = site
    if best is None or best_d > DARK_SKY_MAX_DISTANCE_KM:
        return None
    return DarkSkyPlace(
        name=best["name"],
        country=best["country"],
        type=best["type"],
        lat=best["lat"],
        lon=best["lon"],
        distance_km=round(best_d, 0),
    )


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
    sqm_f = float(sqm) if sqm is not None else None
    lat = float(row["lat"])
    lon = float(row["lon"])
    bortle = _sqm_to_bortle(sqm_f) if sqm_f is not None else None
    return PlaceResult(
        name=str(row["name"]),
        country=str(row["country"]) if row["country"] else None,
        lat=lat,
        lon=lon,
        trend_pct_per_yr=float(row["trend_pct_per_yr"]),
        forecast_2035_pct_vs_2012=float(row["forecast_2035_pct_vs_2012"]),
        sqm_current=sqm_f,
        bortle_class=bortle,
        naked_eye_limit_mag=round(_sqm_to_nelm(sqm_f), 1) if sqm_f is not None else None,
        nearest_dark_sky=nearest_dark_sky_park(lat, lon),
        visibility=visibility_for_bortle(bortle) if bortle is not None else None,
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
    key = region.lower().strip()
    code = COUNTRY_ALIAS.get(key)
    if code:
        return _REAL_DF[_REAL_DF["country"] == code]
    # Try sub-national subdivision (state / province) before falling back to name match.
    sub = SUBDIVISION_ALIAS.get(key)
    if sub and "admin1_code" in _REAL_DF.columns:
        country, admin1 = sub
        return _REAL_DF[(_REAL_DF["country"] == country) & (_REAL_DF["admin1_code"] == admin1)]
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
        distance_km = round(_haversine_km(lat, lon, float(row["lat"]), float(row["lon"])), 1)
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
            distance_km=distance_km,
        )

    # Mock fallback — synthesize a plausible series.
    closest = min(_MOCK_PLACES, key=lambda p: (p.lat - lat) ** 2 + (p.lon - lon) ** 2)
    distance_km = round(_haversine_km(lat, lon, closest.lat, closest.lon), 1)
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
        distance_km=distance_km,
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
