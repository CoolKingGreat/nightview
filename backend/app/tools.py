"""
Claude tool catalog + dispatcher.

The five tools the agent can call. Every tool accepts a `granularity` parameter
the agent chooses per query (`place` / `region` / `cell`). Each tool returns a
JSON-serializable dict; tools that produce a meaningful map response include a
`globe_action` field the frontend interprets (see schemas.GlobeAction).

Tool schemas are kept stable (deterministic field order) so prompt caching on
the tool definitions stays valid across requests.
"""
from __future__ import annotations

from typing import Any

from . import data
from .schemas import GlobeAction, PlaceResult

TOOLS: list[dict[str, Any]] = [
    {
        "name": "query_region",
        "description": (
            "Look up light-pollution change inside a named region (country, state, "
            "or city). Returns the top N places ranked by absolute trend, with each "
            "place's per-year change and any milestones it has crossed. Use this "
            "when the user asks about a specific country / state / region."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "region": {
                    "type": "string",
                    "description": "A country, US state, or named region (e.g. 'India', 'Texas').",
                },
                "granularity": {
                    "type": "string",
                    "enum": ["place", "region", "cell"],
                    "description": "How to aggregate results. Default 'place' for city-level.",
                },
                "n": {
                    "type": "integer",
                    "description": "Number of places to return. Default 5, max 20.",
                    "minimum": 1, "maximum": 20,
                },
            },
            "required": ["region"],
        },
    },
    {
        "name": "point_timeseries",
        "description": (
            "Get the monthly brightness time series for a single point on Earth, "
            "plus a Prophet-based forecast through 2035. Use this when the user "
            "clicks a point on the globe or asks 'how bright will X be by Y?'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "lat": {"type": "number", "description": "Latitude in degrees."},
                "lon": {"type": "number", "description": "Longitude in degrees."},
                "granularity": {
                    "type": "string",
                    "enum": ["place", "region", "cell"],
                    "description": "Aggregation scale. Default 'place'.",
                },
            },
            "required": ["lat", "lon"],
        },
    },
    {
        "name": "top_changers",
        "description": (
            "Get the globally (or within a country) fastest brightening or "
            "darkening places. Use this for 'where is the night sky disappearing "
            "fastest' or 'where is dark sky recovering' style questions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": ["brightening", "darkening"],
                    "description": "Which end of the trend distribution to return.",
                },
                "n": {
                    "type": "integer",
                    "description": "Number of places. Default 5, max 20.",
                    "minimum": 1, "maximum": 20,
                },
                "scope_country": {
                    "type": "string",
                    "description": "Optional ISO-2 country code to restrict scope (e.g. 'US').",
                },
                "granularity": {
                    "type": "string",
                    "enum": ["place", "region", "cell"],
                    "description": "Aggregation scale. Default 'place'.",
                },
            },
            "required": ["direction"],
        },
    },
    {
        "name": "milestones_in_region",
        "description": (
            "Find places in a region where a specific milestone has fired — "
            "'milky_way_visible' (places that have not crossed the Milky Way loss threshold), "
            "'milky_way_lost' (sky quality fell below SQM 21.0), "
            "'brightness_doubled' (≥ 2× the 2012-2013 baseline), or "
            "'brightness_halved' (≤ 0.5× baseline, rare). Use region='global' for "
            "global questions like 'show me cities where you can still see the Milky Way'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "region": {
                    "type": "string",
                    "description": "Country, US state, named region, or 'global'.",
                },
                "milestone_type": {
                    "type": "string",
                    "enum": [
                        "milky_way_visible",
                        "milky_way_lost",
                        "brightness_doubled",
                        "brightness_halved",
                    ],
                },
                "since_year": {
                    "type": "integer",
                    "description": "Only return milestones that fired in or after this year.",
                },
            },
            "required": ["region", "milestone_type"],
        },
    },
    {
        "name": "dark_sky_locations",
        "description": (
            "Find places where the Milky Way is still visible — sky brightness "
            "above SQM 21.0 (Bortle 4 or darker). Returns the darkest places "
            "first. Use this for 'where can you still see the Milky Way?', "
            "'where are the darkest skies left?', or any 'where is dark sky "
            "still preserved' query. Globally there are very few such places, "
            "almost all of them dark-sky reserves or remote observatories."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "n": {
                    "type": "integer",
                    "description": "Number of places to return. Default 10, max 20.",
                    "minimum": 1, "maximum": 20,
                },
                "region": {
                    "type": "string",
                    "description": "Optional country, US state, or named region to restrict to. OMIT this field entirely for global results — do not pass 'global', 'world', or 'everywhere' as a string.",
                },
                "min_sqm": {
                    "type": "number",
                    "description": "Minimum SQM (sky quality magnitude) threshold. Default 19.5 (Bortle 4-5, Milky Way partially visible). The dataset's darkest reserves sit around SQM 20.3. Only override if you have a specific reason.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "compare_regions",
        "description": (
            "Compare light-pollution change between two regions side by side. "
            "Returns aggregate stats for each plus the top contributing places. "
            "Use this for 'India vs China' or 'Texas vs California' style queries."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "region_a": {"type": "string", "description": "First region."},
                "region_b": {"type": "string", "description": "Second region."},
                "granularity": {
                    "type": "string",
                    "enum": ["place", "region", "cell"],
                    "description": "Aggregation scale. Default 'place'.",
                },
            },
            "required": ["region_a", "region_b"],
        },
    },
]


