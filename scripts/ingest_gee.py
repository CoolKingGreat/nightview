"""
Production VIIRS ingestion via Google Earth Engine.

Replaces the seed Parquet with per-pixel-derived measurements at any scale.
The seed script only carries published trend slopes for ~100 well-known cities;
this script samples NASA's monthly VIIRS Black Marble (VNP46A2) at every city
in a configurable list and computes the trend, forecast, and milestones from
the actual pixel time series.

PREREQUISITES
=============
1. Free Google Earth Engine account → https://earthengine.google.com/signup/
2. Install: `pip install earthengine-api`
3. Authenticate: `earthengine authenticate` (opens browser; one-time)

OR for headless use (CI, server): create a service account in Google Cloud
Console, grant it the Earth Engine viewer role, download the JSON key, and
set `GEE_SERVICE_ACCOUNT_JSON` in `.env`.

USAGE
=====
    # Default: all cities from data/raw/cities_seed.csv
    python scripts/ingest_gee.py

    # Custom city list + output
    python scripts/ingest_gee.py --cities data/raw/cities_extended.csv \\
        --output data/processed/trends.parquet

    # Smaller subset for testing
    python scripts/ingest_gee.py --limit 10

WHAT IT DOES
============
For each city: queries `NOAA/VIIRS/DNB/MONTHLY_V1` (the public VIIRS DNB
monthly composite collection) over 2012-04 → present, takes the median
radiance within a 10km buffer, fits an OLS trend on the log-radiance series
(equivalent to compound growth %/yr), runs Prophet for the 10-yr forecast,
and detects milestone-crossing years.

ALL DERIVED VALUES ARE REAL, NOT INTERPOLATED.

This file is NOT run by the seed script. Once you've run it once and the
output Parquet is in place, the backend automatically uses it.
"""
from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CITIES = REPO_ROOT / "data" / "raw" / "cities_seed.csv"
DEFAULT_OUTPUT = REPO_ROOT / "data" / "processed" / "trends.parquet"
SAMPLE_BUFFER_M = 10_000  # 10km radius median around each city centroid

NATURAL_NIGHT_RADIANCE = 0.171  # Falchi (2016) — matches scripts/ingest_seed.py
MILKY_WAY_THRESHOLD_SQM = 21.0


def viirs_to_sqm(radiance_nw: float) -> float:
    if radiance_nw <= 0:
        return 22.0
    return 22.0 - 2.5 * math.log10((radiance_nw / NATURAL_NIGHT_RADIANCE) + 1.0)


def authenticate_gee():
    """Authenticate with Google Earth Engine. Service-account path takes precedence."""
    try:
        import ee
    except ImportError:
        sys.exit("earthengine-api not installed. `pip install earthengine-api`.")

    sa_json = os.environ.get("GEE_SERVICE_ACCOUNT_JSON")
    if sa_json and Path(sa_json).exists():
        creds = ee.ServiceAccountCredentials(email=None, key_file=sa_json)
        ee.Initialize(credentials=creds)
        return ee

    try:
        ee.Initialize()
    except Exception:
        print("[ingest_gee] no credentials cached — running interactive auth flow.")
        ee.Authenticate()
        ee.Initialize()
    return ee


def sample_city(ee, city: dict) -> list[tuple[str, float]]:
    """Return [(yyyy-mm, radiance_nw), ...] for one city over the VIIRS DNB record."""
    point = ee.Geometry.Point([city["lon"], city["lat"]])
    region = point.buffer(SAMPLE_BUFFER_M)
    collection = (
        ee.ImageCollection("NOAA/VIIRS/DNB/MONTHLY_V1")
        .filterDate("2012-04-01", "2025-04-01")
        .select("avg_rad")
    )

    def reduce_one(image):
        stat = image.reduceRegion(
            reducer=ee.Reducer.median(),
            geometry=region,
            scale=500,
            maxPixels=1e8,
        )
        return ee.Feature(None, {
            "month": image.date().format("YYYY-MM"),
            "rad": stat.get("avg_rad"),
        })

    features = collection.map(reduce_one).getInfo()
    out: list[tuple[str, float]] = []
    for f in features["features"]:
        props = f["properties"]
        if props.get("rad") is None:
            continue
        out.append((props["month"], float(props["rad"])))
    return out


