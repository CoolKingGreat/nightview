import { AnimatePresence, motion } from 'motion/react';
import { useEffect, useRef, useState } from 'react';
import { streamChat } from '../lib/api';
import { GHOST_PROMPTS } from '../lib/prompts';
import type { AgentEvent, GlobeAction } from '../lib/types';

const ease = [0.16, 1, 0.3, 1] as const;

interface ChatMessage {
  id: number;
  role: 'user' | 'agent';
  text: string;
  streaming?: boolean;
}

interface Props {
  onGlobeAction: (action: GlobeAction) => void;
  onActive: (active: boolean) => void;
}

const PRETTY_TOOL_NAMES: Record<string, string> = {
  query_region: 'querying region',
  point_timeseries: 'reading time series',
  top_changers: 'ranking fastest changers',
  milestones_in_region: 'scanning milestones',
  compare_regions: 'comparing regions',
};

export function ChatOrb({ onGlobeAction, onActive }: Props) {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [toolStatus, setToolStatus] = useState<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const transcriptRef = useRef<HTMLDivElement>(null);
  const idRef = useRef(0);

  useEffect(() => {
    if (transcriptRef.current) {
      transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight;
    }
  }, [messages, toolStatus]);

  const send = async (override?: string) => {
    const text = (override ?? input).trim();
    if (!text || busy) return;

    const userId = ++idRef.current;
    const agentId = ++idRef.current;
    setMessages((m) => [
      ...m,
      { id: userId, role: 'user', text },
      { id: agentId, role: 'agent', text: '', streaming: true },
    ]);
    setInput('');
    setBusy(true);
    setToolStatus(null);
    onActive(true);

    // Snapshot prior turns before this new message is appended.
    // Drop the in-flight agent placeholder; only completed turns are sent.
    const history = messages
      .filter((m) => !m.streaming && m.text.trim())
      .map((m) => ({ role: m.role, text: m.text }));

    try {
      for await (const ev of streamChat(text, history) as AsyncIterable<AgentEvent<unknown>>) {
        if (ev.type === 'text') {
          setToolStatus(null);
          const delta = String(ev.data);
          setMessages((m) =>
            m.map((msg) => (msg.id === agentId ? { ...msg, text: msg.text + delta } : msg)),
          );
        } else if (ev.type === 'tool_call') {
          const data = ev.data as { name?: string };
          setToolStatus(PRETTY_TOOL_NAMES[data.name ?? ''] ?? 'querying data');
        } else if (ev.type === 'globe_action') {
          onGlobeAction(ev.data as GlobeAction);
        } else if (ev.type === 'error') {
          const data = ev.data as { message?: string };
          setMessages((m) =>
            m.map((msg) =>
              msg.id === agentId
                ? { ...msg, text: `(${data.message ?? 'unknown error'})`, streaming: false }
                : msg,
            ),
          );
        } else if (ev.type === 'done') {
          setMessages((m) =>
            m.map((msg) => (msg.id === agentId ? { ...msg, streaming: false } : msg)),
          );
        }
      }
    } catch {
      setMessages((m) =>
        m.map((msg) =>
          msg.id === agentId
            ? { ...msg, text: '(connection lost)', streaming: false }
            : msg,
        ),
      );
    } finally {
      setBusy(false);
      setToolStatus(null);
    }
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void send();
    }
  };

  return (
    <motion.aside
      initial={{ opacity: 0, x: 18 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.8, delay: 0.35, ease }}
      className="relative z-40 flex h-full min-h-0 flex-col bg-[#040610]/85 backdrop-blur-2xl md:border-l md:border-white/[0.05]"
    >
      <div className="relative px-6 pb-5 pt-12 md:pt-7">
        <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.32em] text-muted">
          <span className="inline-block h-1 w-1 rounded-full bg-glow/80 shadow-[0_0_6px_rgba(255,217,120,0.7)]" />
          ask nightview
        </div>
        <div className="mt-3 font-display text-[1.05rem] font-medium leading-[1.45] text-ink/90">
          Trace the lights changing the night.
        </div>
        <div className="absolute inset-x-6 bottom-0 h-px bg-gradient-to-r from-transparent via-white/[0.1] to-transparent" />
      </div>

      <div ref={transcriptRef} className="min-h-0 flex-1 overflow-y-auto px-6 py-6">
        {messages.length === 0 ? (
          <motion.div
            initial="hidden"
            animate="show"
            variants={{
              hidden: {},
              show: { transition: { staggerChildren: 0.08, delayChildren: 0.2 } },
            }}
            className="space-y-px"
          >
            <motion.div
              variants={{
                hidden: { opacity: 0 },
                show: { opacity: 1, transition: { duration: 0.6, ease } },
              }}
              className="mb-4 font-mono text-[9px] uppercase tracking-[0.32em] text-muted/70"
            >
              suggested
            </motion.div>
            {GHOST_PROMPTS.map((prompt) => (
              <motion.button
                key={prompt}
                type="button"
                disabled={busy}
                onClick={() => void send(prompt)}
                variants={{
                  hidden: { opacity: 0, y: 6 },
                  show: { opacity: 1, y: 0, transition: { duration: 0.55, ease } },
                }}
                whileHover={{ x: 3 }}
                transition={{ duration: 0.25, ease }}
                className="group flex w-full items-start gap-3 border-b border-white/[0.04] py-3.5 text-left font-body text-[13.5px] leading-relaxed text-ink/50 transition-colors hover:text-ink/95 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <span className="mt-[6px] inline-block h-[1px] w-2.5 bg-muted/60 transition-all duration-300 group-hover:w-5 group-hover:bg-glow/80" />
                <span className="flex-1">{prompt}</span>
              </motion.button>
            ))}
          </motion.div>
        ) : (
          <div className="space-y-6">
            <AnimatePresence initial={false}>
              {messages.map((msg) =>
                msg.role === 'user' ? (
                  <motion.div
                    key={msg.id}
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.35, ease }}
                    className="font-mono text-[10px] uppercase leading-relaxed tracking-[0.22em] text-muted"
                  >
                    <span className="mr-2 text-glow/70">›</span>
                    {msg.text}
                  </motion.div>
                ) : (
                  <motion.div
                    key={msg.id}
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.4, ease }}
                    className="whitespace-pre-wrap font-body text-[14px] leading-[1.78] text-ink/88"
                  >
                    {msg.text}
                    {msg.streaming && msg.text === '' && <TypingDots />}
                    {msg.streaming && msg.text !== '' && (
                      <span className="ml-[3px] inline-block h-[14px] w-px -mb-[2px] animate-pulse bg-glow/80 align-middle" />
                    )}
                  </motion.div>
                ),
              )}
            </AnimatePresence>
            <AnimatePresence>
              {toolStatus && (
                <motion.div
                  key={toolStatus}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.3 }}
                  className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.28em] text-muted"
                >
                  <span className="relative inline-flex h-1.5 w-1.5">
                    <span className="absolute inset-0 animate-ping rounded-full bg-glow/60" />
                    <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-glow/80" />
                  </span>
                  {toolStatus}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}
      </div>

      <div className="relative border-t border-white/[0.05] px-6 py-5">
        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          onFocus={() => onActive(true)}
          placeholder="ask about a city, country, or dark-sky change"
          rows={3}
          disabled={busy}
          className="min-h-[84px] w-full resize-none bg-transparent font-body text-[14px] leading-relaxed text-ink/90 placeholder:text-muted/60 outline-none disabled:opacity-50"
        />
        <div className="mt-3 flex items-center justify-end">
          <button
            type="button"
            disabled={!input.trim() || busy}
            onClick={() => void send()}
            className="group flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.32em] text-ink/70 transition-colors hover:text-glow disabled:cursor-not-allowed disabled:text-muted/35"
          >
            send
            <span className="inline-block transition-transform duration-300 group-hover:translate-x-1">
              →
            </span>
          </button>
        </div>
      </div>
    </motion.aside>
  );
}

function TypingDots() {
  return (
    <span className="inline-flex items-center gap-1">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="inline-block h-1 w-1 animate-pulse rounded-full bg-glow/70"
          style={{ animationDelay: `${i * 160}ms`, animationDuration: '1.3s' }}
        />
      ))}
    </span>
  );
}
