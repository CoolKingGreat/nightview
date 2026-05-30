"""
Build the real-data Parquet from data/raw/cities_seed.csv.

Each row carries a *real* trend slope from published VIIRS literature. This
script projects that slope forward and backward to generate the monthly time
series the backend needs, computes the Prophet-shaped forecast analytically
(simple compound-growth since trends are monotonic for the seed set), runs the
Falchi (2016) VIIRS-DNB → SQM conversion to detect Milky Way-visibility
milestones, and writes a Parquet keyed by city.

Usage:
    python scripts/ingest_seed.py                 # default paths
    python scripts/ingest_seed.py --input X --output Y

This is the v0 path so the live demo runs against real cities + real trend
rates. The production path (per-pixel VIIRS via Google Earth Engine) lives in
scripts/ingest_gee.py and replaces this output when run.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = REPO_ROOT / "data" / "raw" / "cities_seed.csv"
DEFAULT_OUTPUT = REPO_ROOT / "data" / "processed" / "trends.parquet"

# Start of the VIIRS DNB record (NPP launched late 2011, useful data from 2012-04).
START_YEAR = 2012
START_MONTH = 4

# Generate history through the current month-equivalent (2025-04 → ~156 months).
HISTORY_MONTHS = 13 * 12  # 156 months: 2012-04 through 2025-03
FORECAST_MONTHS = 10 * 12  # 120 months: 2025-04 through 2035-03

# Falchi et al. (2016) "World Atlas of Artificial Night Sky Brightness" approximation.
# Natural-sky zenith radiance ≈ 0.171 nW/cm²/sr; SQM 22.0 ≈ pristine.
NATURAL_NIGHT_RADIANCE = 0.171
MILKY_WAY_THRESHOLD_SQM = 21.0


def viirs_to_sqm(radiance_nw: float) -> float:
    """Approximate VIIRS DNB radiance → zenith SQM (mag/arcsec²)."""
    if radiance_nw <= 0:
        return 22.0
    ratio = (radiance_nw / NATURAL_NIGHT_RADIANCE) + 1.0
    return 22.0 - 2.5 * math.log10(ratio)


def monthly_series(baseline: float, trend_pct_per_yr: float, n_months: int) -> list[float]:
    """Compound monthly growth from baseline. baseline expressed at t=0."""
    if trend_pct_per_yr == 0:
        return [baseline] * n_months
    monthly_rate = (1 + trend_pct_per_yr / 100.0) ** (1 / 12.0) - 1
    return [baseline * (1 + monthly_rate) ** i for i in range(n_months)]


def find_first_year(series: list[float], start_year: int, start_month: int, predicate) -> int | None:
    for i, value in enumerate(series):
        if predicate(value):
            return start_year + (start_month - 1 + i) // 12
    return None


def process(input_path: Path, output_path: Path) -> int:
    cities = pd.read_csv(input_path)
    records = []

    for _, city in cities.iterrows():
        baseline = float(city["baseline_radiance_nw"])
        trend = float(city["trend_pct_per_yr"])

        history = monthly_series(baseline, trend, HISTORY_MONTHS)
        forecast = monthly_series(history[-1], trend, FORECAST_MONTHS)

        sqm_series = [viirs_to_sqm(r) for r in history + forecast]

        milky_way_lost_year = find_first_year(
            sqm_series, START_YEAR, START_MONTH, lambda sqm: sqm < MILKY_WAY_THRESHOLD_SQM
        )
        # If the baseline is already below threshold, "lost" is pre-record; null it.
        if milky_way_lost_year == START_YEAR and viirs_to_sqm(baseline) < MILKY_WAY_THRESHOLD_SQM:
            milky_way_lost_year = None

        all_radiance = history + forecast
        brightness_doubled_year = find_first_year(
            all_radiance, START_YEAR, START_MONTH, lambda r: r >= 2.0 * baseline
        )
        brightness_halved_year = find_first_year(
            all_radiance, START_YEAR, START_MONTH, lambda r: r <= 0.5 * baseline
        )

        # Milky Way recovery: only relevant if it was lost AND trend is now negative;
        # for the seed set we leave it null (real recoveries are rare).
        milky_way_regained_year = None

        forecast_2035_pct_vs_2012 = (forecast[-1] / baseline) * 100.0

        records.append({
            "name": str(city["name"]),
            "country": str(city["country"]),
            "lat": float(city["lat"]),
            "lon": float(city["lon"]),
            "population_m": float(city["population_m"]),
            "baseline_radiance_nw": baseline,
            "trend_pct_per_yr": trend,
            "sqm_current": viirs_to_sqm(history[-1]),
            "forecast_2035_pct_vs_2012": forecast_2035_pct_vs_2012,
            "milky_way_lost_year": milky_way_lost_year,
            "milky_way_regained_year": milky_way_regained_year,
            "brightness_doubled_year": brightness_doubled_year,
            "brightness_halved_year": brightness_halved_year,
            "history_monthly_nw": history,
            "forecast_monthly_nw": forecast,
        })

    df = pd.DataFrame(records)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output_path, compression="snappy")
    return len(df)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Nightview trends Parquet from the curated seed CSV.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    n = process(args.input, args.output)
    print(f"[ingest_seed] wrote {n} cities → {args.output.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
