/**
 * The 4 ghost-text prompts that rotate in the collapsed chat orb. Order matters —
 * users scan first, hear story second, ask next. Locked during the design interview;
 * see SPEC.md §6.2 if updating.
 */
export const GHOST_PROMPTS = [
  'where is the night sky disappearing fastest?',
  'show me cities where you can still see the milky way',
  'how bright will st. louis be in 2035?',
  'compare night sky loss in india vs china',
];

export const GHOST_ROTATE_MS = 6000;
