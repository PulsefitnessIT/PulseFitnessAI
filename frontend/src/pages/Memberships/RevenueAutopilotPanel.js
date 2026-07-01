/**
 * RevenueAutopilotPanel — Phase 1 of Pulse Fitness Autopilot.
 *
 * A supervised agent that recovers at-risk membership revenue: it detects
 * failed charges + churn signals, then (per the org's autonomy level) auto-
 * sends reversible recovery emails and queues money actions (card retries)
 * for human approval. Backed by /api/autopilot/revenue/*.
 */
import { useCallback, useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { notify } from '@/components/notifications';
import {
  Bot, Loader2, RefreshCw, PlayCircle, ShieldCheck, AlertTriangle,
  CheckCircle2, Clock, Lightbulb, XCircle, Sparkles, Settings2,
} from 'lucide-react';

function gbp(n, ccy = 'gbp') {
  const sym = { gbp: '£', usd: '$', eur: '€' }[String(ccy).toLowerCase()] || '£';
  return `${sym}${Number(n || 0).toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

const LEVELS = [
  { id: 'off', label: 'Off', desc: 'Autopilot does nothing.' },
  { id: 'suggest', label: 'Suggest', desc: 'Proposes actions — you run them.' },
  { id: 'act', label: 'Act & notify', desc: 'Auto-sends emails; asks before money. (Recommended)' },
  { id: 'auto', label: 'Autonomous', desc: 'Runs everything within your policy.' },
];

const STATUS_META = {
  executed: { icon: CheckCircle2, cls: 'text-emerald-600', label: 'Done' },
  pending_approval: { icon: Clock, cls: 'text-amber-600', label: 'Needs approval' },
  suggested: { icon: Lightbulb, cls: 'text-sky-600', label: 'Suggested' },
  approved: { icon: CheckCircle2, cls: 'text-emerald-600', label: 'Approved' },
  rejected: { icon: XCircle, cls: 'text-zinc-400', label: 'Rejected' },
  failed: { icon: AlertTriangle, cls: 'text-rose-600', label: 'Failed' },
};

function Stat({ label, value, sub, testId }) {
  return (
    <div className="theme-card rounded-2xl p-4" data-testid={testId}>
      <div className="text-2xl font-bold" style={{ color: 'var(--theme-text)' }}>{value}</div>
      <div className="text-sm" style={{ color: 'var(--theme-text-muted)' }}>{label}</div>
      {sub != null && <div className="text-xs mt-1" style={{ color: 'var(--theme-text-muted)' }}>{sub}</div>}
    </div>
  );
}

export default function RevenueAutopilotPanel() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data: d } = await api.get('/autopilot/revenue/overview');
      setData(d);
    } catch (e) { notify.error('Failed to load Autopilot.'); }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const saveSettings = async (patch) => {
    setBusy('settings');
    try {
      const { data: s } = await api.put('/autopilot/revenue/settings', patch);
      setData((prev) => ({ ...prev, settings: s }));
      notify.success('Autopilot settings updated.');
    } catch (e) { notify.error('Could not update settings.'); }
    setBusy('');
  };

  const runNow = async (dryRun) => {
    setBusy(dryRun ? 'preview' : 'run');
    try {
      const { data: r } = await api.post('/autopilot/revenue/run', { dry_run: dryRun });
      const c = r.counts || {};
      if (r.skipped) notify.info('Autopilot is currently off — turn it on or use Preview.');
      else if (dryRun) notify.success(`Preview: ${r.planned} action(s) Autopilot would take.`);
      else notify.success(`Ran: ${c.executed || 0} sent · ${c.pending_approval || 0} need approval.`);
      await load();
    } catch (e) { notify.error('Autopilot run failed.'); }
    setBusy('');
  };

  const decide = async (id, approve) => {
    setBusy(id);
    try {
      await api.post(`/autopilot/revenue/actions/${id}/${approve ? 'approve' : 'reject'}`);
      notify.success(approve ? 'Action approved.' : 'Action rejected.');
      await load();
    } catch (e) { notify.error(e?.response?.data?.detail || 'Action failed.'); }
    setBusy('');
  };

  if (loading) {
    return <div className="flex items-center justify-center py-20"><Loader2 className="w-6 h-6 animate-spin" /></div>;
  }
  if (!data) return null;

  const s = data.settings || {};
  const ar = data.at_risk || {};
  const pending = (data.recent_actions || []).filter((a) => a.status === 'pending_approval');

  return (
    <div className="space-y-6" data-testid="revenue-autopilot-panel">
      {/* Hero */}
      <div className="theme-card rounded-2xl p-5 flex flex-col sm:flex-row sm:items-center gap-4">
        <div className="flex items-center gap-3 flex-1">
          <div className="w-11 h-11 rounded-xl flex items-center justify-center"
            style={{ background: 'rgba(29,78,216,0.1)' }}>
            <Bot className="w-6 h-6" style={{ color: '#1d4ed8' }} />
          </div>
          <div>
            <h2 className="text-lg font-bold" style={{ color: 'var(--theme-text)' }}>Revenue Recovery Autopilot</h2>
            <p className="text-sm" style={{ color: 'var(--theme-text-muted)' }}>
              Detects at-risk revenue and recovers it for you — automatically chasing failed
              payments and winning back lapsing members.
            </p>
          </div>
        </div>
        <label className="flex items-center gap-2 cursor-pointer" data-testid="autopilot-enable-toggle">
          <span className="text-sm font-semibold" style={{ color: 'var(--theme-text)' }}>
            {s.revenue_enabled ? 'On' : 'Off'}
          </span>
          <input type="checkbox" className="sr-only peer" checked={!!s.revenue_enabled}
            onChange={(e) => saveSettings({ revenue_enabled: e.target.checked })}
            disabled={busy === 'settings'} />
          <span className="w-11 h-6 rounded-full transition-colors relative peer-checked:bg-blue-600"
            style={{ background: s.revenue_enabled ? '#2563eb' : '#cbd5e1' }}>
            <span className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform ${s.revenue_enabled ? 'translate-x-5' : ''}`} />
          </span>
        </label>
      </div>

      {/* At-risk stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Stat testId="ap-stat-revenue" label="Revenue at risk" value={gbp(ar.dunning_revenue)} sub="from failed charges" />
        <Stat testId="ap-stat-payment" label="Failed payments" value={ar.dunning_count || 0} sub="past-due members" />
        <Stat testId="ap-stat-churn" label="Churn signals" value={ar.churn_count || 0} sub="lapsing members" />
        <Stat testId="ap-stat-pending" label="Awaiting approval" value={data.pending_approvals || 0} sub="money actions" />
      </div>

      {/* Controls */}
      <div className="flex flex-wrap gap-2">
        <button onClick={() => runNow(true)} disabled={!!busy} data-testid="autopilot-preview-btn"
          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold border"
          style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}>
          {busy === 'preview' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
          Preview actions
        </button>
        <button onClick={() => runNow(false)} disabled={!!busy} data-testid="autopilot-run-btn"
          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold text-white"
          style={{ background: '#1d4ed8' }}>
          {busy === 'run' ? <Loader2 className="w-4 h-4 animate-spin" /> : <PlayCircle className="w-4 h-4" />}
          Run recovery now
        </button>
        <button onClick={load} disabled={!!busy}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold border"
          style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}>
          <RefreshCw className="w-4 h-4" /> Refresh
        </button>
      </div>

      {/* Autonomy + policy */}
      <div className="theme-card rounded-2xl p-5">
        <div className="flex items-center gap-2 mb-3">
          <Settings2 className="w-4 h-4" style={{ color: 'var(--theme-text-muted)' }} />
          <h3 className="font-semibold" style={{ color: 'var(--theme-text)' }}>How much can Autopilot do?</h3>
        </div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-2">
          {LEVELS.map((l) => {
            const active = s.autonomy_level === l.id;
            return (
              <button key={l.id} onClick={() => saveSettings({ autonomy_level: l.id })}
                disabled={busy === 'settings'} data-testid={`autopilot-level-${l.id}`}
                className="text-left rounded-xl p-3 border transition-colors"
                style={{
                  borderColor: active ? '#2563eb' : 'var(--theme-border)',
                  background: active ? 'rgba(37,99,235,0.06)' : 'transparent',
                }}>
                <div className="text-sm font-bold" style={{ color: active ? '#1d4ed8' : 'var(--theme-text)' }}>{l.label}</div>
                <div className="text-xs mt-1" style={{ color: 'var(--theme-text-muted)' }}>{l.desc}</div>
              </button>
            );
          })}
        </div>
        <label className="flex items-start gap-3 mt-4 cursor-pointer" data-testid="autopilot-money-toggle">
          <input type="checkbox" className="mt-1" checked={!!s.allow_money_actions}
            onChange={(e) => saveSettings({ allow_money_actions: e.target.checked })}
            disabled={busy === 'settings'} />
          <span>
            <span className="text-sm font-semibold flex items-center gap-1" style={{ color: 'var(--theme-text)' }}>
              <ShieldCheck className="w-4 h-4" /> Let Autopilot retry card charges automatically
            </span>
            <span className="text-xs block" style={{ color: 'var(--theme-text-muted)' }}>
              Only applies at the "Autonomous" level. When off, every card retry waits for your approval. Money never moves without this.
            </span>
          </span>
        </label>
      </div>

      {/* Pending approvals */}
      {pending.length > 0 && (
        <div className="theme-card rounded-2xl p-5" data-testid="autopilot-approvals">
          <h3 className="font-semibold mb-3 flex items-center gap-2" style={{ color: 'var(--theme-text)' }}>
            <Clock className="w-4 h-4 text-amber-600" /> Waiting for your approval
          </h3>
          <div className="space-y-2">
            {pending.map((a) => (
              <div key={a.id} className="flex flex-col sm:flex-row sm:items-center gap-2 rounded-xl border p-3"
                style={{ borderColor: 'var(--theme-border)' }} data-testid={`approval-row-${a.id}`}>
                <div className="flex-1">
                  <div className="text-sm font-semibold" style={{ color: 'var(--theme-text)' }}>
                    {a.member_name || 'Member'} · {gbp(a.amount, a.currency)}
                  </div>
                  <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{a.rationale || a.evidence}</div>
                </div>
                <div className="flex gap-2">
                  <button onClick={() => decide(a.id, true)} disabled={busy === a.id}
                    data-testid={`approve-${a.id}`}
                    className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-semibold text-white"
                    style={{ background: '#059669' }}>
                    {busy === a.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <CheckCircle2 className="w-3 h-3" />} Approve
                  </button>
                  <button onClick={() => decide(a.id, false)} disabled={busy === a.id}
                    data-testid={`reject-${a.id}`}
                    className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-semibold border"
                    style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}>
                    <XCircle className="w-3 h-3" /> Reject
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recent activity */}
      <div className="theme-card rounded-2xl p-5" data-testid="autopilot-activity">
        <h3 className="font-semibold mb-3" style={{ color: 'var(--theme-text)' }}>What Autopilot has done</h3>
        {(data.recent_actions || []).length === 0 ? (
          <p className="text-sm" style={{ color: 'var(--theme-text-muted)' }}>
            No actions yet. Turn Autopilot on, or click <strong>Run recovery now</strong> to let it work through your at-risk members.
          </p>
        ) : (
          <div className="space-y-1.5">
            {data.recent_actions.map((a) => {
              const meta = STATUS_META[a.status] || STATUS_META.suggested;
              const Icon = meta.icon;
              return (
                <div key={a.id} className="flex items-start gap-3 py-2 border-b last:border-0"
                  style={{ borderColor: 'var(--theme-border)' }}>
                  <Icon className={`w-4 h-4 mt-0.5 shrink-0 ${meta.cls}`} />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm" style={{ color: 'var(--theme-text)' }}>
                      <span className="font-semibold">{a.member_name || 'Member'}</span>
                      {' · '}{(a.kind || '').replace(/_/g, ' ')}
                    </div>
                    <div className="text-xs truncate" style={{ color: 'var(--theme-text-muted)' }}>{a.rationale || a.evidence}</div>
                  </div>
                  <span className={`text-xs font-semibold shrink-0 ${meta.cls}`}>{meta.label}</span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
