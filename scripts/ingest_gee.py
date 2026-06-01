"""
Production VIIRS ingestion via Google Earth Engine.

Replaces modeled per-city values with real measured VIIRS DNB radiance from
NASA's VNP46A2 Black Marble daily product. The script MERGES INTO the
existing trends.parquet (built by ingest_global.py) — cities listed in the
input CSV get their rows overwritten with measured data and tagged
`data_source = "measured"`. All other rows in the parquet remain
modeled and untouched.

PREREQUISITES
=============
1. Free Google Earth Engine account → https://earthengine.google.com/signup/
2. Install: pip install earthengine-api
3. Authenticate once: earthengine authenticate
4. Register your GCP project for Earth Engine (noncommercial / Community tier
   is free, no billing) at
   https://console.cloud.google.com/earth-engine/configuration?project=YOUR_PROJECT_ID
5. Enable the Earth Engine API for the project (one click in the GCP console)

Pass the project ID via --project or the GEE_PROJECT_ID env var.

USAGE
=====
    # Default: every city in cities_seed.csv, merge into trends.parquet
    python scripts/ingest_gee.py --project geoproj-498104

    # Small smoke test
    python scripts/ingest_gee.py --project geoproj-498104 --limit 5

    # Custom input/output
    python scripts/ingest_gee.py --project geoproj-498104 \\
        --cities data/raw/cities_seed.csv \\
        --output data/processed/trends.parquet

WHAT IT DOES
============
For each city:
  1. Pulls NASA/VIIRS/002/VNP46A2 daily images over the 10km buffer, 2012-04
     onward, masking pixels where Mandatory_Quality_Flag != 0 (drops cloudy,
     snowy, and lunar-contaminated days).
  2. Builds a monthly median composite server-side and reduces each month to
     a single radiance value (median across the 10km buffer).
  3. Returns a clean [(YYYY-MM, radiance_nw), …] time series.
  4. Fits an OLS log-linear trend to compute %-per-year.
  5. Runs Prophet to forecast 120 months ahead. Falls back to log-linear
     extrapolation if Prophet isn't installed.
  6. Detects milestone-crossing years (Milky Way lost via SQM, brightness
     doubled / halved vs 2012 baseline).
  7. Merges the result row into the existing Parquet by name+lat+lon,
     replacing the modeled values and tagging data_source = "measured".

Cities that fail (insufficient data, GEE error) are skipped and the
existing modeled row is preserved.

ALL DERIVED VALUES ARE FROM REAL VIIRS MEASUREMENTS, NOT INTERPOLATED.
"""
from __future__ import annotations

import argparse
import math
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CITIES = REPO_ROOT / "data" / "raw" / "cities_seed.csv"
DEFAULT_OUTPUT = REPO_ROOT / "data" / "processed" / "trends.parquet"
SAMPLE_BUFFER_M = 10_000  # 10km radius median around each city centroid

NATURAL_NIGHT_RADIANCE = 0.171  # Falchi (2016) — matches scripts/ingest_seed.py
MILKY_WAY_THRESHOLD_SQM = 21.0

VIIRS_COLLECTION = "NASA/VIIRS/002/VNP46A2"
RADIANCE_BAND = "DNB_BRDF_Corrected_NTL"
QUALITY_BAND = "Mandatory_Quality_Flag"

START_DATE = "2012-04-01"
END_DATE = "2025-04-01"
HISTORY_MONTHS = 156  # 2012-04 → 2025-04
FORECAST_MONTHS = 120


def viirs_to_sqm(radiance_nw: float) -> float:
    if radiance_nw <= 0:
        return 22.0
    return 22.0 - 2.5 * math.log10((radiance_nw / NATURAL_NIGHT_RADIANCE) + 1.0)


def authenticate_gee(project: str):
    """Initialize the Earth Engine client. Auth must already be cached via
    `earthengine authenticate` — we don't trigger an interactive flow here
    because the script is typically run unattended."""
    try:
        import ee
    except ImportError:
        sys.exit("earthengine-api not installed. pip install earthengine-api")

    sa_json = os.environ.get("GEE_SERVICE_ACCOUNT_JSON")
    if sa_json and Path(sa_json).exists():
        creds = ee.ServiceAccountCredentials(email=None, key_file=sa_json)
        ee.Initialize(credentials=creds, project=project)
    else:
        ee.Initialize(project=project)
    return ee


