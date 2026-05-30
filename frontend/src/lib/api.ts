import type { AgentEvent } from './types';

const API_BASE = (import.meta.env.VITE_BACKEND_URL || '').replace(/\/$/, '');
const url = (p: string) => `${API_BASE}${p}`;

export interface ChatTurn {
  role: 'user' | 'agent';
  text: string;
}

/**
 * Stream typed agent events from POST /api/chat (SSE).
 * Each `data: { ... }` line becomes one yielded AgentEvent.
 */
export async function* streamChat(
  message: string,
  history: ChatTurn[] = [],
  signal?: AbortSignal,
): AsyncIterable<AgentEvent> {
  let res: Response;
  try {
    res = await fetch(url('/api/chat'), {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ message, history }),
      signal,
    });
  } catch (err) {
    yield { type: 'error', data: { message: (err as Error).message || 'network error' } };
    return;
  }

  if (!res.ok || !res.body) {
    const text =
      res.status === 429
        ? 'rate limit reached — try tomorrow'
        : `request failed (${res.status})`;
    yield { type: 'error', data: { message: text } };
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let separatorIdx;
    while ((separatorIdx = buffer.indexOf('\n\n')) !== -1) {
      const chunk = buffer.slice(0, separatorIdx);
      buffer = buffer.slice(separatorIdx + 2);
      for (const line of chunk.split('\n')) {
        if (!line.startsWith('data: ')) continue;
        const json = line.slice(6);
        try {
          yield JSON.parse(json) as AgentEvent;
        } catch (e) {
          console.warn('malformed SSE event', json, e);
        }
      }
    }
  }
}

export async function fetchTopChangers(direction: 'brightening' | 'darkening', n = 5) {
  const res = await fetch(url(`/api/top_changers?direction=${direction}&n=${n}`));
  if (!res.ok) throw new Error(`top_changers ${res.status}`);
  return res.json() as Promise<{ places: import('./types').Place[] }>;
}

export async function fetchAllCities() {
  const res = await fetch(url('/api/cities'));
  if (!res.ok) throw new Error(`cities ${res.status}`);
  return res.json() as Promise<{ cities: import('./types').City[] }>;
}

export async function fetchPoint(lat: number, lon: number) {
  const res = await fetch(url('/api/point'), {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ lat, lon }),
  });
  if (!res.ok) throw new Error(`point ${res.status}`);
  return res.json();
}
