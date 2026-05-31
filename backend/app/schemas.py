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


class PlaceResult(BaseModel):
    name: str
    country: str | None = None
    lat: float
    lon: float
    h3_index: str | None = None
    trend_pct_per_yr: float
    forecast_2035_pct_vs_2012: float | None = None
    sqm_current: float | None = None
    milky_way_lost_year: int | None = None
    milky_way_regained_year: int | None = None
    brightness_doubled_year: int | None = None
    brightness_halved_year: int | None = None


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
