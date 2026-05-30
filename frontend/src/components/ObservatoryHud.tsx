import { motion } from 'motion/react';
import { useEffect, useState } from 'react';

const ease = [0.16, 1, 0.3, 1] as const;

function currentUtc(): string {
  const d = new Date();
  const pad = (n: number) => n.toString().padStart(2, '0');
  return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;
}

export function ObservatoryHud() {
  const [utc, setUtc] = useState(currentUtc());

  useEffect(() => {
    const id = setInterval(() => setUtc(currentUtc()), 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <>
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.9, delay: 0.2, ease }}
        className="pointer-events-none absolute left-4 top-5 z-30 select-none md:left-8 md:top-7"
      >
        <div className="font-display text-[1rem] font-semibold leading-none tracking-[0.02em] text-ink/90 md:text-[1.2rem]">
          Nightview
        </div>
        <div className="mt-2 font-mono text-[8px] uppercase tracking-[0.28em] text-muted md:text-[9px] md:tracking-[0.3em]">
          dark-sky atlas · 2012 baseline
        </div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.9, delay: 0.55, ease }}
        className="pointer-events-none absolute right-8 top-[88px] z-30 hidden text-right md:block"
      >
        <div className="font-mono text-[9px] uppercase tracking-[0.3em] text-muted">
          utc
        </div>
        <div className="mt-1 font-mono text-[13px] tabular-nums text-ink/74">
          {utc}
        </div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.9, delay: 0.85, ease }}
        className="pointer-events-none absolute bottom-2 right-8 z-30 hidden text-right md:block"
      >
        <div className="font-mono text-[9px] uppercase leading-relaxed tracking-[0.28em] text-muted/80">
          data · nasa viirs day-night band
          <br />
          built by aryan valsa
        </div>
      </motion.div>
    </>
  );
}
