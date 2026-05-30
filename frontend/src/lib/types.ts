export type AgentEventType = 'text' | 'tool_call' | 'tool_result' | 'globe_action' | 'done' | 'error';

export interface AgentEvent<T = unknown> {
  type: AgentEventType;
  data: T;
}

export interface GlobeAction {
  type: 'highlight_cells' | 'fly_to' | 'overlay_badge' | 'time_scrub_to' | 'none';
  payload: Record<string, unknown>;
}

export interface HighlightPoint {
  lat: number;
  lon: number;
  label?: string;
}

export interface ToolCall {
  name: string;
  input: Record<string, unknown>;
}

export interface TimeSeriesPoint {
  year: number;
  month: number;
  radiance_nw: number;
  sqm_estimated?: number | null;
}

export interface City {
  name: string;
  country: string;
  lat: number;
  lon: number;
  trend: number;
  pop: number;
  baseline: number;
  milky_way_lost?: number | null;
  doubled?: number | null;
  halved?: number | null;
}

export interface Place {
  name: string;
  country: string | null;
  lat: number;
  lon: number;
  trend_pct_per_yr: number;
  forecast_2035_pct_vs_2012: number | null;
  milky_way_lost_year: number | null;
  milky_way_regained_year: number | null;
  brightness_doubled_year: number | null;
  brightness_halved_year: number | null;
}
