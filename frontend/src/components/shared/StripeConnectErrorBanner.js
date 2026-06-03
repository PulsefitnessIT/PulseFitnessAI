/**
 * StripeConnectErrorBanner — actionable banner shown on Stripe Connect screens
 * when the platform's Connect setup is incomplete (e.g. the loss-liability
 * "platform profile" hasn't been completed). Surfaces a clear message + a
 * direct link to the Stripe Dashboard instead of a raw Stripe error string.
 *
 * `error` shape: { code, message, help_url } (the backend `detail` object).
 */
import { AlertTriangle, ExternalLink } from 'lucide-react';

export default function StripeConnectErrorBanner({ error }) {
  if (!error) return null;
  const message = error.message || 'Your Stripe Connect setup needs to be completed before onboarding can start.';
  const helpUrl = error.help_url;
  return (
    <div
      className="rounded-xl border border-amber-300 bg-amber-50 p-4 flex items-start gap-3"
      data-testid="stripe-connect-error-banner"
    >
      <AlertTriangle size={18} className="text-amber-600 shrink-0 mt-0.5" />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-bold text-amber-900">Finish your Stripe Connect setup</p>
        <p className="text-xs text-amber-800 mt-0.5 leading-relaxed">{message}</p>
        {helpUrl && (
          <a
            href={helpUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 mt-2 text-xs font-bold text-amber-900 underline hover:text-amber-950"
            data-testid="stripe-connect-error-link"
          >
            Open Stripe Connect settings <ExternalLink size={12} />
          </a>
        )}
      </div>
    </div>
  );
}
