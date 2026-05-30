# Nightview

> An interactive 3D globe of how the night sky has changed across Earth since 2012 — with a conversational AI agent built on Claude that drives the camera and surfaces patterns in real VIIRS satellite data.

![Nightview screenshot placeholder — globe with heatmap, chat panel, time ribbon](docs/screenshot.png)

[Live demo](#) · [Case study](#) · [Methodology](#methodology)

---

## What it does

- **A globe permanently painted with data.** ~2,900 cities across every populated continent, colored by their rate of light-pollution change since 2012 (blue → cream → red). Population sizes the dots; trend colors them. Riyadh and Mumbai light up immediately as the worst offenders; Cherry Springs and the Atacama stay dark.
- **A time scrubber pinned to the bottom.** Drag it between 2012 and 2035 and the dots morph in real time — brightening cities visibly grow, darkening cities shrink. Play button auto-animates the 23-year arc.
- **A conversational agent.** Powered by Claude Haiku 4.5 (with prompt caching and an automatic Sonnet 4.6 escalation for hard queries). Ask things like *"where is the night sky disappearing fastest?"*, *"compare India vs China"*, or *"how bright will St. Louis be in 2035?"* — the relevant cities pulse in their existing heatmap color (not generic markers), the camera glides to frame them, and the agent narrates in plain English with the actual numbers cited.
- **Click any city** for an inspector with the brightness time series, Prophet-style forecast to 2035, current SQM (Sky Quality Magnitude), and milestone badges (e.g. *"brightness doubled · 2030"*). If the scrubber is at year Y, the inspector projects SQM for Y, not for the present.
- **Search any city** from the top-right autocomplete (Paris, Pathein, St. Louis, Atacama, anywhere).

## Architecture

```
                  ┌──────────────────────────────────────┐
                  │   React + Vite + CesiumJS frontend   │
                  │   (full-bleed globe + chat orb +     │
                  │    inspector + time ribbon + search) │
                  └─────────────┬────────────────────────┘
                                │  HTTP / SSE
                  ┌─────────────▼────────────────────────┐
                  │           FastAPI backend            │
                  │  ┌──────────────────────────────┐    │
                  │  │  Claude agent loop           │    │
                  │  │  Haiku 4.5 (cached)          │    │
                  │  │  → Sonnet 4.6 on complex     │    │
                  │  └──────────────┬───────────────┘    │
                  │                 │                    │
                  │  ┌──────────────▼───────────────┐    │
                  │  │  6 tools                     │    │
                  │  │  · query_region              │    │
                  │  │  · point_timeseries          │    │
                  │  │  · top_changers              │    │
                  │  │  · milestones_in_region      │    │
                  │  │  · compare_regions           │    │
                  │  │  · dark_sky_locations        │    │
                  │  └──────────────┬───────────────┘    │
                  │                 │                    │
                  │  ┌──────────────▼───────────────┐    │
                  │  │  Rate limit + $ daily cap    │    │
                  │  └──────────────────────────────┘    │
                  └─────────────────┬────────────────────┘
                                    │
                  ┌─────────────────▼────────────────────┐
                  │       Parquet trends store           │
                  │  (per-city: baseline radiance,       │
                  │   trend %/yr, SQM, 156-month         │
                  │   history, 120-month forecast,       │
                  │   milestone years)                   │
                  └─────────────────┬────────────────────┘
                                    │   offline ingestion
                  ┌─────────────────▼────────────────────┐
                  │   scripts/                           │
                  │  · ingest_seed.py    curated 107     │
                  │  · ingest_global.py  geonames 2,894  │
                  │  · ingest_gee.py     real GEE pixels │
                  └──────────────────────────────────────┘
```

## Quick start

```bash
make install        # one-time: backend venv + npm install
make dev            # starts both servers in the background
# open http://localhost:5173
```

You'll need:
- Python 3.11+
- Node 20+
- An [Anthropic API key](https://console.anthropic.com) in `.env` at the repo root:
  ```
  ANTHROPIC_API_KEY=sk-ant-...
  ```
- Optional: a [Cesium Ion token](https://ion.cesium.com/tokens) for NASA Black Marble imagery as the basemap (free):
  ```
  VITE_CESIUM_ION_TOKEN=eyJhbGciOi...
  ```
  Then flip `USE_BLACK_MARBLE_BASEMAP = true` in `frontend/src/components/Globe.tsx`. Without it, the globe uses Cesium's bundled Natural Earth II imagery, darkened to fit the night theme.

Other targets:

```bash
make help           # list available targets
make stop           # kill backend + frontend
make seed           # regenerate the curated-seed Parquet (~107 cities)
make seed-global    # regenerate via geonamescache (~2,894 cities, default)
make typecheck      # tsc + py_compile across both halves
```

## Stack

| Layer | Choice |
|---|---|
| Globe | CesiumJS (`Cesium.PointPrimitiveCollection` for GPU-direct heatmap, entity overlays for highlights) |
| UI | React 18 + Vite + TypeScript + TailwindCSS + Motion (`motion/react`) |
| Backend | FastAPI + Anthropic Python SDK (streaming tool-use with prompt caching) |
| LLM | Claude **Haiku 4.5** default, escalates to **Sonnet 4.6** on complex queries |
| Data | NASA VIIRS DNB derived; trends sourced from Kyba et al. 2017 / Sánchez de Miguel et al. 2021 |
| Storage | Parquet, queried via pandas (single file, ~10 MB) |
| Forecast | Per-city compound-growth projection (Prophet path available in `ingest_gee.py`) |
| Deploy | Vercel (frontend) + Fly.io (backend) — see [DEPLOY.md](DEPLOY.md) |

## Methodology

**Trend rates** come from published VIIRS Day-Night Band analyses — Kyba et al. (2017) for global / regional rates, Sánchez de Miguel et al. (2021) for country-level updates, plus city-specific studies for ~107 hand-curated cities (the worst offenders and the famous dark-sky reserves). Cities not in the curated set get their country's published rate.

**Baseline radiance** for the ~2,800 geonames cities is modeled from population — a log-linear curve fit against the curated set. This is the modeled part: real per-pixel measurements require running `scripts/ingest_gee.py`, which pulls actual `NOAA/VIIRS/DNB/MONTHLY_V1` time series from Google Earth Engine for every city in the list (requires a free GEE account, ~10 min to process).

**SQM (Sky Quality Magnitude)** is derived from radiance using the Falchi et al. (2016) conversion, with natural night-sky radiance pinned at 0.171 nW/cm²/sr. The Milky Way visibility threshold is SQM 21.0 (Bortle 4) — though the dataset's darkest reserves cap around SQM 20.3, the `dark_sky_locations` tool uses 19.5 as the practical floor.

**Forecasts to 2035** apply each city's trend as compound monthly growth from its present radiance.

## Project layout

```
.
├── backend/                FastAPI + Anthropic SDK
│   ├── app/
│   │   ├── main.py         endpoints (/api/chat, /api/cities, /api/point, /api/top_changers, /api/health)
│   │   ├── agent.py        Claude tool-use loop, model routing, error handling
│   │   ├── tools.py        6 tool JSON schemas + async dispatcher
│   │   ├── data.py         Parquet → pandas, query helpers
│   │   ├── schemas.py      Pydantic models
│   │   └── rate_limit.py   per-IP + daily $ cap
│   └── requirements.txt
├── frontend/               React + Vite + Cesium
│   └── src/
│       ├── components/     Globe · ChatOrb · Inspector · CitySearch · HoverTooltip · TimeRibbon · ObservatoryHud · ErrorBoundary
│       ├── lib/            api, types, prompts
│       ├── App.tsx · main.tsx · index.css
│       └── ...
├── scripts/                ingestion pipelines (seed, global, gee)
├── data/
│   ├── raw/                cities_seed.csv (107 curated cities)
│   └── processed/          trends.parquet (gitignored, generated)
├── Makefile
└── README.md
```

## Credits

- NASA Earth Observatory — VIIRS Day-Night Band imagery and the Black Marble product family
- Christopher C. M. Kyba et al. (2017) — *Artificially lit surface of Earth at night increasing in radiance and extent*
- Alejandro Sánchez de Miguel et al. — VIIRS-derived long-term sky brightness trends
- Fabio Falchi et al. (2016) — *World Atlas of Artificial Night Sky Brightness* (the VIIRS → SQM conversion)
- [geonamescache](https://github.com/yaph/geonamescache) — bundled global cities database
- Cesium / Cesium Ion — globe rendering + Natural Earth II base imagery
- Anthropic — Claude API