def sample_city(ee, city: dict) -> list[tuple[str, float]]:
    """Return [(YYYY-MM, radiance_nw), …] for one city.

    Server-side pipeline:
      raw daily VNP46A2 → mask to good-quality pixels → group by month
      → median composite per month → median reduce over 10km buffer.
    One getInfo() call returns the full 156-month series for the city.
    """
    point = ee.Geometry.Point([city["lon"], city["lat"]])
    region = point.buffer(SAMPLE_BUFFER_M)

    raw = (
        ee.ImageCollection(VIIRS_COLLECTION)
        .filterDate(START_DATE, END_DATE)
        .filterBounds(region)
    )

    def keep_good(img):
        good = img.select(QUALITY_BAND).eq(0)
        return img.select(RADIANCE_BAND).updateMask(good)

    masked = raw.map(keep_good)

    start = ee.Date(START_DATE)
    end = ee.Date(END_DATE)
    n_months = end.difference(start, "month").toInt()
    months = ee.List.sequence(0, n_months.subtract(1))

    def month_composite(offset):
        offset = ee.Number(offset)
        m_start = start.advance(offset, "month")
        m_end = m_start.advance(1, "month")
        composite = masked.filterDate(m_start, m_end).median()
        return composite.set("month", m_start.format("YYYY-MM"))

    monthly_coll = ee.ImageCollection.fromImages(months.map(month_composite))

    def reduce_one(img):
        val = img.reduceRegion(
            reducer=ee.Reducer.median(),
            geometry=region,
            scale=500,
            maxPixels=int(1e8),
        ).get(RADIANCE_BAND)
        return ee.Feature(None, {"month": img.get("month"), "rad": val})

    features = monthly_coll.map(reduce_one).getInfo()
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


def forecast_prophet(series: list[tuple[str, float]], horizon_months: int = FORECAST_MONTHS) -> list[float]:
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


def build_record(city: dict, series: list[tuple[str, float]]) -> dict:
    trend = fit_trend(series)
    baseline = sum(v for _, v in series[:12]) / 12  # first-year mean
    radiance_history = [v for _, v in series]
    forecast = forecast_prophet(series)
    all_rad = radiance_history + forecast
    all_sqm = [viirs_to_sqm(r) for r in all_rad]

    milky_way_lost = find_first_year(all_sqm, 2012, 4, lambda sqm: sqm < MILKY_WAY_THRESHOLD_SQM)
    if milky_way_lost == 2012 and viirs_to_sqm(baseline) < MILKY_WAY_THRESHOLD_SQM:
        # If the baseline year was already below threshold the milestone fired
        # pre-record and we have no real "lost" year to report.
        milky_way_lost = None
    doubled = find_first_year(all_rad, 2012, 4, lambda r: r >= 2.0 * baseline)
    halved = find_first_year(all_rad, 2012, 4, lambda r: r <= 0.5 * baseline)

    return {
        "name": city["name"],
        "country": city["country"],
        "lat": float(city["lat"]),
        "lon": float(city["lon"]),
        "population_m": float(city.get("population_m", 0.0)) if city.get("population_m") is not None else 0.0,
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
        "data_source": "measured",
    }


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