def fit_trend(series: list[tuple[str, float]]) -> float:
    """OLS on log-radiance vs time (months). Returns compound %-per-year."""
    if len(series) < 12:
        return 0.0
    n = len(series)
    xs = list(range(n))
    ys = [math.log(max(v, 0.01)) for _, v in series]
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
    den = sum((xs[i] - mean_x) ** 2 for i in range(n))
    slope_per_month = num / den if den else 0.0
    return ((math.exp(slope_per_month) ** 12) - 1.0) * 100.0


def forecast_prophet(series: list[tuple[str, float]], horizon_months: int = 120) -> list[float]:
    """Prophet forecast. Falls back to log-linear extrapolation if Prophet unavailable."""
    try:
        from prophet import Prophet
        import pandas as pd
        df = pd.DataFrame({
            "ds": [s[0] + "-15" for s in series],
            "y": [s[1] for s in series],
        })
        df["ds"] = pd.to_datetime(df["ds"])
        m = Prophet(yearly_seasonality=True, weekly_seasonality=False, daily_seasonality=False)
        m.fit(df)
        future = m.make_future_dataframe(periods=horizon_months, freq="MS")
        forecast = m.predict(future)
        tail = forecast["yhat"].tail(horizon_months).tolist()
        return [max(0.0, v) for v in tail]
    except Exception as e:
        print(f"  [forecast] Prophet unavailable ({e}); using log-linear extrapolation")
        slope_pct_yr = fit_trend(series)
        if not series:
            return [0.0] * horizon_months
        last = series[-1][1]
        monthly_rate = (1 + slope_pct_yr / 100.0) ** (1 / 12.0) - 1
        return [last * (1 + monthly_rate) ** (i + 1) for i in range(horizon_months)]


def find_first_year(series: list[float], start_year: int, start_month: int, predicate) -> int | None:
    for i, v in enumerate(series):
        if predicate(v):
            return start_year + (start_month - 1 + i) // 12
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Real VIIRS DNB ingestion via Google Earth Engine.")
    parser.add_argument("--cities", type=Path, default=DEFAULT_CITIES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N cities (testing)")
    args = parser.parse_args()

    import pandas as pd
    cities = pd.read_csv(args.cities)
    if args.limit:
        cities = cities.head(args.limit)

    print(f"[ingest_gee] authenticating with Earth Engine…")
    ee = authenticate_gee()
    print(f"[ingest_gee] processing {len(cities)} cities (buffer {SAMPLE_BUFFER_M//1000}km median)…")

    records = []
    for i, (_, city) in enumerate(cities.iterrows(), start=1):
        try:
            series = sample_city(ee, city.to_dict())
            if len(series) < 24:
                print(f"  [{i}/{len(cities)}] {city['name']}: insufficient data ({len(series)} months)")
                continue
            trend = fit_trend(series)
            baseline = sum(v for _, v in series[:12]) / 12  # first-year mean
            radiance_history = [v for _, v in series]
            forecast = forecast_prophet(series)
            all_rad = radiance_history + forecast
            all_sqm = [viirs_to_sqm(r) for r in all_rad]

            milky_way_lost = find_first_year(all_sqm, 2012, 4, lambda sqm: sqm < MILKY_WAY_THRESHOLD_SQM)
            if milky_way_lost == 2012 and viirs_to_sqm(baseline) < MILKY_WAY_THRESHOLD_SQM:
                milky_way_lost = None
            doubled = find_first_year(all_rad, 2012, 4, lambda r: r >= 2.0 * baseline)
            halved = find_first_year(all_rad, 2012, 4, lambda r: r <= 0.5 * baseline)

            records.append({
                "name": city["name"],
                "country": city["country"],
                "lat": float(city["lat"]),
                "lon": float(city["lon"]),
                "population_m": float(city.get("population_m", 0.0)),
                "baseline_radiance_nw": float(baseline),
                "trend_pct_per_yr": float(trend),
                "sqm_current": viirs_to_sqm(radiance_history[-1]),
                "forecast_2035_pct_vs_2012": (forecast[-1] / baseline) * 100.0 if baseline else 0.0,
                "milky_way_lost_year": milky_way_lost,
                "milky_way_regained_year": None,
                "brightness_doubled_year": doubled,
                "brightness_halved_year": halved,
                "history_monthly_nw": radiance_history,
                "forecast_monthly_nw": forecast,
            })
            print(f"  [{i}/{len(cities)}] {city['name']}: trend {trend:+.2f}%/yr, {len(series)} months")
        except Exception as e:
            print(f"  [{i}/{len(cities)}] {city['name']}: FAILED — {e}")

    df = pd.DataFrame(records)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(args.output, compression="snappy")
    print(f"\n[ingest_gee] wrote {len(df)} cities → {args.output.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
