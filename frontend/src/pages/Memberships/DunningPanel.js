/**
 * DunningPanel — recover failed/overdue membership charges.
 *
 * Lists members whose Stripe subscription charge failed (billing_status
 * = past_due), with at-risk revenue, days overdue and reminders sent.
 * The operator can fire a staged reminder email, retry the failed Stripe
 * charge, or run the whole dunning cadence in one click. Backed by
 * /api/dunning/*.
 */
import { useCallback, useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { notify } from '@/components/notifications';
import {
  AlertCircle, Loader2, RefreshCw, Mail, RotateCcw, PlayCircle, Clock, Users,
} from 'lucide-react';

function gbp(n, ccy = 'gbp') {
  const sym = { gbp: '£', usd: '$', eur: '€' }[String(ccy).toLowerCase()] || '';
  return `${sym}${Number(n || 0).toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export default function DunningPanel() {
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [{ data: a }, { data: s }] = await Promise.all([
        api.get('/dunning/at-risk'), api.get('/dunning/summary'),
      ]);
      setRows(a.members || []);
      setSummary(s);
    } catch (e) { notify.error('Failed to load recovery data.'); }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const remind = async (id) => {
    setBusy(`remind-${id}`);
    try {
      const { data } = await api.post(`/dunning/${id}/remind`);
      notify.success(`Reminder sent (stage ${data.stage}).`);
      load();
    } catch (e) { notify.error(e.response?.data?.detail || 'Could not send reminder.'); }
    setBusy('');
  };

  const retry = async (id) => {
    setBusy(`retry-${id}`);
    try {
      const { data } = await api.post(`/dunning/${id}/retry`);
      notify.success(`Charge retried — invoice ${data.invoice_status}.`);
      load();
    } catch (e) { notify.error(e.response?.data?.detail || 'Retry failed.'); }
    setBusy('');
  };

  const runAll = async () => {
    setBusy('run');
    try {
      const { data } = await api.post('/dunning/run', {});
      notify.success(`Dunning run complete — ${data.reminders_sent} reminder(s) sent.`);
      load();
    } catch (e) { notify.error('Dunning run failed.'); }
    setBusy('');
  };

  return (
    <div className="space-y-5" data-testid="dunning-panel">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <AlertCircle size={18} style={{ color: '#d97706' }} />
          <div>
            <h2 className="text-lg font-extrabold" style={{ color: 'var(--theme-text)' }}>Recover revenue</h2>
            <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>Chase failed membership charges with staged reminders and retries.</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" onClick={runAll} disabled={busy === 'run' || rows.length === 0}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-bold text-white disabled:opacity-50"
            style={{ background: '#d97706' }} data-testid="dunning-run-all">
            {busy === 'run' ? <Loader2 size={14} className="animate-spin" /> : <PlayCircle size={14} />} Run dunning
          </button>
          <button type="button" onClick={load} className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold"
            style={{ border: '1px solid var(--theme-border)', color: 'var(--theme-text)' }} data-testid="dunning-refresh">
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Refresh
          </button>
        </div>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-3 gap-2">
        {[
          { label: 'At risk', value: summary?.at_risk_count ?? 0, icon: Users },
          { label: 'At-risk revenue', value: gbp(summary?.at_risk_revenue), icon: AlertCircle },
          { label: 'Never reminded', value: summary?.never_reminded ?? 0, icon: Clock },
        ].map((c) => (
          <div key={c.label} className="rounded-xl p-3" style={{ background: 'var(--theme-surface)', border: '1px solid var(--theme-border)' }} data-testid={`dunning-stat-${c.label.toLowerCase().replace(/\s+/g, '-')}`}>
            <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}><c.icon size={11} /> {c.label}</div>
            <div className="text-lg font-extrabold mt-0.5" style={{ color: 'var(--theme-text)' }}>{c.value}</div>
          </div>
        ))}
      </div>

      {loading ? (
        <div className="flex justify-center py-10"><Loader2 className="animate-spin" style={{ color: 'var(--theme-text-muted)' }} /></div>
      ) : rows.length === 0 ? (
        <div className="text-center py-10 rounded-xl" style={{ background: 'var(--theme-surface)', border: '1px dashed var(--theme-border)' }} data-testid="dunning-empty">
          <p className="text-sm font-semibold" style={{ color: 'var(--theme-text)' }}>All caught up 🎉</p>
          <p className="text-xs mt-1" style={{ color: 'var(--theme-text-muted)' }}>No failed or overdue membership charges right now.</p>
        </div>
      ) : (
        <ul className="space-y-2" data-testid="dunning-list">
          {rows.map((r) => (
            <li key={r.id} className="rounded-xl border p-3 flex items-center gap-3 flex-wrap" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }} data-testid={`dunning-row-${r.id}`}>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-bold" style={{ color: 'var(--theme-text)' }}>{r.member_name}</span>
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider"
                    style={{ background: r.days_past_due >= 14 ? 'rgba(239,68,68,0.14)' : 'rgba(245,158,11,0.14)', color: r.days_past_due >= 14 ? '#b91c1c' : '#b45309' }}>
                    {r.days_past_due}d overdue
                  </span>
                </div>
                <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>
                  {r.plan_name} · <span className="font-semibold">{gbp(r.amount, r.currency)}</span> · {r.reminders_sent} reminder(s) sent
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button type="button" onClick={() => remind(r.id)} disabled={busy === `remind-${r.id}`}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold disabled:opacity-50"
                  style={{ border: '1px solid var(--theme-border)', color: 'var(--theme-text)' }} data-testid={`dunning-remind-${r.id}`}>
                  {busy === `remind-${r.id}` ? <Loader2 size={12} className="animate-spin" /> : <Mail size={12} />} Remind
                </button>
                <button type="button" onClick={() => retry(r.id)} disabled={busy === `retry-${r.id}` || !r.has_subscription}
                  title={r.has_subscription ? 'Retry the failed Stripe charge' : 'No Stripe subscription on file'}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold text-white disabled:opacity-40"
                  style={{ background: 'var(--color-brand-blue,#1d4ed8)' }} data-testid={`dunning-retry-${r.id}`}>
                  {busy === `retry-${r.id}` ? <Loader2 size={12} className="animate-spin" /> : <RotateCcw size={12} />} Retry charge
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
