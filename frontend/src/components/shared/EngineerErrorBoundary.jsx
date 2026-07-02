/**
 * Iter 220e6 — Engineer App route-scoped Error Boundary.
 *
 * Wraps the Engineer App routes so a render error on one job page
 * doesn't white-screen the engineer mid-job. Shows a recoverable
 * "Reload this screen" UI plus a one-tap "Report this" hook that
 * POSTs through the existing client_errors collector.
 */
import { Component } from 'react';
import { AlertOctagon, RefreshCcw } from 'lucide-react';
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';

export default class EngineerErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null, info: null, reported: false };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    this.setState({ info });
    // Best-effort error report (auth header optional — the backend
    // collector accepts anonymous reports too).
    try {
      const auth = localStorage.getItem('token') || '';
      axios.post(`${API}/client-errors`, {
        kind: 'react_render_error',
        message: String(error?.message || error),
        stack: String(error?.stack || ''),
        component_stack: String(info?.componentStack || ''),
        path: typeof window !== 'undefined' ? window.location.pathname : '',
        user_agent: typeof navigator !== 'undefined' ? navigator.userAgent : '',
        surface: 'engineer_app',
      }, auth ? { headers: { Authorization: `Bearer ${auth}` } } : {})
        .then(() => this.setState({ reported: true }))
        .catch(() => { /* don't bury original error in another error */ });
    } catch (e) {
      // swallowed intentionally
    }
  }

  reset = () => this.setState({ error: null, info: null, reported: false });

  render() {
    if (!this.state.error) {
      return <div className="pulse-font" style={{ display: 'contents' }}>{this.props.children}</div>;
    }
    return (
      <div className="min-h-[60vh] flex items-center justify-center px-6"
           data-testid="engineer-error-boundary">
        <div className="max-w-md w-full rounded-2xl border bg-white dark:bg-[var(--theme-surface)] shadow-sm p-6 text-center"
             style={{ borderColor: '#FECACA' }}>
          <div className="w-12 h-12 mx-auto rounded-full flex items-center justify-center mb-3"
               style={{ background: '#FEF2F2' }}>
            <AlertOctagon size={20} className="text-rose-600" />
          </div>
          <h2 className="text-base font-extrabold text-slate-900 dark:text-slate-100 mb-1">
            Something went wrong on this screen
          </h2>
          <p className="text-xs text-slate-500 mb-4">
            The rest of the app is still working. Tap reload to go back to a safe state —
            our team {this.state.reported ? 'has' : 'will'} get the crash report automatically.
          </p>
          <div className="space-y-2">
            <button onClick={this.reset} data-testid="engineer-eb-reset-btn"
                    className="w-full py-2 rounded-md text-sm font-semibold bg-[var(--color-info-ios)] text-white flex items-center justify-center gap-1.5">
              <RefreshCcw size={12} /> Reload this screen
            </button>
            <button onClick={() => { window.location.href = '/svc/engineer'; }} data-testid="engineer-eb-home-btn"
                    className="w-full py-2 rounded-md text-sm font-semibold border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200">
              Back to engineer home
            </button>
          </div>
          {process.env.NODE_ENV !== 'production' && (
            <details className="mt-4 text-left text-[10px] text-slate-400">
              <summary className="cursor-pointer">Dev: error details</summary>
              <pre className="mt-2 whitespace-pre-wrap break-all">
                {String(this.state.error?.message || this.state.error)}
                {'\n'}{String(this.state.info?.componentStack || '')}
              </pre>
            </details>
          )}
        </div>
      </div>
    );
  }
}
EngineerErrorBoundary.displayName = 'EngineerErrorBoundary';
