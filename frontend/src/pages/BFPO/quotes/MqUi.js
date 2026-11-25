import './modOps.css';
import { STATUS_LABEL } from './modQuotesApi';

const TONE = {
  draft: 'neutral', pending_approval: 'warn', approved: 'info', approved_not_published: 'info', published: 'info',
  customer_review: 'info', authorisation_submitted: 'warn', accepted: 'ok', handed_over: 'ok', setup_complete: 'ok',
  verified: 'ok', submitted: 'warn', awaiting_setup: 'warn', declined: 'bad', withdrawn: 'neutral', expired: 'bad',
  superseded: 'neutral', not_selected: 'neutral', unverified: 'warn', test_data: 'bad', poa: 'neutral', historical: 'warn',
  live: 'ok', preview: 'warn',
};

export function StatusChip({ status, label }) {
  return (
    <span className={`mq-status mq-tone-${TONE[status] || 'neutral'}`} data-testid={`mq-status-${status}`}>
      {label || STATUS_LABEL[status] || String(status || '').replace(/_/g, ' ')}
    </span>
  );
}

export function Btn({ icon: Icon, children, variant = 'secondary', size, loading, className = '', ...p }) {
  return (
    <button type="button" {...p} disabled={p.disabled || loading}
      className={`mq-btn mq-btn--${variant}${size === 'sm' ? ' mq-btn--sm' : ''} ${className}`}>
      {loading ? <span className="mq-spin" aria-hidden /> : Icon ? <Icon size={15} aria-hidden /> : null}
      {children}
    </button>
  );
}

export function Banner({ tone = 'warn', icon: Icon, children, testid }) {
  return (
    <div className={`mq-banner mq-banner--${tone}`} role="status" data-testid={testid}>
      {Icon && <Icon size={18} className="flex-none mt-0.5" aria-hidden />}
      <div className="min-w-0">{children}</div>
    </div>
  );
}

export function Empty({ icon: Icon, title, sub, action, testid }) {
  return (
    <div className="mq-card px-6 py-12 text-center" data-testid={testid}>
      {Icon && <Icon size={28} className="mx-auto mq-muted" aria-hidden />}
      <div className="mt-3 font-semibold">{title}</div>
      {sub && <div className="text-sm mt-1 mq-muted max-w-md mx-auto">{sub}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Skeleton({ rows = 3 }) {
  return (
    <div className="space-y-2" data-testid="mq-loading" aria-busy="true">
      {Array.from({ length: rows }, (_, i) => <div key={i} className="mq-skel h-12" />)}
    </div>
  );
}

export function Field({ label, children, className = '' }) {
  return (
    <div className={className}>
      <div className="mq-label">{label}</div>
      <div className="text-sm mt-0.5 break-words">{children}</div>
    </div>
  );
}
