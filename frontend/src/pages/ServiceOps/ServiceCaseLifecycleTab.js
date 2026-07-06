/**
 * ServiceCaseLifecycleTab — equipment → service → billing closed-loop trace.
 *
 * One read-only timeline proving an asset's full journey is connected:
 * asset → fault → dispatch → on-site/labour → parts → resolution →
 * invoice → paid. Real data flows straight through (nothing mocked).
 *
 * Stages are click-through where a record exists:
 *   • Asset   → jumps to the case Details tab (asset record)  [onNavigate]
 *   • Parts   → expands the full parts-request breakdown inline
 *   • Invoice → opens the branded invoice PDF in a new tab
 *
 * Plus a "cost-to-serve" mini-bar splitting the job into labour vs
 * parts vs travel — turning the trace into an at-a-glance margin tool.
 *
 * Data: GET /api/svc/cases/{caseId}/lifecycle
 */
import { useEffect, useState } from 'react';
import {
  Wrench, AlertTriangle, Truck, Clock, Package, CheckCircle2,
  FileText, CreditCard, Loader2, Circle, Timer, PoundSterling,
  ChevronRight, ExternalLink,
} from 'lucide-react';
import { api } from '@/lib/api';
import { notify } from '@/components/notifications';

const STAGE_ICON = {
  asset: Wrench, fault: AlertTriangle, dispatch: Truck, onsite: Clock,
  parts: Package, resolution: CheckCircle2, invoice: FileText, paid: CreditCard,
};

// Cost-to-serve segments — order matters (renders left→right).
const COST_SEGMENTS = [
  { key: 'labour', label: 'Labour', color: '#4f46e5' },
  { key: 'parts',  label: 'Parts',  color: '#f59e0b' },
  { key: 'travel', label: 'Travel', color: '#0ea5e9' },
  { key: 'other',  label: 'Other',  color: '#94a3b8' },
];

function fmtDate(s) {
  if (!s) return null;
  try { return new Date(s).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }); }
  catch { return null; }
}

function CostToServeBar({ breakdown, total, cur, margin }) {
  if (!breakdown || !total || total <= 0) return null;
  const segs = COST_SEGMENTS
    .map((s) => ({ ...s, amount: Number(breakdown[s.key] || 0) }))
    .filter((s) => s.amount > 0);
  if (segs.length === 0) return null;

  const m = margin || {};
  const hasMargin = m.margin_total != null;
  const pct = m.margin_pct;
  const marginTone = pct == null ? '#64748b' : pct >= 40 ? '#059669' : pct >= 15 ? '#d97706' : '#dc2626';
  const missing = m.missing_cost || [];

  return (
    <div className="svc-card p-3" data-testid="lifecycle-cost-to-serve">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1.5 svc-muted text-[10px] font-bold uppercase tracking-wider">
          <PoundSterling size={12} /> Cost to serve
        </div>
        <span className="text-xs font-bold" style={{ color: 'var(--svc-text, #0f172a)' }}>{cur}{total.toFixed(2)}</span>
      </div>
      <div className="flex h-2.5 w-full overflow-hidden rounded-full" style={{ background: 'var(--svc-surface-2, #f1f5f9)' }}>
        {segs.map((s) => (
          <div
            key={s.key}
            title={`${s.label}: ${cur}${s.amount.toFixed(2)}`}
            data-testid={`cost-seg-${s.key}`}
            style={{ width: `${(s.amount / total) * 100}%`, background: s.color }}
          />
        ))}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
        {segs.map((s) => (
          <div key={s.key} className="flex items-center gap-1.5 text-[11px]" data-testid={`cost-legend-${s.key}`}>
            <span className="w-2 h-2 rounded-full shrink-0" style={{ background: s.color }} />
            <span className="svc-muted">{s.label}</span>
            <span className="font-semibold" style={{ color: 'var(--svc-text, #0f172a)' }}>
              {cur}{s.amount.toFixed(2)}
            </span>
            <span className="svc-muted">({Math.round((s.amount / total) * 100)}%)</span>
          </div>
        ))}
      </div>

      {/* Margin (charge vs internal cost) — only when a cost basis exists */}
      {hasMargin ? (
        <div className="mt-2.5 pt-2.5 flex items-center justify-between gap-2" style={{ borderTop: '1px solid var(--svc-border, #e2e8f0)' }} data-testid="lifecycle-margin">
          <div className="flex items-center gap-1.5">
            <span className="svc-muted text-[10px] font-bold uppercase tracking-wider">Margin</span>
            {m.cost_basis === 'partial' && missing.length > 0 && (
              <span className="text-[9px] svc-muted" data-testid="lifecycle-margin-partial">({missing.join(' + ')} cost not set)</span>
            )}
          </div>
          <div className="flex items-center gap-2 text-xs">
            <span className="svc-muted">cost {cur}{Number(m.internal_cost_total || 0).toFixed(2)}</span>
            <span className="font-bold" style={{ color: marginTone }} data-testid="lifecycle-margin-value">
              {cur}{Number(m.margin_total).toFixed(2)}{pct != null ? ` · ${pct}%` : ''}
            </span>
          </div>
        </div>
      ) : (
        <div className="mt-2.5 pt-2.5 text-[11px] svc-muted" style={{ borderTop: '1px solid var(--svc-border, #e2e8f0)' }} data-testid="lifecycle-margin-empty">
          Add part costs &amp; engineer pay rates to unlock job margin.
        </div>
      )}
    </div>
  );
}

