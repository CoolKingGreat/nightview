from typing import Any, Literal

from pydantic import BaseModel, Field

Granularity = Literal["place", "region", "cell"]


class ChatTurn(BaseModel):
    role: Literal["user", "agent"]
    text: str


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    history: list[ChatTurn] = Field(default_factory=list)


class GlobeAction(BaseModel):
    """Frontend-interpreted directive for animating the globe in response to a tool call."""
    type: Literal["highlight_cells", "fly_to", "overlay_badge", "time_scrub_to", "none"]
    payload: dict[str, Any] = Field(default_factory=dict)


class DarkSkyPlace(BaseModel):
    name: str
    country: str | None = None
    # park / reserve / sanctuary / community / observatory
    type: str
    lat: float
    lon: float
    distance_km: float


class SkyVisibility(BaseModel):
    """What a naked-eye observer can typically see from this site on a clear night.
    Derived from Bortle class — these are the standard amateur-astronomy
    expectations per Bortle (2001), not measured per-site."""
    stars_visible_estimate: str  # e.g. "~7,000+" or "~30"
    milky_way: str               # short description of MW visibility
    notable_objects: list[str]   # named DSOs / phenomena visible naked-eye


class PlaceResult(BaseModel):
    name: str
    country: str | None = None
    lat: float
    lon: float
    h3_index: str | None = None
    trend_pct_per_yr: float
    forecast_2035_pct_vs_2012: float | None = None
    sqm_current: float | None = None
    # Bortle class 1-9 (Bortle 2001 scale). 1 = excellent dark; 9 = inner-city.
    # Derived from sqm_current at serve time; null if SQM is unknown.
    bortle_class: int | None = None
    # Approximate naked-eye limiting magnitude (faintest star visible at zenith).
    # Interpolated from a Crumey/Schaefer reference table; null if SQM unknown.
    naked_eye_limit_mag: float | None = None
    # Nearest curated dark-sky destination — for "where to escape to" framing
    # in the Inspector. Null if no site within ~3000 km (i.e. ocean / Antarctica).
    nearest_dark_sky: DarkSkyPlace | None = None
    # Typical naked-eye visibility for this site's Bortle class. Null if
    # Bortle is unknown.
    visibility: SkyVisibility | None = None
    milky_way_lost_year: int | None = None
    milky_way_regained_year: int | None = None
    brightness_doubled_year: int | None = None
    brightness_halved_year: int | None = None
    # "measured" = per-pixel VIIRS DNB via Google Earth Engine (NASA VNP46A2).
    # "modeled" = population-derived baseline + published country-level trend.
    # Used by the agent to decide whether to cite numbers precisely or hedge.
    data_source: Literal["measured", "modeled"] | None = None


class TimeSeriesPoint(BaseModel):
    year: int
    month: int
    radiance_nw: float
    sqm_estimated: float | None = None


class TimeSeriesResult(BaseModel):
    place: PlaceResult
    history: list[TimeSeriesPoint]
    forecast: list[TimeSeriesPoint]
    forecast_confidence: Literal["high", "medium", "low"]
    # Great-circle km from the queried lat/lon to `place`. >0 means the user's
    # exact spot is not in the dataset and `place` is the nearest available one.
    distance_km: float | None = None


class PointQuery(BaseModel):
    lat: float
    lon: float
    granularity: Granularity = "place"
