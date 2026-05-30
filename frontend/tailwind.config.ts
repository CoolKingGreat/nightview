import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        display: ['"Inter"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        body: ['"Inter"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      colors: {
        midnight: '#020308',
        observatory: '#080B12',
        ink: '#F4F7FB',
        glow: '#FFD978',
        brightening: '#C24E4A',
        darkening: '#5A7A9C',
        muted: '#667085',
      },
      transitionTimingFunction: {
        planetarium: 'cubic-bezier(0.16, 1, 0.3, 1)',
      },
    },
  },
  plugins: [],
} satisfies Config;
