import { motion } from 'motion/react';
import { useEffect, useRef, useState } from 'react';

const ease = [0.16, 1, 0.3, 1] as const;

export const TIME_MIN = 2012;
export const TIME_MAX = 2035;
export const TIME_NOW = 2025;

interface Props {
  year: number;
  onYearChange: (year: number) => void;
}

const BASE_YEARS_PER_SEC = 4;

export function TimeRibbon({ year, onYearChange }: Props) {
  const [playing, setPlaying] = useState(false);
  const [turbo, setTurbo] = useState(false);
  const trackRef = useRef<HTMLDivElement>(null);
  const draggingRef = useRef(false);
  const rafRef = useRef<number | null>(null);
  const lastTickRef = useRef<number>(0);

  useEffect(() => {
    if (!playing) {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      return;
    }
    const rate = BASE_YEARS_PER_SEC * (turbo ? 2 : 1);
    const tick = (timestamp: number) => {
      if (!lastTickRef.current) lastTickRef.current = timestamp;
      const dt = (timestamp - lastTickRef.current) / 1000;
      lastTickRef.current = timestamp;
      onYearChange(Math.min(TIME_MAX, year + dt * rate));
      if (year >= TIME_MAX) {
        setPlaying(false);
        lastTickRef.current = 0;
        return;
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      lastTickRef.current = 0;
    };
  }, [playing, turbo, year, onYearChange]);

  const yearFromX = (clientX: number) => {
    const rect = trackRef.current?.getBoundingClientRect();
    if (!rect) return year;
    const frac = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    return TIME_MIN + frac * (TIME_MAX - TIME_MIN);
  };

  const onPointerDown = (e: React.PointerEvent) => {
    draggingRef.current = true;
    setPlaying(false);
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    onYearChange(yearFromX(e.clientX));
  };

  const onPointerMove = (e: React.PointerEvent) => {
    if (!draggingRef.current) return;
    onYearChange(yearFromX(e.clientX));
  };

  const onPointerUp = () => {
    draggingRef.current = false;
  };

  const yearFrac = (year - TIME_MIN) / (TIME_MAX - TIME_MIN);
  const nowFrac = (TIME_NOW - TIME_MIN) / (TIME_MAX - TIME_MIN);
  const yearLabel = Math.round(year);
  const era = year < TIME_NOW ? 'history' : year > TIME_NOW + 0.1 ? 'forecast' : 'present';

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.9, delay: 1.3, ease }}
      className="pointer-events-auto absolute bottom-[calc(env(safe-area-inset-bottom)+56px)] left-1/2 z-30 w-[88%] -translate-x-1/2 select-none md:bottom-14 md:w-[min(640px,68%)]"
    >
      <div className="mb-2 flex items-baseline gap-3">
        <button
          type="button"
          onClick={() => setPlaying((p) => !p)}
          aria-label={playing ? 'pause' : 'play'}
          className="grid h-6 w-6 place-items-center rounded-full border border-white/[0.12] bg-[#04060D]/70 font-mono text-[10px] text-ink/80 backdrop-blur-md transition-colors hover:border-glow/40 hover:text-glow"
        >
          {playing ? '❚❚' : '▶'}
        </button>
        <button
          type="button"
          onClick={() => setTurbo((t) => !t)}
          aria-label={turbo ? 'normal speed' : 'double speed'}
          aria-pressed={turbo}
          className={`grid h-6 w-7 place-items-center rounded-full border bg-[#04060D]/70 font-mono text-[9px] tabular-nums backdrop-blur-md transition-colors ${
            turbo
              ? 'border-glow/60 text-glow'
              : 'border-white/[0.12] text-ink/65 hover:border-glow/40 hover:text-glow'
          }`}
        >
          2×
        </button>
        <span className="font-display text-[1.6rem] tabular-nums leading-none text-ink/95">
          {yearLabel}
        </span>
        <span className="font-mono text-[9px] uppercase tracking-[0.32em] text-muted">{era}</span>
      </div>

      <div
        ref={trackRef}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        className="relative h-7 cursor-grab touch-none rounded-full active:cursor-grabbing"
      >
        <div className="absolute inset-y-3 left-0 right-0 rounded-full bg-white/[0.05]" />
        <div
          className="absolute inset-y-3 left-0 rounded-full bg-gradient-to-r from-darkening/40 via-ink/15 to-brightening/55"
          style={{ width: `${yearFrac * 100}%` }}
        />
        <div
          className="absolute top-1 h-5 w-px bg-white/40"
          style={{ left: `${nowFrac * 100}%` }}
        />
        <div
          className="pointer-events-none absolute -top-[1px] -translate-x-1/2 rounded-full border border-glow/70 bg-glow/15 backdrop-blur-sm"
          style={{ left: `${yearFrac * 100}%`, width: 28, height: 28 }}
        />
        <div
          className="pointer-events-none absolute top-[10px] -translate-x-1/2 rounded-full bg-glow"
          style={{ left: `${yearFrac * 100}%`, width: 8, height: 8 }}
        />
      </div>

      <div className="mt-1.5 flex justify-between font-mono text-[9px] tabular-nums text-muted/70">
        <span>{TIME_MIN}</span>
        <span style={{ marginLeft: `calc(${nowFrac * 100}% - 12px)` }}>now</span>
        <span>{TIME_MAX}</span>
      </div>
    </motion.div>
  );
}
