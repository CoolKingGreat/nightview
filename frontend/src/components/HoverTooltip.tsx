import { useEffect, useState } from 'react';
import type { HoverState } from './Globe';

const ARROW_OFFSET = 16;

export function HoverTooltip({ state }: { state: HoverState | null }) {
  const [touchDevice, setTouchDevice] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia('(pointer: coarse)');
    setTouchDevice(mq.matches);
    const onChange = (e: MediaQueryListEvent) => setTouchDevice(e.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);

  if (touchDevice) return null;
  if (!state || !state.city || typeof state.city.trend !== 'number') return null;
  const { city, x, y } = state;
  const trendStr = city.trend > 0 ? `+${city.trend.toFixed(1)}` : city.trend.toFixed(1);
  const trendClass =
    city.trend > 2 ? 'text-[#E67462]' : city.trend < 0 ? 'text-[#6CA8DC]' : 'text-ink/85';

  return (
    <div
      className="pointer-events-none absolute z-50 -translate-x-1/2 -translate-y-full whitespace-nowrap"
      style={{ left: x, top: y - ARROW_OFFSET }}
    >
      <div className="rounded-md border border-white/[0.07] bg-[#04060D]/95 px-3 py-2 shadow-[0_4px_16px_rgba(0,0,0,0.4)] backdrop-blur-md">
        <div className="font-display text-[13px] font-medium leading-tight text-ink">
          {city.name}
        </div>
        <div className="mt-1 flex items-baseline gap-2 font-mono text-[10px] tracking-[0.18em] text-muted">
          <span className="uppercase">{city.country}</span>
          <span className={trendClass}>{trendStr}% / yr</span>
        </div>
        {(city.milky_way_lost || city.doubled) && (
          <div className="mt-2 border-t border-white/[0.06] pt-1.5 font-mono text-[9px] uppercase tracking-[0.18em] text-glow/75">
            {city.milky_way_lost && <div>milky way lost · {city.milky_way_lost}</div>}
            {city.doubled && <div>brightness doubled · {city.doubled}</div>}
          </div>
        )}
      </div>
    </div>
  );
}