def _places_globe_action(places: list[PlaceResult]) -> GlobeAction:
    if not places:
        return GlobeAction(type="none")
    if len(places) == 1:
        p = places[0]
        return GlobeAction(type="fly_to", payload={"lat": p.lat, "lon": p.lon, "zoom": 6})
    return GlobeAction(
        type="highlight_cells",
        payload={
            "points": [{"lat": p.lat, "lon": p.lon, "label": p.name} for p in places],
            "color_by": "trend_pct_per_yr",
        },
    )


def _milky_way_visible_response(places: list[PlaceResult]) -> str:
    if not places:
        return "I don't have any Milky Way-visible places in the current demo dataset."

    names = " and ".join(p.name for p in places)
    details = []
    for place in places:
        direction = "darkening" if place.trend_pct_per_yr < 0 else "brightening"
        details.append(f"{place.name} is {direction} at {abs(place.trend_pct_per_yr):.1f}% per year")
    milestone = next((p for p in places if p.brightness_halved_year), None)
    milestone_text = (
        f" {milestone.name} reached a brightness-halved milestone in "
        f"{milestone.brightness_halved_year}."
        if milestone
        else ""
    )
    return (
        f"In the current demo data, the Milky Way is still visible from {names}. "
        f"{'; '.join(details)}.{milestone_text} "
        "This is a sparse demo subset, not a complete global inventory."
    )


async def execute_tool(name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a Claude-emitted tool call to the data layer and shape the response."""
    if name == "query_region":
        places = data.query_region(
            tool_input["region"],
            granularity=tool_input.get("granularity", "place"),
            n=tool_input.get("n", 5),
        )
        return {
            "places": [p.model_dump() for p in places],
            "data_status": "ok" if places else "no_data",
            "note": None if places else f"No data available for '{tool_input['region']}' in the current dataset.",
            "globe_action": _places_globe_action(places).model_dump(),
        }

    if name == "point_timeseries":
        ts = data.point_timeseries(
            tool_input["lat"], tool_input["lon"],
            granularity=tool_input.get("granularity", "place"),
        )
        return {"timeseries": ts.model_dump(),
                "globe_action": GlobeAction(
                    type="fly_to",
                    payload={"lat": ts.place.lat, "lon": ts.place.lon, "zoom": 8},
                ).model_dump()}

    if name == "top_changers":
        places = data.top_changers(
            direction=tool_input["direction"],
            n=tool_input.get("n", 5),
            scope_country=tool_input.get("scope_country"),
            granularity=tool_input.get("granularity", "place"),
        )
        return {
            "places": [p.model_dump() for p in places],
            "data_status": "ok" if places else "no_data",
            "note": None if places else "No matching places in the current dataset.",
            "globe_action": _places_globe_action(places).model_dump(),
        }

    if name == "milestones_in_region":
        places = data.milestones_in_region(
            region=tool_input["region"],
            milestone_type=tool_input["milestone_type"],
            since_year=tool_input.get("since_year"),
        )
        coverage_note = None
        if tool_input["milestone_type"] == "milky_way_visible":
            coverage_note = (
                "Current dataset is a sparse demo subset, not a complete global "
                "inventory. Do not claim these are the only places globally."
            )
        return {
            "places": [p.model_dump() for p in places],
            "milestone_type": tool_input["milestone_type"],
            "data_status": "ok" if places else "no_data",
            "note": None if places else f"No '{tool_input['milestone_type']}' matches in '{tool_input['region']}' in the current dataset.",
            "coverage_note": coverage_note,
            "direct_response": (
                _milky_way_visible_response(places)
                if tool_input["milestone_type"] == "milky_way_visible"
                else None
            ),
            "globe_action": _places_globe_action(places).model_dump(),
        }

    if name == "dark_sky_locations":
        places = data.dark_sky_locations(
            n=tool_input.get("n", 10),
            region=tool_input.get("region"),
            min_sqm=tool_input.get("min_sqm", 19.5),
        )
        return {
            "places": [p.model_dump() for p in places],
            "data_status": "ok" if places else "no_data",
            "note": None if places else "No places above the SQM threshold in the current dataset.",
            "globe_action": _places_globe_action(places).model_dump(),
        }

    if name == "compare_regions":
        comparison = data.compare_regions(
            tool_input["region_a"], tool_input["region_b"],
            granularity=tool_input.get("granularity", "place"),
        )
        first_place_a = comparison["a"]["places"][0] if comparison["a"]["places"] else None
        first_place_b = comparison["b"]["places"][0] if comparison["b"]["places"] else None
        action = GlobeAction(type="none")
        if first_place_a and first_place_b:
            action = GlobeAction(
                type="highlight_cells",
                payload={"points": [
                    {"lat": first_place_a.lat, "lon": first_place_a.lon, "label": tool_input["region_a"]},
                    {"lat": first_place_b.lat, "lon": first_place_b.lon, "label": tool_input["region_b"]},
                ]},
            )
        comparison["a"]["places"] = [p.model_dump() for p in comparison["a"]["places"]]
        comparison["b"]["places"] = [p.model_dump() for p in comparison["b"]["places"]]
        return {"comparison": comparison, "globe_action": action.model_dump()}

    return {"error": f"unknown tool: {name}"}
