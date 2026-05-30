import { Component, type ReactNode } from 'react';

interface State {
  error: Error | null;
}

/**
 * Catches render errors so a bad state doesn't black out the entire page.
 * In dev, also logs the error to the console with React's stack trace.
 */
export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: { componentStack: string }) {
    console.error('[Nightview] render error:', error, info);
  }

  reset = () => this.setState({ error: null });

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="grid h-full w-full place-items-center bg-midnight p-8">
        <div className="max-w-md space-y-4 rounded-lg border border-white/[0.08] bg-[#04060D]/95 p-6 backdrop-blur-md">
          <div className="font-mono text-[10px] uppercase tracking-[0.3em] text-[#E67462]">
            something broke
          </div>
          <div className="font-display text-lg leading-snug text-ink/90">
            The visualization hit an unexpected state.
          </div>
          <div className="font-mono text-[11px] leading-relaxed text-muted">
            {this.state.error.message}
          </div>
          <button
            type="button"
            onClick={this.reset}
            className="font-mono text-[10px] uppercase tracking-[0.3em] text-ink/80 transition-colors hover:text-glow"
          >
            try to recover →
          </button>
        </div>
      </div>
    );
  }
}
