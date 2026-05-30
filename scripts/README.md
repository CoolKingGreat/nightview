# Nightview data pipelines

Two paths from raw VIIRS data to the Parquet the backend queries. They produce
the same schema, so they're swappable — whichever ran last wins.

## `ingest_seed.py` — runs now, no auth

Builds `data/processed/trends.parquet` from `data/raw/cities_seed.csv`. The CSV
carries ~100 cities with **published trend slopes** from the VIIRS light-pollution
literature (Kyba et al. 2017, Sánchez de Miguel et al. 2021, and city-specific
studies). The script projects each slope into 13 years of monthly history + 10
years of analytical forecast, runs the Falchi (2016) VIIRS→SQM conversion, and
detects Milky Way / 2×brightness / 0.5×brightness crossing years.

```bash
python scripts/ingest_seed.py
```

This is what the live demo uses out of the box. Real cities, real trend rates,
analytically-derived monthly granularity.

## `ingest_gee.py` — real per-pixel measurements

Replaces the seed Parquet with per-city pixel-derived measurements from NASA's
`NOAA/VIIRS/DNB/MONTHLY_V1` ImageCollection on Google Earth Engine. For each
city: median radiance within a 10 km buffer per month, OLS trend on the log
series, Prophet forecast, milestone detection — all from real measurements.

### Setup (one-time)

1. Sign up for free Earth Engine access → <https://earthengine.google.com/signup/>
2. `pip install earthengine-api`
3. `earthengine authenticate` (opens your browser, ~30 seconds)

For headless / CI use: create a GCP service account with the Earth Engine
Viewer role, download the JSON key, and set `GEE_SERVICE_ACCOUNT_JSON` in `.env`.

### Run

```bash
# Full run (default ~100 cities, ~10 min)
python scripts/ingest_gee.py

# Small test
python scripts/ingest_gee.py --limit 10

# Custom city list
python scripts/ingest_gee.py --cities data/raw/cities_extended.csv
```

The Parquet output lands at `data/processed/trends.parquet` by default and the
backend picks it up on next restart.

## Schema

Both scripts produce the same Parquet schema:

| Column | Type | Source |
|---|---|---|
| `name`, `country`, `lat`, `lon`, `population_m` | str/float | city CSV |
| `baseline_radiance_nw` | float | first-year mean radiance |
| `trend_pct_per_yr` | float | seed: published; gee: OLS on log series |
| `sqm_current` | float | Falchi 2016 conversion of latest radiance |
| `forecast_2035_pct_vs_2012` | float | derived from last forecast month |
| `milky_way_lost_year` | int? | first year SQM crossed below 21.0 |
| `milky_way_regained_year` | int? | first year SQM crossed back above 21.0 |
| `brightness_doubled_year` | int? | first year radiance ≥ 2× baseline |
| `brightness_halved_year` | int? | first year radiance ≤ 0.5× baseline |
| `history_monthly_nw` | list&lt;float&gt; | 156 monthly values, 2012-04 → 2025-03 |
| `forecast_monthly_nw` | list&lt;float&gt; | 120 monthly values, 2025-04 → 2035-03 |

## Verifying real data is live

```bash
curl -s http://localhost:8000/api/health
# → {"status":"ok","anthropic_key_configured":true,"data_source":{"real_data_loaded":true,"row_count":102}}
```
