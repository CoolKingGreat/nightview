import { motion } from 'motion/react';
import { useEffect, useState } from 'react';
import { fetchPoint } from '../lib/api';
import type { City, TimeSeriesPoint } from '../lib/types';

const ease = [0.16, 1, 0.3, 1] as const;

interface PointResponse {
  place: {
    name: string;
    sqm_current?: number;
    forecast_2035_pct_vs_2012?: number;
    milky_way_lost_year?: number | null;
    milky_way_regained_year?: number | null;
    brightness_doubled_year?: number | null;
    brightness_halved_year?: number | null;
  };
  history: TimeSeriesPoint[];
  forecast: TimeSeriesPoint[];
  forecast_confidence: string;
}

interface Props {
  city: City;
  year: number;
  onBack: () => void;
}

const TIME_NOW = 2025;
const HISTORY_START_YEAR = 2012;
const HISTORY_START_MONTH = 4;

/** Find the time-series point for a given (fractional) year. */
function pointAtYear(history: TimeSeriesPoint[], forecast: TimeSeriesPoint[], year: number): TimeSeriesPoint | null {
  const all = [...history, ...forecast];
  if (all.length === 0) return null;
  const targetMonthIdx = Math.round((year - HISTORY_START_YEAR) * 12 - (HISTORY_START_MONTH - 1));
  const idx = Math.max(0, Math.min(all.length - 1, targetMonthIdx));
  return all[idx];
}

export function Inspector({ city, year, onBack }: Props) {
  const [data, setData] = useState<PointResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    setData(null);
    fetchPoint(city.lat, city.lon)
      .then((d: PointResponse) => {
        setData(d);
        setLoading(false);
      })
      .catch((e) => {
        setError(String(e));
        setLoading(false);
      });
  }, [city.lat, city.lon]);

  const trendStr = city.trend > 0 ? `+${city.trend.toFixed(1)}` : city.trend.toFixed(1);
  const yearLabel = Math.round(year);
  const atYear = data ? pointAtYear(data.history, data.forecast, year) : null;
  const baselinePt = data?.history?.[0] ?? null;
  const vsBaseline = atYear && baselinePt ? (atYear.radiance_nw / baselinePt.radiance_nw) * 100 : null;

  const milestones: { label: string; year: number }[] = [];
  if (data?.place.milky_way_lost_year) {
    milestones.push({ label: 'milky way visibility lost', year: data.place.milky_way_lost_year });
  }
  if (data?.place.milky_way_regained_year) {
    milestones.push({ label: 'milky way regained', year: data.place.milky_way_regained_year });
  }
  if (data?.place.brightness_doubled_year) {
    milestones.push({ label: 'brightness doubled vs 2012', year: data.place.brightness_doubled_year });
  }
  if (data?.place.brightness_halved_year) {
    milestones.push({ label: 'brightness halved vs 2012', year: data.place.brightness_halved_year });
  }

  return (
    <motion.aside
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.5, ease }}
      className="relative z-40 flex h-full min-h-0 flex-col bg-[#040610]/90 backdrop-blur-2xl md:border-l md:border-white/[0.05]"
    >
      <div className="relative border-b border-white/[0.05] px-6 pb-5 pt-12 md:pt-7">
        <button
          type="button"
          onClick={onBack}
          className="group mb-4 hidden items-center gap-2 font-mono text-[10px] uppercase tracking-[0.28em] text-muted transition-colors hover:text-glow md:flex"
        >
          <span className="inline-block transition-transform duration-300 group-hover:-translate-x-1">←</span>
          back to chat
        </button>
        <div className="font-display text-[1.45rem] font-medium leading-tight text-ink/95">
          {city.name}
        </div>
        <div className="mt-1.5 font-mono text-[10px] uppercase tracking-[0.32em] text-muted">
          {city.country} · {city.pop > 0 ? `${city.pop.toFixed(1)} M` : 'reserve'}
        </div>
      </div>

      <div className="min-h-0 flex-1 space-y-7 overflow-y-auto px-6 py-6">
        <div className="grid grid-cols-2 gap-x-4 gap-y-5">
          <Stat label="trend / yr" value={`${trendStr}%`} accent={city.trend > 2 ? 'red' : city.trend < 0 ? 'blue' : null} />
          {data && (
            <Stat
              label={yearLabel === TIME_NOW ? 'sqm now' : `sqm ${yearLabel}`}
              value={
                atYear?.sqm_estimated != null
                  ? atYear.sqm_estimated.toFixed(1)
                  : data.place.sqm_current?.toFixed(1) ?? '—'
              }
            />
          )}
          {data && vsBaseline != null && (
            <Stat
              label={`vs 2012 (${yearLabel})`}
              value={`${vsBaseline.toFixed(0)}%`}
              accent={vsBaseline > 200 ? 'red' : vsBaseline < 100 ? 'blue' : null}
            />
          )}
          {data && <Stat label="confidence" value={data.forecast_confidence} />}
        </div>

        {loading && <p className="font-mono text-[11px] uppercase tracking-[0.28em] text-muted">loading time series…</p>}
        {error && <p className="font-mono text-[11px] text-[#E67462]">{error}</p>}

        {data && (
          <>
            <div>
              <div className="mb-2 flex items-baseline justify-between">
                <div className="font-mono text-[9px] uppercase tracking-[0.32em] text-muted">
                  brightness over time
                </div>
                <div className="font-mono text-[9px] uppercase tracking-[0.32em] text-muted">
                  2012 — 2035
                </div>
              </div>
              <Chart history={data.history} forecast={data.forecast} markerYear={year} />
            </div>

            {milestones.length > 0 ? (
              <div>
                <div className="mb-3 font-mono text-[9px] uppercase tracking-[0.32em] text-muted">
                  milestones
                </div>
                <div className="space-y-2.5">
                  {milestones.map((m) => (
                    <div
                      key={m.label}
                      className="flex items-baseline justify-between border-b border-white/[0.04] pb-2.5"
                    >
                      <span className="font-body text-[13px] text-ink/85">{m.label}</span>
                      <span className="font-mono text-[13px] tabular-nums text-glow/85">{m.year}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="text-[12px] italic leading-relaxed text-muted">
                No tracked milestones for this place during the VIIRS record (2012–present).
              </div>
            )}
          </>
        )}
      </div>
    </motion.aside>
  );
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: 'red' | 'blue' | null }) {
  const valueClass = accent === 'red' ? 'text-[#E67462]' : accent === 'blue' ? 'text-[#6CA8DC]' : 'text-ink/95';
  return (
    <div>
      <div className="font-mono text-[9px] uppercase tracking-[0.32em] text-muted">{label}</div>
      <div className={`mt-1 font-display text-[16px] tabular-nums ${valueClass}`}>{value}</div>
    </div>
  );
}

