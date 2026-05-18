/**
 * ModalErrorBoundary — catches React render errors inside modals/drawers
 * so they surface a readable error toast + console trace instead of a
 * silent white-screen "crash".
 *
 * Wrap any modal that handles user input (especially those with
 * complex form state or third-party Select / DatePicker / etc.).
 *
 * Iter 216h209 — added in response to Craig's "Class Builder crashed"
 * report which we couldn't reproduce. If it happens again, we now have
 * a stack trace.
 */
import React from 'react';
import { notify } from '@/components/notifications';
import { AlertTriangle } from 'lucide-react';

export class ModalErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    // Surface via console for our debugging + toast for the operator.
    // eslint-disable-next-line no-console
    console.error(
      `[ModalErrorBoundary:${this.props.label || 'unknown'}]`,
      error,
      info?.componentStack,
    );
    try {
      notify.error(
        `Something broke in "${this.props.label || 'this dialog'}". The team has been notified.`,
      );
    } catch (_) { /* notify may not be ready */ }
    // POST to backend telemetry endpoint if we have one (best-effort).
    try {
      if (typeof window !== 'undefined' && window.fetch) {
        const token = localStorage.getItem('token') || localStorage.getItem('member_token');
        window.fetch(`${process.env.REACT_APP_BACKEND_URL || ''}/api/client-errors`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({
            scope: 'modal',
            label: this.props.label || 'unknown',
            message: String(error?.message || error),
            stack: String(error?.stack || '').slice(0, 4000),
            component_stack: String(info?.componentStack || '').slice(0, 4000),
            url: window.location.href,
            ua: navigator.userAgent,
            ts: new Date().toISOString(),
          }),
        }).catch(() => {});
      }
    } catch (_) { /* never let telemetry break the boundary */ }
  }

  reset = () => this.setState({ error: null });

  render() {
    if (this.state.error) {
      return (
        <div
          role="alert"
          data-testid="modal-error-fallback"
          className="rounded-xl border border-rose-500/30 bg-rose-950/40 px-4 py-5 text-sm text-rose-100"
        >
          <div className="flex items-start gap-3">
            <AlertTriangle size={18} className="shrink-0 mt-0.5 text-rose-300" />
            <div className="flex-1">
              <p className="font-bold text-base mb-1">
                Couldn’t render this dialog
              </p>
              <p className="text-rose-200/80 text-xs leading-snug mb-3">
                {this.state.error?.message || 'Unknown error'} —
                we’ve logged the trace. Close this dialog and try again, or
                reload the page if it persists.
              </p>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={this.reset}
                  className="px-3 py-1.5 rounded-lg bg-rose-500/20 hover:bg-rose-500/30 text-rose-100 text-xs font-semibold"
                  data-testid="modal-error-retry"
                >
                  Retry
                </button>
                <button
                  type="button"
                  onClick={() => this.props.onClose?.()}
                  className="px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-xs font-semibold"
                  data-testid="modal-error-close"
                >
                  Close dialog
                </button>
              </div>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

export default ModalErrorBoundary;
