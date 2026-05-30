import { AnimatePresence, motion } from 'motion/react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { fetchAllCities } from '../lib/api';
import type { City } from '../lib/types';

const ease = [0.16, 1, 0.3, 1] as const;

interface Props {
  onSelect: (city: City) => void;
}

export function CitySearch({ onSelect }: Props) {
  const [cities, setCities] = useState<City[]>([]);
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [activeIdx, setActiveIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchAllCities().then((res) => setCities(res.cities)).catch(() => undefined);
  }, []);

  useEffect(() => {
    const onClickAway = (e: MouseEvent) => {
      if (!containerRef.current?.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener('mousedown', onClickAway);
    return () => window.removeEventListener('mousedown', onClickAway);
  }, []);

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q || cities.length === 0) return [];
    const normalize = (s: string) =>
      s.toLowerCase().replace('st.', 'saint').replace('st ', 'saint ');
    const needle = normalize(q);
    const starts: City[] = [];
    const contains: City[] = [];
    for (const c of cities) {
      const n = normalize(c.name);
      if (n.startsWith(needle)) starts.push(c);
      else if (n.includes(needle)) contains.push(c);
    }
    return [...starts.sort((a, b) => b.pop - a.pop), ...contains.sort((a, b) => b.pop - a.pop)].slice(0, 7);
  }, [query, cities]);

  useEffect(() => {
    setActiveIdx(0);
  }, [query]);

  const pick = (city: City) => {
    onSelect(city);
    setQuery('');
    setOpen(false);
    inputRef.current?.blur();
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIdx((i) => Math.min(matches.length - 1, i + 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIdx((i) => Math.max(0, i - 1));
    } else if (e.key === 'Enter' && matches[activeIdx]) {
      e.preventDefault();
      pick(matches[activeIdx]);
    } else if (e.key === 'Escape') {
      setQuery('');
      setOpen(false);
      inputRef.current?.blur();
    }
  };

  return (
    <motion.div
      ref={containerRef}
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.9, delay: 0.45, ease }}
      className="pointer-events-auto absolute right-4 top-5 z-40 w-[180px] md:right-8 md:top-7 md:w-[240px]"
    >
      <div className="flex items-baseline justify-end gap-2 font-mono text-[9px] uppercase tracking-[0.3em] text-muted">
        <span className="text-glow/60">⌕</span>
        <span>find a city</span>
      </div>
      <div className="relative mt-1.5">
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => query && setOpen(true)}
          onKeyDown={onKeyDown}
          placeholder="paris, mumbai, st louis…"
          spellCheck={false}
          className="w-full border-b border-white/[0.1] bg-transparent pb-1.5 text-right font-body text-[13px] text-ink/90 placeholder:font-mono placeholder:text-[10.5px] placeholder:uppercase placeholder:tracking-[0.18em] placeholder:text-muted/55 outline-none transition-colors focus:border-glow/40"
        />
        <AnimatePresence>
          {open && matches.length > 0 && (
            <motion.ul
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.18, ease }}
              className="absolute right-0 top-full z-50 mt-2 w-full overflow-hidden rounded-md border border-white/[0.08] bg-[#04060D]/95 shadow-[0_8px_24px_rgba(0,0,0,0.5)] backdrop-blur-md"
            >
              {matches.map((m, i) => (
                <li key={`${m.name}-${m.lat}-${m.lon}`}>
                  <button
                    type="button"
                    onMouseEnter={() => setActiveIdx(i)}
                    onClick={() => pick(m)}
                    className={`flex w-full items-baseline justify-between px-3 py-2 text-left transition-colors ${
                      i === activeIdx ? 'bg-white/[0.05]' : ''
                    }`}
                  >
                    <span className="font-body text-[13px] text-ink/95">{m.name}</span>
                    <span className="ml-3 flex shrink-0 items-baseline gap-2 font-mono text-[9px] uppercase tracking-[0.18em] text-muted">
                      <span>{m.country}</span>
                      <span
                        className={
                          m.trend > 2 ? 'text-[#E67462]' : m.trend < 0 ? 'text-[#6CA8DC]' : 'text-ink/60'
                        }
                      >
                        {m.trend > 0 ? '+' : ''}
                        {m.trend.toFixed(1)}%
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </motion.ul>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}
