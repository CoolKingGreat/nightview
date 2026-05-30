import { AnimatePresence, motion } from 'motion/react';
import { useEffect, useState } from 'react';

const STORAGE_KEY = 'nightview-seen';
const ease = [0.16, 1, 0.3, 1] as const;

export function Welcome() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    try {
      if (!localStorage.getItem(STORAGE_KEY)) setOpen(true);
    } catch {
      setOpen(true);
    }
  }, []);

  const dismiss = () => {
    try {
      localStorage.setItem(STORAGE_KEY, '1');
    } catch {
      // ignore
    }
    setOpen(false);
  };

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' || e.key === 'Enter') dismiss();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          key="welcome"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.5, ease }}
          className="absolute inset-0 z-50 grid place-items-center bg-black/55 backdrop-blur-[6px]"
          onClick={dismiss}
        >
          <motion.div
            initial={{ opacity: 0, y: 12, scale: 0.985 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 4, scale: 0.99 }}
            transition={{ duration: 0.6, ease, delay: 0.05 }}
            onClick={(e) => e.stopPropagation()}
            className="relative max-w-[440px] rounded-[20px] border border-white/[0.07] bg-[#080B12]/90 px-9 py-8 shadow-[0_30px_80px_-30px_rgba(0,0,0,0.85)] backdrop-blur-xl"
          >
            <div className="font-mono text-[9px] uppercase tracking-[0.32em] text-glow/75">
              dark-sky atlas · 2012 → 2035
            </div>
            <h1 className="mt-3 font-display text-[2rem] font-semibold leading-none text-ink">
              Nightview
            </h1>

            <p className="mt-5 text-[14px] leading-[1.55] text-ink/72">
              An interactive globe of how the night sky has changed across Earth since 2012.
              Roughly 2,900 cities, colored by their VIIRS-measured trend rate — red where the
              night is vanishing fastest, blue where it&apos;s recovering.
            </p>

            <ul className="mt-5 space-y-2 text-[12.5px] leading-[1.4] text-ink/65">
              <li className="flex items-start gap-3">
                <span className="mt-[2px] font-mono text-[10px] tracking-[0.2em] text-glow/75">
                  ▶
                </span>
                <span>play or drag the bottom scrubber to sweep 2012 → 2035</span>
              </li>
              <li className="flex items-start gap-3">
                <span className="mt-[2px] font-mono text-[10px] tracking-[0.2em] text-glow/75">
                  ◉
                </span>
                <span>click any city for its brightness history and forecast</span>
              </li>
              <li className="flex items-start gap-3">
                <span className="mt-[2px] font-mono text-[10px] tracking-[0.2em] text-glow/75">
                  ✦
                </span>
                <span>ask the agent on the right anything about the data</span>
              </li>
            </ul>

            <button
              type="button"
              onClick={dismiss}
              className="mt-7 inline-flex items-center gap-2 rounded-full border border-glow/45 bg-glow/10 px-5 py-2 font-mono text-[10px] uppercase tracking-[0.3em] text-glow transition-colors hover:bg-glow/20"
            >
              begin
              <span className="text-[9px] tracking-[0.22em] text-glow/55">enter</span>
            </button>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
