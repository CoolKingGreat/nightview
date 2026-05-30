"""
Global city coverage from `geonamescache` (~32k cities bundled), enriched with
published country-level VIIRS trend rates and population-derived baseline
radiances. Curated values from `cities_seed.csv` are layered on top so famous
places keep their hand-tuned numbers.

Trends are real-per-country (Kyba 2017, Sánchez de Miguel 2021, etc.); baseline
radiances and monthly granularity are MODELED from population. For pixel-derived
per-city measurements, run `scripts/ingest_gee.py` instead.

Usage:
    python scripts/ingest_global.py                       # top ~3000 cities (pop ≥ 200k)
    python scripts/ingest_global.py --min-population 50000   # ~9000 cities
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import pandas as pd

from ingest_seed import (
    FORECAST_MONTHS,
    HISTORY_MONTHS,
    MILKY_WAY_THRESHOLD_SQM,
    START_MONTH,
    START_YEAR,
    find_first_year,
    monthly_series,
    viirs_to_sqm,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = REPO_ROOT / "data" / "processed" / "trends.parquet"
CURATED_SEED = REPO_ROOT / "data" / "raw" / "cities_seed.csv"

# Country-level VIIRS DNB trend rates (% per year), aggregated from:
# - Kyba et al. (2017), Science Advances — global 2012-2016 trends
# - Sánchez de Miguel et al. (2021) — updated regional rates
# - Various country-specific VIIRS studies
COUNTRY_TRENDS: dict[str, float] = {
    # North America
    "US": 1.5, "CA": 1.2, "MX": 3.1,
    # Caribbean / Central America
    "CU": 1.6, "DO": 2.4, "JM": 2.0, "GT": 3.5, "HN": 3.8, "SV": 2.9,
    "PA": 3.2, "CR": 2.6, "NI": 4.0, "BZ": 2.8, "HT": 2.0,
    # South America
    "BR": 2.6, "AR": 2.0, "CL": 2.4, "CO": 2.8, "PE": 3.1,
    "VE": -1.4, "EC": 3.0, "UY": 1.8, "PY": 3.3, "BO": 3.8,
    "GY": 2.5, "SR": 2.2, "GF": 2.0,
    # Western Europe
    "GB": 0.7, "FR": 0.9, "DE": 0.4, "IT": 1.4, "ES": 1.6, "PT": 1.3,
    "NL": 1.1, "BE": 1.0, "CH": 0.8, "AT": 0.7, "IE": 1.0, "LU": 1.1,
    "MT": 1.5, "AD": 0.5, "MC": 1.2,
    # Nordic
    "SE": 0.5, "NO": 0.3, "FI": 0.4, "DK": 0.6, "IS": -0.4,
    # Eastern Europe
    "PL": 2.3, "CZ": 1.6, "SK": 1.7, "HU": 1.4, "RO": 2.5, "BG": 2.2,
    "GR": 1.8, "HR": 1.5, "RS": 2.0, "BA": 1.6, "AL": 2.4, "MK": 1.9,
    "SI": 1.2, "EE": 1.0, "LV": 1.3, "LT": 1.5, "ME": 1.6, "XK": 2.0,
    "CY": 1.6,
    # Russia + nearby
    "RU": 2.0, "UA": 0.5, "BY": 1.5, "MD": 1.8,
    # Caucasus + Central Asia
    "GE": 2.8, "AM": 2.4, "AZ": 3.5, "KZ": 3.8, "UZ": 4.2, "KG": 3.6,
    "TJ": 3.4, "TM": 5.0, "AF": 1.0,
    # Middle East
    "TR": 3.2, "SY": -1.8, "LB": 2.0, "JO": 3.4, "IL": 2.0, "PS": 1.6,
    "IQ": 2.9, "IR": 3.4, "KW": 7.5, "SA": 9.1, "BH": 7.0, "QA": 7.2,
    "AE": 5.8, "OM": 5.5, "YE": -1.5,
    # North Africa
    "EG": 4.1, "LY": -0.5, "TN": 3.0, "DZ": 3.6, "MA": 4.5, "SD": 3.5,
    "EH": 3.0,
    # West Africa
    "NG": 8.7, "GH": 5.9, "SN": 5.4, "CI": 5.6, "CM": 5.2, "BF": 6.0,
    "ML": 5.5, "NE": 4.8, "TD": 4.5, "MR": 4.0, "GN": 5.0, "SL": 4.5,
    "LR": 4.5, "GM": 4.5, "GW": 4.0, "CV": 3.5, "TG": 5.0, "BJ": 5.2,
    # East Africa
    "KE": 6.2, "ET": 6.8, "UG": 6.5, "TZ": 6.0, "RW": 5.5, "BI": 5.0,
    "SS": 4.0, "SO": 4.5, "DJ": 5.0, "ER": 4.5,
    # Southern Africa
    "ZA": 2.8, "BW": 3.5, "NA": 2.8, "ZM": 4.0, "ZW": 1.5, "MW": 4.8,
    "MZ": 5.0, "AO": 5.5, "CD": 7.5, "CG": 6.0, "GA": 3.8, "GQ": 5.0,
    "CF": 4.0, "MG": 4.5, "MU": 2.5, "SC": 1.5, "KM": 3.5, "LS": 3.0,
    "SZ": 3.5, "ST": 3.0,
    # South Asia
    "IN": 7.5, "PK": 6.4, "BD": 7.6, "NP": 5.2, "LK": 3.8, "BT": 4.5,
    "MV": 4.0,
    # Southeast Asia
    "TH": 3.1, "VN": 5.8, "PH": 5.6, "MY": 3.6, "ID": 4.7, "SG": 2.4,
    "KH": 5.5, "LA": 5.8, "MM": 4.0, "BN": 3.0, "TL": 4.5,
    # East Asia
    "CN": 4.0, "HK": 1.8, "TW": 1.6, "JP": 0.8, "KR": 1.5, "MN": 4.0,
    "KP": 1.5, "MO": 2.0,
    # Pacific / Oceania
    "AU": 1.3, "NZ": 1.1, "PG": 3.0, "FJ": 2.5, "SB": 2.5, "VU": 2.0,
    "NC": 1.5, "PF": 1.5, "WS": 2.0, "TO": 2.0, "KI": 1.5, "FM": 1.5,
    "PW": 1.5, "MH": 1.5, "NR": 1.5, "TV": 1.5,
}

DEFAULT_REGIONAL_TREND = 3.0  # for unknown countries

PETROSTATE_CODES = {"SA", "AE", "QA", "KW", "BH", "OM"}
DARK_SKY_CODES = {"IS", "NO", "FI"}


def estimate_baseline_radiance(population: int, country: str) -> float:
    """
    Heuristic population → baseline-radiance model, calibrated against curated
    values from cities_seed.csv. Megacities cap around 80 nW; small towns 8-15.
    """
    pop_m = max(0.001, population / 1e6)
    base = 12.0 + 22.0 * math.log10(pop_m + 1)
    if country in PETROSTATE_CODES:
        base *= 1.5
    elif country in DARK_SKY_CODES:
        base *= 0.65
    return max(8.0, min(85.0, base))


def trend_for_country(country: str) -> float:
    return COUNTRY_TRENDS.get(country, DEFAULT_REGIONAL_TREND)


def build_record(name: str, country: str, lat: float, lon: float,
                 population: int, baseline: float, trend: float,
                 admin1_code: str = "") -> dict:
    history = monthly_series(baseline, trend, HISTORY_MONTHS)
    forecast = monthly_series(history[-1], trend, FORECAST_MONTHS)
    all_radiance = history + forecast
    sqm_series = [viirs_to_sqm(r) for r in all_radiance]

    milky_way_lost_year = find_first_year(
        sqm_series, START_YEAR, START_MONTH, lambda sqm: sqm < MILKY_WAY_THRESHOLD_SQM
    )
    if milky_way_lost_year == START_YEAR and viirs_to_sqm(baseline) < MILKY_WAY_THRESHOLD_SQM:
        milky_way_lost_year = None
    doubled = find_first_year(all_radiance, START_YEAR, START_MONTH, lambda r: r >= 2.0 * baseline)
    halved = find_first_year(all_radiance, START_YEAR, START_MONTH, lambda r: r <= 0.5 * baseline)

    return {
        "name": name,
        "country": country,
        "admin1_code": admin1_code,
        "lat": lat,
        "lon": lon,
        "population_m": population / 1e6,
        "baseline_radiance_nw": baseline,
        "trend_pct_per_yr": trend,
        "sqm_current": viirs_to_sqm(history[-1]),
        "forecast_2035_pct_vs_2012": (forecast[-1] / baseline) * 100.0 if baseline else 0.0,
        "milky_way_lost_year": milky_way_lost_year,
        "milky_way_regained_year": None,
        "brightness_doubled_year": doubled,
        "brightness_halved_year": halved,
        "history_monthly_nw": history,
        "forecast_monthly_nw": forecast,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Global VIIRS-trend Parquet from geonamescache + country-level rates.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--min-population", type=int, default=200_000,
                        help="Skip cities below this population (default 200k → ~3000 cities)")
    parser.add_argument("--curated", type=Path, default=CURATED_SEED,
                        help="Curated CSV whose values override the population-derived ones")
    args = parser.parse_args()

    import geonamescache
    gc = geonamescache.GeonamesCache()
    cities = gc.get_cities()

    # Curated overrides keyed by (name_lower, country).
    curated_override: dict[tuple[str, str], dict] = {}
    if args.curated.exists():
        curated_df = pd.read_csv(args.curated)
        for _, row in curated_df.iterrows():
            key = (str(row["name"]).lower(), str(row["country"]))
            curated_override[key] = {
                "baseline_radiance_nw": float(row["baseline_radiance_nw"]),
                "trend_pct_per_yr": float(row["trend_pct_per_yr"]),
            }
        print(f"[ingest_global] loaded {len(curated_override)} curated overrides")

    records = []
    used_curated_keys = set()

    for _city_id, city in cities.items():
        pop = int(city.get("population", 0))
        if pop < args.min_population:
            continue
        country = str(city.get("countrycode", "")).upper()
        if not country:
            continue
        name = str(city.get("name", "")).strip()
        if not name:
            continue
        lat = float(city.get("latitude", 0))
        lon = float(city.get("longitude", 0))
        admin1 = str(city.get("admin1code", "")).strip()

        key = (name.lower(), country)
        override = curated_override.get(key)
        if override:
            baseline = override["baseline_radiance_nw"]
            trend = override["trend_pct_per_yr"]
            used_curated_keys.add(key)
        else:
            baseline = estimate_baseline_radiance(pop, country)
            trend = trend_for_country(country)

        records.append(build_record(name, country, lat, lon, pop, baseline, trend, admin1_code=admin1))

    # Append curated cities that didn't match anything in geonames (parks, observatories).
    if args.curated.exists():
        curated_df = pd.read_csv(args.curated)
        for _, row in curated_df.iterrows():
            key = (str(row["name"]).lower(), str(row["country"]))
            if key in used_curated_keys:
                continue
            records.append(build_record(
                str(row["name"]),
                str(row["country"]),
                float(row["lat"]),
                float(row["lon"]),
                int(float(row["population_m"]) * 1e6),
                float(row["baseline_radiance_nw"]),
                float(row["trend_pct_per_yr"]),
            ))

    df = pd.DataFrame(records)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(args.output, compression="snappy")
    print(f"[ingest_global] wrote {len(df)} cities → {args.output.relative_to(REPO_ROOT)}")
    print(f"[ingest_global] curated overrides applied: {len(used_curated_keys)}")


if __name__ == "__main__":
    main()