def merge_into_parquet(output_path: Path, measured_rows: list[dict]) -> None:
    """Load the existing Parquet, drop any modeled row that's the same city as
    a fresh measured row (matched by name case-insensitive + haversine within
    100 km), append the measured rows, write back. The 100 km radius is loose
    enough to absorb coord drift between geonamescache and the seed CSV but
    tight enough to keep truly-different same-name cities apart (e.g.
    Newcastle AU vs Newcastle ZA are ~10,000 km apart)."""
    import pandas as pd

    if not output_path.exists():
        df = pd.DataFrame(measured_rows)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(output_path, compression="snappy")
        print(f"[ingest_gee] no prior parquet; wrote {len(df)} measured rows")
        return

    existing = pd.read_parquet(output_path)
    if "data_source" not in existing.columns:
        existing["data_source"] = "modeled"

    drops: set[int] = set()
    name_index: dict[str, list[int]] = {}
    for idx, row in existing.iterrows():
        name_index.setdefault(str(row["name"]).lower(), []).append(int(idx))

    for m in measured_rows:
        candidates = name_index.get(str(m["name"]).lower(), [])
        for idx in candidates:
            existing_row = existing.iloc[idx]
            if existing_row["data_source"] == "measured":
                continue  # never displace an earlier measurement; we'll overwrite via append-replace below
            dist = _haversine_km(m["lat"], m["lon"], float(existing_row["lat"]), float(existing_row["lon"]))
            if dist < 100:
                drops.add(idx)

    keep = existing.drop(index=list(drops))
    measured_df = pd.DataFrame(measured_rows)

    # If we're re-running a city already measured (same name + within 100 km of a
    # prior measured row), drop the old measured row so the fresh one wins.
    for m in measured_rows:
        same = keep[
            (keep["name"].astype(str).str.lower() == m["name"].lower())
            & (keep["data_source"] == "measured")
        ]
        for idx, row in same.iterrows():
            if _haversine_km(m["lat"], m["lon"], float(row["lat"]), float(row["lon"])) < 100:
                keep = keep.drop(index=idx)

    merged = pd.concat([keep, measured_df], ignore_index=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(output_path, compression="snappy")

    n_measured = int((merged["data_source"] == "measured").sum())
    n_modeled = int((merged["data_source"] == "modeled").sum())
    print(f"[ingest_gee] merged: {n_measured} measured + {n_modeled} modeled = {len(merged)} total rows")


def main() -> None:
    parser = argparse.ArgumentParser(description="Real VIIRS DNB ingestion via Google Earth Engine.")
    parser.add_argument("--cities", type=Path, default=DEFAULT_CITIES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N cities (testing)")
    parser.add_argument("--project", type=str, default=os.environ.get("GEE_PROJECT_ID"),
                        help="Google Cloud project ID registered with GEE (or set GEE_PROJECT_ID).")
    args = parser.parse_args()

    if not args.project:
        sys.exit("--project is required (or set GEE_PROJECT_ID env var)")

    import pandas as pd
    cities = pd.read_csv(args.cities, keep_default_na=False, na_values=[""])
    if args.limit:
        cities = cities.head(args.limit)

    print(f"[ingest_gee] authenticating with Earth Engine project={args.project}…")
    ee = authenticate_gee(args.project)
    print(f"[ingest_gee] processing {len(cities)} cities (buffer {SAMPLE_BUFFER_M//1000}km median)…")

    records: list[dict] = []
    t0 = time.time()
    for i, (_, city) in enumerate(cities.iterrows(), start=1):
        try:
            t1 = time.time()
            series = sample_city(ee, city.to_dict())
            if len(series) < 24:
                print(f"  [{i}/{len(cities)}] {city['name']}: insufficient data ({len(series)} months) — skip")
                continue
            rec = build_record(city.to_dict(), series)
            records.append(rec)
            dt = time.time() - t1
            print(f"  [{i}/{len(cities)}] {city['name']}: {len(series)} mo, "
                  f"baseline {rec['baseline_radiance_nw']:.2f} nW, "
                  f"trend {rec['trend_pct_per_yr']:+.2f}%/yr, "
                  f"SQM {rec['sqm_current']:.2f} ({dt:.1f}s)")
        except Exception as e:
            print(f"  [{i}/{len(cities)}] {city['name']}: FAILED — {type(e).__name__}: {e}")

    elapsed = time.time() - t0
    print(f"\n[ingest_gee] {len(records)} cities measured in {elapsed/60:.1f} min")

    if records:
        merge_into_parquet(args.output, records)
    else:
        print("[ingest_gee] no records — Parquet untouched.")


if __name__ == "__main__":
    main()
