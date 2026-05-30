# Nightview frontend

React 18 + Vite + TypeScript + TailwindCSS + CesiumJS, with Motion for orchestrated reveals.

## Quick start

```bash
cd frontend
npm install
npm run dev    # http://localhost:5173
```

The dev server proxies `/api/*` to `http://localhost:8000` by default. To point at a different backend, set `VITE_BACKEND_URL` in your `.env` (e.g. `VITE_BACKEND_URL=http://localhost:8765`). Bring the FastAPI backend up first.

## Cesium Ion token (required for the Black Marble basemap)

The night-Earth basemap that gives Nightview its identity comes from **NASA Black Marble** via Cesium Ion. Free for our usage level. Get a token at <https://ion.cesium.com/tokens>, then add it to `.env` at the repo root:

```
VITE_CESIUM_ION_TOKEN=eyJhbGciOi...
```

Without a token the globe still renders, but on Cesium's fallback basemap — not the aesthetic we want for the portfolio piece. A console warning prints the link.

## Visual identity

| Element | Choice |
|---|---|
| Display | **Playfair Display** (Google Fonts) — characterful serif, used sparingly |
| Body | **Newsreader** (Google Fonts) — editorial serif, hushed, low-contrast strokes |
| Mono | **JetBrains Mono** — observatory readouts, attribution, user-turn echo |
| Base | `#0A0E1A` deep midnight |
| Text | `#E8E2D3` warm cream (never pure white — too harsh) |
| City lights | `#F3D38A` warm amber |
| Brightening overlay | `#C24E4A` muted sodium-vapor red |
| Darkening overlay | `#5A7A9C` muted steel blue |
| Easing | `cubic-bezier(0.16, 1, 0.3, 1)` — weighted, planetarium-slow |

**Aesthetic direction: astronomical-observatory editorial.** The page *is* the night. Slow motion, generous tracking, lowercase by default, no rounded card chrome, no drop shadows. Subtle film-grain overlay and corner vignette so the dark never reads flat.

## Layout

```
src/
├── main.tsx                # React entry
├── App.tsx                 # Composes Globe + HUD + ChatOrb; toggles auto-rotation while chat is active
├── index.css               # Tailwind + Google Font loads + grain & vignette overlays
├── lib/
│   ├── api.ts              # SSE streaming client + top_changers fetch
│   ├── types.ts            # AgentEvent / GlobeAction / Place
│   └── prompts.ts          # 4 rotating empty-state ghost prompts
└── components/
    ├── Globe.tsx           # CesiumJS viewer, Black Marble, auto-rotation, applyAction handler
    ├── ChatOrb.tsx         # Collapsed pill → expanded transcript+input; streams from backend
    ├── GhostText.tsx       # Rotating empty-state prompts; fade in/out every 6s
    └── ObservatoryHud.tsx  # Wordmark + UTC readout + attribution
```

## What ships in v0

- Full-bleed CesiumJS globe with hidden chrome, deep-midnight background, slow auto-rotation (one rev ≈ 200s)
- Collapsed chat orb anchored center-bottom with ghost-text rotating through 4 prompts
- Click the orb → it expands into a transcript + input
- Type a prompt → streams a response from the backend; the globe pauses rotation and responds to `globe_action` events
- Graceful fallback when the backend has no API key or 429s (rate-limit text appears in the transcript)
- Page-load orchestration: globe materializes first, wordmark slides in (200ms delay), observatory readouts fade in (550ms), chat orb appears (1000ms)

## Not yet wired (TODO comments in components)

- Rate-of-change heatmap overlay on the globe (Cesium primitive for the per-cell color painting from SPEC.md §6.2)
- Click-to-inspect on a globe point → time-series modal
- Time scrubber (the "play history" affordance on focused regions)
- Milestone badge overlays
- Geo-IP localization of the St. Louis prompt
- Mobile-aware density (v1)

## Performance notes

- Cesium terrain disabled (`EllipsoidTerrainProvider`) — no topo needed for the night aesthetic
- Cesium sun, moon, atmosphere, fog, lighting all off
- Brightness/contrast on the Black Marble layer lifted slightly (`brightness: 1.15`, `contrast: 1.12`) so cities glow against near-black water