export default function ServiceCaseLifecycleTab({ caseId, onNavigate }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [partsOpen, setPartsOpen] = useState(false);
  const [openingInvoice, setOpeningInvoice] = useState(false);

  useEffect(() => {
    let on = true;
    setLoading(true); setErr('');
    api.get(`/svc/cases/${caseId}/lifecycle`)
      .then((r) => { if (on) setData(r.data); })
      .catch((e) => { if (on) setErr(e.response?.data?.detail || 'Failed to load lifecycle'); })
      .finally(() => { if (on) setLoading(false); });
    return () => { on = false; };
  }, [caseId]);

  const openInvoicePdf = async (invoiceId) => {
    if (!invoiceId || openingInvoice) return;
    setOpeningInvoice(true);
    try {
      const r = await api.get(`/svc/engineer/invoices/${invoiceId}.pdf`, { responseType: 'blob' });
      const url = URL.createObjectURL(r.data);
      window.open(url, '_blank', 'noopener');
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (e) {
      notify?.error?.(e.response?.data?.detail || 'Could not open the invoice PDF.');
    }
    setOpeningInvoice(false);
  };

  if (loading) return <div className="flex items-center justify-center py-12"><Loader2 className="animate-spin svc-muted" size={20} /></div>;
  if (err) return <div className="svc-muted text-sm py-6" data-testid="lifecycle-error">{err}</div>;
  if (!data) return null;

  const s = data.summary || {};
  const CUR_SYM = { GBP: '£', USD: '$', EUR: '€' };
  const cur = CUR_SYM[s.invoice_currency] || s.invoice_currency || '£';
  const chips = [
    { label: 'Time to resolve', value: s.time_to_resolve_hours != null ? `${s.time_to_resolve_hours} h` : '—', icon: Timer },
    { label: 'Labour', value: `${s.labour_hours || 0} h`, icon: Clock },
    { label: 'Parts', value: s.parts_count || 0, icon: Package },
    { label: 'Invoice', value: s.invoice_total != null ? `${cur}${s.invoice_total}` : '—', icon: PoundSterling },
  ];

  // Per-stage click-through: returns an onClick or null.
  const stageAction = (st) => {
    if (st.key === 'asset' && st.done && onNavigate) {
      return { onClick: () => onNavigate('details'), hint: 'View asset record' };
    }
    if (st.key === 'parts' && (st.meta?.parts || []).length > 0) {
      return { onClick: () => setPartsOpen((o) => !o), hint: partsOpen ? 'Hide parts' : 'View parts request' };
    }
    if (st.key === 'invoice' && st.meta?.invoice_id) {
      return { onClick: () => openInvoicePdf(st.meta.invoice_id), hint: 'Open invoice PDF', external: true };
    }
    return null;
  };

  return (
    <div className="space-y-5" data-testid="lifecycle-tab">
      {/* Summary chips — founder emphasis: speed + cost-to-serve */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {chips.map((c) => (
          <div key={c.label} className="svc-card p-3" data-testid={`lifecycle-chip-${c.label.toLowerCase().replace(/\s+/g, '-')}`}>
            <div className="flex items-center gap-1.5 svc-muted text-[10px] font-bold uppercase tracking-wider">
              <c.icon size={12} /> {c.label}
            </div>
            <div className="text-lg font-bold mt-0.5" style={{ color: 'var(--svc-text, #0f172a)' }}>{c.value}</div>
          </div>
        ))}
      </div>

      {/* Cost-to-serve mini-bar (labour vs parts vs travel) */}
      <CostToServeBar breakdown={s.cost_breakdown} total={Number(s.cost_total || 0)} cur={cur} margin={s.margin} />

      {/* Paid status banner */}
      <div className="flex items-center gap-2 text-sm" data-testid="lifecycle-paid-status">
        <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold ${s.paid ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}`}>
          <span className={`w-2 h-2 rounded-full ${s.paid ? 'bg-emerald-500' : 'bg-amber-500'}`} />
          {s.paid ? 'Paid' : (s.invoice_status ? `Invoice ${s.invoice_status}` : 'Not invoiced')}
        </span>
        <span className="svc-muted text-xs">Service-to-cash trace</span>
      </div>

      {/* Vertical stage timeline */}
      <ol className="relative ml-1" data-testid="lifecycle-stages">
        {(data.stages || []).map((st, i) => {
          const Icon = STAGE_ICON[st.key] || Circle;
          const last = i === data.stages.length - 1;
          const action = stageAction(st);
          const RowTag = action ? 'button' : 'div';
          return (
            <li key={st.key} className="relative flex gap-3 pb-5" data-testid={`lifecycle-stage-${st.key}`}>
              {!last && <span className="absolute left-[15px] top-8 bottom-0 w-px" style={{ background: 'var(--svc-border, #e2e8f0)' }} />}
              <span className={`relative z-10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${st.done ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-400'}`}>
                <Icon size={15} />
              </span>
              <div className="min-w-0 flex-1 pt-0.5">
                <RowTag
                  type={action ? 'button' : undefined}
                  onClick={action?.onClick}
                  disabled={action && st.key === 'invoice' && openingInvoice}
                  data-testid={action ? `lifecycle-link-${st.key}` : undefined}
                  className={`w-full text-left ${action ? 'group cursor-pointer rounded-md -mx-1 px-1 py-0.5 hover:bg-black/[0.03] transition-colors' : ''}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <p className={`text-sm font-bold flex items-center gap-1.5 ${st.done ? '' : 'svc-muted'}`} style={st.done ? { color: 'var(--svc-text, #0f172a)' } : undefined}>
                      {st.label}
                      {action && (
                        st.key === 'invoice' && openingInvoice
                          ? <Loader2 size={13} className="animate-spin svc-muted" />
                          : action.external
                            ? <ExternalLink size={13} className="svc-muted opacity-60 group-hover:opacity-100" />
                            : <ChevronRight size={14} className="svc-muted opacity-60 group-hover:opacity-100 group-hover:translate-x-0.5 transition-transform" />
                      )}
                    </p>
                    {st.at && <span className="svc-muted text-[11px] shrink-0">{fmtDate(st.at)}</span>}
                  </div>
                  {st.detail && <p className="svc-muted text-xs mt-0.5">{st.detail}</p>}
                  {action?.hint && <p className="text-[10px] mt-0.5" style={{ color: 'var(--svc-accent, #4f46e5)' }}>{action.hint}</p>}
                </RowTag>

                {st.key === 'asset' && st.meta?.manufacturer && (
                  <p className="svc-muted text-[11px] mt-0.5">{[st.meta.manufacturer, st.meta.model].filter(Boolean).join(' ')}{st.meta.serial ? ` · SN ${st.meta.serial}` : ''}</p>
                )}

                {st.key === 'parts' && (st.meta?.parts || []).length > 0 && (
                  partsOpen ? (
                    <ul className="mt-2 space-y-1" data-testid="lifecycle-parts-detail">
                      {st.meta.parts.map((p, idx) => (
                        <li key={p.id || idx} className="flex items-center justify-between gap-2 text-[11px] rounded-md px-2 py-1.5" style={{ background: 'var(--svc-surface-2, #f1f5f9)' }}>
                          <span className="min-w-0 truncate">
                            <span className="font-semibold" style={{ color: 'var(--svc-text, #0f172a)' }}>{p.name}</span>
                            {p.sku ? <span className="svc-muted"> · {p.sku}</span> : null}
                          </span>
                          <span className="flex items-center gap-2 shrink-0">
                            {p.source ? <span className="svc-muted capitalize">{p.source}</span> : null}
                            <span className="font-semibold">×{p.qty}</span>
                            <span className={`px-1.5 py-0.5 rounded-full text-[9px] font-bold uppercase ${p.fulfilled ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}`}>
                              {p.fulfilled ? 'Fitted' : 'Pending'}
                            </span>
                          </span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <ul className="mt-1 flex flex-wrap gap-1">
                      {st.meta.parts.map((p, idx) => (
                        <li key={p.id || idx} className="text-[11px] px-2 py-0.5 rounded-full" style={{ background: 'var(--svc-surface-2, #f1f5f9)' }}>{p.name}{p.qty > 1 ? ` ×${p.qty}` : ''}</li>
                      ))}
                    </ul>
                  )
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
