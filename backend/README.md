# Nightview backend

FastAPI + Anthropic SDK. Serves the conversational agent and a few non-agent point/region lookups the frontend uses without paying for an LLM call.

## Quick start

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env  # fill in ANTHROPIC_API_KEY
uvicorn app.main:app --reload --port 8000
```

Smoke test:

```bash
curl -s http://localhost:8000/api/health

curl -N -X POST http://localhost:8000/api/chat \
  -H 'content-type: application/json' \
  -d '{"message":"where is the night sky disappearing fastest?"}'
```

You should see Server-Sent Events stream back with `text`, `tool_call`, `globe_action`, and `done` event payloads.

## Layout

```
backend/
├── requirements.txt
└── app/
    ├── main.py        # FastAPI app, endpoints, CORS, SSE wiring
    ├── agent.py       # Claude tool-use loop: Haiku 4.5 default, Sonnet 4.6 escalation, prompt caching
    ├── tools.py       # 5 tool JSON schemas + dispatcher
    ├── data.py        # mock data layer (replace with DuckDB-on-Parquet once scripts/ingest_viirs.py lands)
    ├── schemas.py     # Pydantic types shared between the layers
    └── rate_limit.py  # in-memory per-IP + daily $ cap
```

## Model & cost notes

- Haiku 4.5 (`claude-haiku-4-5`) handles the bulk of queries (~$0.005 / typical cached turn).
- Sonnet 4.6 (`claude-sonnet-4-6`) is auto-picked when the user query contains complexity markers (`compare`, `vs`, `rank`, `between`, …).
- Prompt caching uses top-level `cache_control: {"type": "ephemeral"}`. The SDK auto-places the breakpoint on the last cacheable block, which (since `tools` and `system` render before `messages`) caches **both** together. Expected hit ratio ~95% after the first turn in a session.
- **`effort` is not set** — it's unsupported on Haiku 4.5 and would 400. Sonnet 4.6 supports it; we'd add it there if we ever needed deeper thinking on hard queries.

## Data layer status

`app/data.py` currently serves plausible mock data so the agent loop is end-to-end testable before VIIRS ingestion exists. Once `scripts/ingest_viirs.py` (Task #4) produces the H3-indexed Parquet store, swap the `_MOCK_*` constants for DuckDB queries — the docstrings above each function sketch the SQL shape.
