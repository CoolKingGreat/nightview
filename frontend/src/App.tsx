import { AnimatePresence, motion, useDragControls } from 'motion/react';
import { useEffect, useRef, useState } from 'react';
import { ChatOrb } from './components/ChatOrb';
import { CitySearch } from './components/CitySearch';
import { Globe, type GlobeHandle, type HoverState } from './components/Globe';
import { HoverTooltip } from './components/HoverTooltip';
import { Inspector } from './components/Inspector';
import { Methodology } from './components/Methodology';
import { ObservatoryHud } from './components/ObservatoryHud';
import { TIME_NOW, TimeRibbon } from './components/TimeRibbon';
import { Welcome } from './components/Welcome';
import type { City, GlobeAction } from './lib/types';

const ease = [0.16, 1, 0.3, 1] as const;

export default function App() {
  const globeRef = useRef<GlobeHandle>(null);
  const [active, setActive] = useState(false);
  const [focused, setFocused] = useState(false);
  const [hover, setHover] = useState<HoverState | null>(null);
  const [inspected, setInspected] = useState<City | null>(null);
  const [year, setYear] = useState(TIME_NOW);
  const [chatOpenMobile, setChatOpenMobile] = useState(false);
  const [methodologyOpen, setMethodologyOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(() =>
    typeof window !== 'undefined' && window.matchMedia('(max-width: 767px)').matches,
  );
  const dragControls = useDragControls();

  useEffect(() => {
    const mq = window.matchMedia('(max-width: 767px)');
    const onChange = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);

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
    setChatOpenMobile(false);
  };

  const handleCitySelect = (city: City) => {
    setInspected(city);
    setChatOpenMobile(false);
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

  const handleCloseMobileSheet = () => {
    setChatOpenMobile(false);
    setInspected(null);
  };

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (inspected) setInspected(null);
        else if (chatOpenMobile) setChatOpenMobile(false);
        else if (focused) handleResetView();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [focused, inspected, chatOpenMobile]);

  const sheetOpenMobile = chatOpenMobile || !!inspected;

  return (
    <main className="grain relative h-full w-full overflow-hidden bg-black md:grid md:grid-cols-[minmax(0,1fr)_390px]">
      <section className="vignette relative h-full w-full overflow-hidden">
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: active ? 1 : 0.92 }}
          transition={{ duration: 1.4, ease }}
          className="absolute inset-0"
        >
          <Globe ref={globeRef} onHover={setHover} onSelect={handleCitySelect} year={year} />
        </motion.div>
        <ObservatoryHud onOpenMethodology={() => setMethodologyOpen(true)} />
        <CitySearch onSelect={handleCitySelect} />

        <HoverTooltip state={hover} />
        <TimeRibbon year={year} onYearChange={setYear} />

        {/* Color legend — desktop only (too crowded on phones) */}
        <motion.div
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.9, delay: 1.1, ease }}
          className="pointer-events-none absolute bottom-5 left-8 z-30 hidden select-none md:block"
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
              className="group absolute right-4 top-[110px] z-30 flex items-center gap-2 rounded-full border border-white/[0.08] bg-[#04060D]/70 px-3 py-1.5 font-mono text-[9px] uppercase tracking-[0.26em] text-ink/65 backdrop-blur-md transition-colors hover:border-glow/35 hover:text-glow md:right-8 md:top-[150px] md:px-3.5 md:text-[10px] md:tracking-[0.28em]"
            >
              <span className="text-base leading-none">↺</span>
              reset view
              <span className="ml-1 hidden text-[8px] tracking-[0.22em] text-muted/70 group-hover:text-glow/60 sm:inline">
                esc
              </span>
            </motion.button>
          )}
        </AnimatePresence>

        {/* Mobile-only FAB to open chat. Hidden when a sheet is already up. */}
        <AnimatePresence>
          {!sheetOpenMobile && (
            <motion.button
              key="fab"
              type="button"
              onClick={() => setChatOpenMobile(true)}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 12 }}
              transition={{ duration: 0.45, ease, delay: 0.4 }}
              className="absolute bottom-[148px] right-4 z-30 flex items-center gap-2 rounded-full border border-glow/45 bg-[#04060D]/90 px-4 py-2.5 font-mono text-[10px] uppercase tracking-[0.28em] text-glow shadow-[0_8px_24px_rgba(0,0,0,0.55)] backdrop-blur-md md:hidden"
              aria-label="ask nightview"
            >
              <span className="text-[12px] leading-none">✦</span>
              ask
            </motion.button>
          )}
        </AnimatePresence>
      </section>

      {/* Mobile sheet backdrop — transparent click-catcher so the globe stays visible above the sheet.
          Sits only above the sheet (h-40dvh) so it doesn't block taps on the visible globe-area HUD. */}
      <button
        type="button"
        aria-label="close panel"
        onClick={handleCloseMobileSheet}
        className={`fixed inset-x-0 top-0 z-40 h-[40dvh] bg-transparent transition-opacity duration-300 md:hidden ${
          sheetOpenMobile ? 'pointer-events-auto opacity-100' : 'pointer-events-none opacity-0'
        }`}
      />

      {/* Panel container.
          Mobile: draggable slide-up sheet (60dvh). Drag the top handle down to dismiss.
          Desktop: static right column, no transform, no drag. */}
      <motion.div
        drag={isMobile ? 'y' : false}
        dragListener={false}
        dragControls={dragControls}
        dragConstraints={{ top: 0, bottom: 0 }}
        dragElastic={{ top: 0, bottom: 0.5 }}
        onDragEnd={(_, info) => {
          if (info.offset.y > 90 || info.velocity.y > 500) handleCloseMobileSheet();
        }}
        animate={{ y: isMobile && !sheetOpenMobile ? '100%' : 0 }}
        transition={{ type: 'spring', stiffness: 320, damping: 36, mass: 0.9 }}
        className="fixed inset-x-0 bottom-0 z-50 h-[60dvh] overflow-hidden rounded-t-[18px] border-t border-white/[0.08] bg-[#040610] shadow-[0_-20px_60px_-15px_rgba(0,0,0,0.7)] md:relative md:inset-auto md:z-auto md:h-full md:min-h-0 md:rounded-none md:border-0 md:bg-transparent md:shadow-none"
      >
        {/* Drag affordance — 32px touch zone with the visible pill centered. Mobile only. */}
        <div
          onPointerDown={(e) => isMobile && dragControls.start(e)}
          className="absolute inset-x-0 top-0 z-[60] flex h-8 touch-none cursor-grab items-center justify-center active:cursor-grabbing md:hidden"
        >
          <div className="h-1 w-10 rounded-full bg-white/25" />
        </div>
        <button
          type="button"
          onClick={handleCloseMobileSheet}
          aria-label="close"
          className="absolute right-3 top-3 z-[60] grid h-8 w-8 place-items-center rounded-full border border-white/[0.1] bg-[#0A0D17]/85 font-mono text-[12px] text-ink/80 backdrop-blur md:hidden"
        >
          ✕
        </button>

        <div className="h-full">
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
        </div>
      </motion.div>

      <Welcome />
      <Methodology open={methodologyOpen} onClose={() => setMethodologyOpen(false)} />
    </main>
  );
}
