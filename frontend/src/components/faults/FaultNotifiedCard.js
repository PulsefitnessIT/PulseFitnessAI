import { useEffect, useState } from 'react';
import axios from 'axios';
import { CheckCircle, CheckCheck, Check, XCircle, HelpCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';

/**
 * One "Notified" card for a fault (replaces the separate "Notified when
 * logged" + "Sent to <supplier>" cards). Every recipient is listed once with
 * a tick showing whether the email provider confirmed delivery to their inbox:
 *   ✓✓ green  delivered      ✓ grey  sent, awaiting confirmation
 *   ✕ red    not delivered  ? grey  not tracked (older faults)
 */
const ROLE_BADGE = {
  pulse: { label: 'Pulse', cls: 'bg-sky-500/20 text-sky-600 dark:text-sky-300' },
  overseas: { label: 'Service provider', cls: 'bg-amber-500/20 text-amber-700 dark:text-amber-300' },
  supplier: { label: 'Supplier', cls: 'bg-zinc-500/20 text-zinc-600 dark:text-zinc-300' },
};

const STATUS = {
  delivered: { Icon: CheckCheck, cls: 'text-emerald-500', label: 'Delivered to inbox' },
  pending: { Icon: Check, cls: 'text-zinc-400', label: 'Sent — waiting for delivery confirmation' },
  bounced: { Icon: XCircle, cls: 'text-red-500', label: 'Not delivered (bounced)' },
  failed: { Icon: XCircle, cls: 'text-red-500', label: 'Not delivered — Master Admin → Email log can resend it' },
  unknown: { Icon: HelpCircle, cls: 'text-zinc-400', label: 'Delivery not tracked for this older fault' },
};

function fallbackRecipients(issue) {
  const list = (Array.isArray(issue.notified_recipients) ? issue.notified_recipients : []).map((r) => ({
    role: r.role, name: r.name, email: r.email, at: r.at,
    status: r.delivery_status || (r.delivered === false ? 'failed' : 'pending'),
  }));
  const sc = issue.supplier_case;
  if (sc?.supplier_email && !list.some((r) => (r.email || '').toLowerCase() === sc.supplier_email.toLowerCase())) {
    list.push({ role: 'supplier', name: sc.supplier_name, email: sc.supplier_email, at: issue.auto_dispatched_at, status: 'pending' });
  }
  return list;
}

export default function FaultNotifiedCard({ issue, API }) {
  const [recipients, setRecipients] = useState(() => fallbackRecipients(issue));
  const hasAny = recipients.length > 0 || !!issue.supplier_case?.supplier_name;

  useEffect(() => {
    setRecipients(fallbackRecipients(issue));
    if (!issue?.id) return undefined;
    let cancelled = false;
    const token = localStorage.getItem('token');
    axios.get(`${API}/issues/${issue.id}/delivery-status`, { headers: { Authorization: `Bearer ${token}` } })
      .then((res) => { if (!cancelled && Array.isArray(res.data?.recipients)) setRecipients(res.data.recipients); })
      .catch(() => { /* keep the fallback list */ });
    return () => { cancelled = true; };
  }, [issue?.id, API]);

  if (!hasAny) return null;
  const firstAt = recipients.find((r) => r.at)?.at;
  const token = issue.supplier_case?.token;

  return (
    <div className="p-4 rounded-xl bg-emerald-500/5 border border-emerald-500/20" data-testid={`issue-notified-card-${issue.id}`}>
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-2">
          <CheckCircle size={14} className="text-emerald-500" />
          <span className="text-[var(--color-text-muted)] text-xs uppercase tracking-wide">Notified</span>
        </div>
        {token && (
          <Button size="sm" variant="outline"
            onClick={() => window.open(`/supplier/case/${token}?view=site`, '_blank', 'noopener')}
            className="border-emerald-500/40 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-500/20 text-xs h-7"
            data-testid={`supplier-sent-view-${issue.id}`}>
            View card
          </Button>
        )}
      </div>
      <div className="space-y-1.5">
        {recipients.map((r, i) => {
          const badge = ROLE_BADGE[r.role] || ROLE_BADGE.supplier;
          const st = STATUS[r.status] || STATUS.unknown;
          const { Icon } = st;
          return (
            <div key={`${r.email || i}-${i}`} className="flex items-center justify-between gap-3 text-sm" data-testid={`issue-notified-${issue.id}-${i}`}>
              <div className="min-w-0 flex items-center gap-2">
                <span className={`text-[9px] uppercase font-bold px-1.5 py-0.5 rounded shrink-0 ${badge.cls}`}>{badge.label}</span>
                <span className="text-[var(--theme-text,#fff)] font-medium truncate">{r.name || r.email}</span>
                <span className={`inline-flex shrink-0 ${st.cls}`} title={st.label} aria-label={st.label}
                  data-testid={`issue-notified-tick-${issue.id}-${i}`} data-status={r.status}>
                  <Icon size={15} strokeWidth={2.5} />
                </span>
              </div>
              <span className="text-[var(--color-text-muted)] text-xs truncate min-w-0">{r.email}</span>
            </div>
          );
        })}
      </div>
      <p className="text-[11px] text-[var(--color-text-muted)] mt-2">
        Emailed {firstAt ? new Date(firstAt).toLocaleString() : 'when the job was logged'}.{' '}
        <span className="inline-flex items-center gap-1"><CheckCheck size={11} className="text-emerald-500" /> = delivered to their inbox</span>
      </p>
    </div>
  );
}
