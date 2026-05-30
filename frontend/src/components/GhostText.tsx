import { AnimatePresence, motion } from 'motion/react';
import { useEffect, useState } from 'react';
import { GHOST_PROMPTS, GHOST_ROTATE_MS } from '../lib/prompts';

const ease = [0.16, 1, 0.3, 1] as const;

export function GhostText() {
  const [idx, setIdx] = useState(0);

  useEffect(() => {
    const id = setInterval(
      () => setIdx((i) => (i + 1) % GHOST_PROMPTS.length),
      GHOST_ROTATE_MS,
    );
    return () => clearInterval(id);
  }, []);

  return (
    <div className="relative h-7 w-full overflow-hidden text-center">
      <AnimatePresence mode="wait">
        <motion.span
          key={idx}
          className="absolute inset-0 font-body text-[1.05rem] italic tracking-wide text-ink/55"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          transition={{ duration: 1.1, ease }}
        >
          {GHOST_PROMPTS[idx]}
        </motion.span>
      </AnimatePresence>
    </div>
  );
}
