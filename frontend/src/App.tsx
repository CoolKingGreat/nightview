import { AnimatePresence, motion } from 'motion/react';
import { useEffect, useRef, useState } from 'react';
import { ChatOrb } from './components/ChatOrb';
import { CitySearch } from './components/CitySearch';
import { Globe, type GlobeHandle, type HoverState } from './components/Globe';
import { HoverTooltip } from './components/HoverTooltip';
import { Inspector } from './components/Inspector';
import { ObservatoryHud } from './components/ObservatoryHud';
import { TIME_NOW, TimeRibbon } from './components/TimeRibbon';
import type { City, GlobeAction } from './lib/types';

const ease = [0.16, 1, 0.3, 1] as const;

export default function App() {
  const globeRef = useRef<GlobeHandle>(null);
  const [active, setActive] = useState(false);
  const [focused, setFocused] = useState(false);
  const [hover, setHover] = useState<HoverState | null>(null);
  const [inspected, setInspected] = useState<City | null>(null);
  const [year, setYear] = useState(TIME_NOW);

  const handleGlobeAction = (action: GlobeAction) => {
    globeRef.current?.applyAction(action);
    if (action.type === 'fly_to' || action.type === 'highlight_cells') {
      setFocused(true);
    }
  };

  const handleActive = (next: boolean) => {
    setActive(next);
    globeRef.current?.setAutoRotate(!next && !focused && !inspected);
  };

  const handleResetView = () => {
    globeRef.current?.resetView();
    setFocused(false);
    setInspected(null);
  };

  const handleCitySelect = (city: City) => {
    setInspected(city);
    setHover(null);
    globeRef.current?.setAutoRotate(false);
    globeRef.current?.applyAction({
      type: 'fly_to',
      payload: { lat: city.lat, lon: city.lon, label: city.name },
    });
    setFocused(true);
  };

  const handleBackToChat = () => {
    setInspected(null);
  };

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (inspected) {
          setInspected(null);
        } else if (focused) {
          handleResetView();
        }
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [focused, inspected]);

  return (
    <main className="grain relative grid h-full w-full grid-cols-[minmax(0,1fr)_390px] overflow-hidden bg-black">
      <section className="vignette relative min-w-0 overflow-hidden">
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: active ? 1 : 0.92 }}
          transition={{ duration: 1.4, ease }}
          className="absolute inset-0"
        >
          <Globe ref={globeRef} onHover={setHover} onSelect={handleCitySelect} year={year} />
        </motion.div>
        <ObservatoryHud />
        <CitySearch onSelect={handleCitySelect} />

        <HoverTooltip state={hover} />
        <TimeRibbon year={year} onYearChange={setYear} />

        <motion.div
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.9, delay: 1.1, ease }}
          className="pointer-events-none absolute bottom-5 left-8 z-30 select-none"
        >
          <div className="mb-2 font-mono text-[9px] uppercase tracking-[0.3em] text-muted">
            change since 2012 · %/yr
          </div>
          <div className="flex items-center gap-2">
            <span className="font-mono text-[10px] tabular-nums text-ink/70">−3</span>
            <div
              className="h-1.5 w-44 rounded-full"
              style={{
                background:
                  'linear-gradient(to right, rgb(90,160,220), rgb(200,210,225), rgb(255,235,190), rgb(245,160,110), rgb(220,90,60))',
              }}
            />
            <span className="font-mono text-[10px] tabular-nums text-ink/70">+8</span>
          </div>
          <div className="mt-1 flex w-44 justify-between pl-6 font-mono text-[8px] uppercase tracking-[0.22em] text-muted/70">
            <span>darkening</span>
            <span>brightening</span>
          </div>
        </motion.div>

        <AnimatePresence>
          {focused && !inspected && (
            <motion.button
              key="reset"
              type="button"
              onClick={handleResetView}
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.45, ease }}
              className="group absolute right-8 top-[150px] z-30 flex items-center gap-2 rounded-full border border-white/[0.08] bg-[#04060D]/70 px-3.5 py-1.5 font-mono text-[10px] uppercase tracking-[0.28em] text-ink/65 backdrop-blur-md transition-colors hover:border-glow/35 hover:text-glow"
            >
              <span className="text-base leading-none">↺</span>
              reset view
              <span className="ml-1 hidden text-[8px] tracking-[0.22em] text-muted/70 group-hover:text-glow/60 sm:inline">
                esc
              </span>
            </motion.button>
          )}
        </AnimatePresence>
      </section>

      <AnimatePresence mode="wait">
        {inspected ? (
          <Inspector
            key={`inspect-${inspected.lat},${inspected.lon}`}
            city={inspected}
            year={year}
            onBack={handleBackToChat}
          />
        ) : (
          <ChatOrb key="chat" onGlobeAction={handleGlobeAction} onActive={handleActive} />
        )}
      </AnimatePresence>
    </main>
  );
}