function Chart({
  history,
  forecast,
  markerYear,
}: {
  history: TimeSeriesPoint[];
  forecast: TimeSeriesPoint[];
  markerYear: number;
}) {
  const all = [...history, ...forecast];
  if (all.length === 0) return null;

  const W = 320;
  const H = 130;
  const PAD_X = 4;
  const PAD_Y = 8;
  const values = all.map((p) => p.radiance_nw);
  const max = Math.max(...values);
  const min = Math.min(0, Math.min(...values));
  const range = Math.max(0.01, max - min);

  const xAt = (i: number) => PAD_X + (i / (all.length - 1)) * (W - 2 * PAD_X);
  const yAt = (v: number) => H - PAD_Y - ((v - min) / range) * (H - 2 * PAD_Y);

  const historyD = history
    .map((p, i) => `${i === 0 ? 'M' : 'L'}${xAt(i).toFixed(1)},${yAt(p.radiance_nw).toFixed(1)}`)
    .join('');
  const forecastD = forecast
    .map(
      (p, i) =>
        `${i === 0 ? 'M' : 'L'}${xAt(history.length + i).toFixed(1)},${yAt(p.radiance_nw).toFixed(1)}`,
    )
    .join('');
  const nowX = xAt(history.length - 1);

  // Marker for the scrubbed year.
  const monthIdx = Math.max(
    0,
    Math.min(all.length - 1, Math.round((markerYear - HISTORY_START_YEAR) * 12 - (HISTORY_START_MONTH - 1))),
  );
  const markerX = xAt(monthIdx);
  const markerY = yAt(all[monthIdx].radiance_nw);
  const showMarker = Math.abs(markerYear - TIME_NOW) > 0.2;

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} className="block">
      <line x1={PAD_X} y1={H - PAD_Y} x2={W - PAD_X} y2={H - PAD_Y} stroke="rgba(255,255,255,0.06)" />
      <path d={historyD} fill="none" stroke="#FFD978" strokeWidth="1.4" />
      <path d={forecastD} fill="none" stroke="#FFD978" strokeWidth="1.2" strokeDasharray="3,3" opacity="0.6" />
      <line
        x1={nowX.toFixed(1)}
        y1={PAD_Y}
        x2={nowX.toFixed(1)}
        y2={H - PAD_Y}
        stroke="rgba(255,255,255,0.14)"
        strokeDasharray="2,3"
      />
      <text x={nowX - 3} y={H - 1} textAnchor="end" fontSize="8" fill="rgba(204,210,225,0.5)" fontFamily="'JetBrains Mono', monospace">
        now
      </text>
      {showMarker && (
        <>
          <line
            x1={markerX.toFixed(1)}
            y1={PAD_Y}
            x2={markerX.toFixed(1)}
            y2={H - PAD_Y}
            stroke="rgba(255,217,120,0.7)"
            strokeWidth="1"
          />
          <circle cx={markerX} cy={markerY} r="3" fill="#FFF3C2" />
        </>
      )}
    </svg>
  );
}
