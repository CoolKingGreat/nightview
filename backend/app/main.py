"""
FastAPI entry point for Nightview.

Endpoints:
  GET  /api/health                — liveness probe
  POST /api/chat                  — SSE stream of agent events for one user message
  POST /api/point                 — non-agent point lookup (used by globe click)
  GET  /api/top_changers          — non-agent top-N for empty-state heatmap pre-fetch

The chat endpoint is the agent's home. The non-agent endpoints exist so the
frontend can fetch data without paying for an LLM call when there's no chat
involved (clicking a point, painting the heatmap).
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from . import data
from .agent import run_agent
from .rate_limit import check_allowed, record_request
from .schemas import ChatRequest, PointQuery

load_dotenv()

app = FastAPI(title="Nightview API", version="0.1.0")

_allowed_origins = os.environ.get(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict:
    return {
        "status": "ok",
        "anthropic_key_configured": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "data_source": data.data_source(),
    }


@app.post("/api/chat")
async def chat(request: Request, body: ChatRequest) -> StreamingResponse:
    ip = request.client.host if request.client else "unknown"
    allowed, reason = check_allowed(ip)
    if not allowed:
        raise HTTPException(status_code=429, detail=reason)

    history = [t.model_dump() for t in body.history]

    async def event_stream():
        try:
            async for event in run_agent(body.message, history=history):
                yield event.to_sse()
        finally:
            record_request(ip)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.post("/api/point")
async def point(body: PointQuery) -> dict:
    ts = data.point_timeseries(body.lat, body.lon, granularity=body.granularity)
    return ts.model_dump()


@app.get("/api/top_changers")
async def top_changers(direction: str = "brightening", n: int = 5) -> dict:
    if direction not in ("brightening", "darkening"):
        raise HTTPException(status_code=400, detail="direction must be 'brightening' or 'darkening'")
    places = data.top_changers(direction=direction, n=n)
    return {"places": [p.model_dump() for p in places]}


@app.get("/api/cities")
async def cities() -> dict:
    """All cities for the global rate-of-change heatmap. Trimmed to render-essential fields."""
    if data._REAL_DF is None:
        return {"cities": []}
    df = data._REAL_DF[[
        "name", "country", "lat", "lon", "trend_pct_per_yr", "population_m",
        "baseline_radiance_nw", "milky_way_lost_year", "brightness_doubled_year",
        "brightness_halved_year",
    ]]
    out = []
    for _, row in df.iterrows():
        out.append({
            "name": str(row["name"]),
            "country": str(row["country"]) if row["country"] else "",
            "lat": round(float(row["lat"]), 4),
            "lon": round(float(row["lon"]), 4),
            "trend": round(float(row["trend_pct_per_yr"]), 2),
            "pop": round(float(row["population_m"]), 3),
            "baseline": round(float(row["baseline_radiance_nw"]), 2),
            "milky_way_lost": _int_or_none(row.get("milky_way_lost_year")),
            "doubled": _int_or_none(row.get("brightness_doubled_year")),
            "halved": _int_or_none(row.get("brightness_halved_year")),
        })
    return {"cities": out}


def _int_or_none(v):
    import math
    if v is None:
        return None
    try:
        if isinstance(v, float) and math.isnan(v):
            return None
        return int(v)
    except (TypeError, ValueError):
        return None
