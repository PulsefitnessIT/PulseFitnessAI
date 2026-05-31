/**
 * Iter 220e3 — Contract Reports + Renewals dashboard (Phases E + F).
 *
 * Both surfaces are read-only summaries that consume the lifecycle
 * routes. Designed to slot into the existing CRM → Contracts area
 * without adding new navigation: rendered as inline tabs above the
 * contract list (operator toggles between "Contracts", "Renewals"
 * and "Reports").
 */
import { useEffect, useState } from 'react';
import axios from 'axios';
import {
  BarChart3, RefreshCw, AlertTriangle, DollarSign,
  Shield, Calendar, TrendingUp, Zap,
} from 'lucide-react';

const fmtMoney = v => `£${Math.round(v || 0).toLocaleString('en-GB')}`;

function MetricCard({ label, value, hint, color, icon: Icon, c, isDark, testId }) {
  return (
    <div className="p-4 rounded-xl border" data-testid={testId}
         style={{ background: isDark ? '#111' : 'var(--color-neutral-50)',
                  borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
      <div className="flex items-center justify-between mb-1.5">
        <Icon size={14} style={{ color }} />
        {hint && <span className="text-[10px] uppercase tracking-wider" style={{ color: c.textDim }}>{hint}</span>}
      </div>
      <p className="text-xl font-extrabold tracking-tight" style={{ color: c.text }}>{value}</p>
      <p className="text-[10px] uppercase tracking-wider" style={{ color: c.textDim }}>{label}</p>
    </div>
  );
}
MetricCard.displayName = 'MetricCard';

export function ContractsReportsDashboard({ API, headers, c, isDark }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let alive = true;
    axios.get(`${API}/crm/v2/contracts/reports/dashboard`, { headers: headers() })
      .then(r => { if (alive) setData(r.data); })
      .catch(() => alive && setData({}))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [API, headers]);
  if (loading) return <div className="flex justify-center py-12"><div className="w-5 h-5 border-2 border-[var(--color-info-ios)] border-t-transparent rounded-full animate-spin" /></div>;
  if (!data) return null;
  return (
    <div data-testid="contracts-reports">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <MetricCard label="ARR"        value={fmtMoney(data.arr)}              icon={DollarSign} color="var(--color-success-alt)" c={c} isDark={isDark} testId="report-arr" />
        <MetricCard label="MRR"        value={fmtMoney(data.mrr)}              icon={TrendingUp} color="var(--color-info-ios)"    c={c} isDark={isDark} testId="report-mrr" />
        <MetricCard label="At risk 30d" value={fmtMoney(data.expiring_30d_value)} hint="≤30d" icon={AlertTriangle} color="var(--color-danger)"    c={c} isDark={isDark} testId="report-at-risk-30" />
        <MetricCard label="At risk 90d" value={fmtMoney(data.expiring_90d_value)} hint="≤90d" icon={AlertTriangle} color="var(--color-accent-amber)" c={c} isDark={isDark} testId="report-at-risk-90" />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
        <div className="p-4 rounded-xl border" style={{ background: isDark ? '#111' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
          <p className="text-xs font-bold uppercase tracking-wider mb-2" style={{ color: c.textDim }}>By tier</p>
          {(data.by_tier || []).map(t => (
            <div key={t.tier} className="flex items-center gap-2 text-xs py-1">
              <Shield size={12} style={{ color: 'var(--color-info-ios)' }} />
              <span className="capitalize flex-1" style={{ color: c.text }}>{t.tier || 'unset'}</span>
              <span className="font-semibold" style={{ color: c.textDim }}>{t.count} · {fmtMoney(t.annual_value)}/yr</span>
            </div>
          ))}
          {(!data.by_tier || data.by_tier.length === 0) && (
            <p className="text-center text-[11px] py-4" style={{ color: c.textDim }}>No active contracts yet.</p>
          )}
        </div>
        <div className="p-4 rounded-xl border" style={{ background: isDark ? '#111' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
          <p className="text-xs font-bold uppercase tracking-wider mb-2" style={{ color: c.textDim }}>Coverage gap</p>
          <div className="flex items-center gap-3 text-xs">
            <div data-testid="coverage-covered">
              <p className="text-2xl font-extrabold" style={{ color: 'var(--color-success-alt)' }}>{data.coverage?.assets_covered || 0}</p>
              <p className="text-[10px] uppercase" style={{ color: c.textDim }}>Covered assets</p>
            </div>
            <div data-testid="coverage-uncovered">
              <p className="text-2xl font-extrabold" style={{ color: 'var(--color-accent-amber)' }}>{data.coverage?.assets_uncovered || 0}</p>
              <p className="text-[10px] uppercase" style={{ color: c.textDim }}>Uncovered assets — potential upsell</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function ContractsRenewalsDashboard({ API, headers, c, isDark, onOpen }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [auto, setAuto] = useState(false);

  const reload = () => {
    setLoading(true);
    return axios.get(`${API}/crm/v2/contracts/renewals/pipeline`, { headers: headers() })
      .then(r => setData(r.data))
      .catch(() => setData({ buckets: { '30': [], '60': [], '90': [] }, totals: {} }))
      .finally(() => setLoading(false));
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { reload();   }, []);

  const runReminders = async () => {
    setRunning(true);
    try {
      const res = await axios.post(`${API}/crm/v2/contracts/renewals/run-reminders`, {}, { headers: headers() });
      alert(`${res.data.reminders_created} reminder(s) created.`);
    } catch (e) { alert(e?.response?.data?.detail || 'Failed'); }
    setRunning(false);
  };

  const autoSend = async () => {
    if (!window.confirm('Auto-send renewal drafts to every customer whose contract has auto_renew enabled and is within the 30-day window? Customers still need to click Accept & sign — nothing activates automatically.')) return;
    setAuto(true);
    try {
      const res = await axios.post(`${API}/crm/v2/contracts/renewals/auto-send`, {}, { headers: headers() });
      const d = res.data.totals?.dispatched || 0;
      const s = res.data.totals?.skipped || 0;
      alert(`Auto-renewals dispatched: ${d}. Skipped: ${s}.`);
      reload();
    } catch (e) { alert(e?.response?.data?.detail || 'Failed'); }
    setAuto(false);
  };

  if (loading) return <div className="flex justify-center py-12"><div className="w-5 h-5 border-2 border-[var(--color-info-ios)] border-t-transparent rounded-full animate-spin" /></div>;
  const buckets = data?.buckets || { '30': [], '60': [], '90': [] };
  return (
    <div data-testid="contracts-renewals">
      <div className="flex items-center justify-between mb-3">
        <div>
          <p className="text-sm font-semibold" style={{ color: c.text }}>Renewal pipeline</p>
          <p className="text-[11px]" style={{ color: c.textDim }}>
            {(data?.totals?.contracts || 0)} contract(s) — {fmtMoney(data?.totals?.annual_value_at_risk)}/yr at risk
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={runReminders} disabled={running} data-testid="run-renewal-reminders-btn"
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md bg-[var(--color-warning)] text-white">
            {running ? <RefreshCw size={12} className="animate-spin" /> : <Calendar size={12} />} Run reminders now
          </button>
          <button onClick={autoSend} disabled={auto} data-testid="auto-renewal-autopilot-btn"
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md bg-emerald-600 text-white">
            {auto ? <RefreshCw size={12} className="animate-spin" /> : <Zap size={12} />} Auto-renewal autopilot
          </button>
        </div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {[
          { key: '30', label: '≤30 days', tone: 'var(--color-danger)' },
          { key: '60', label: '31-60 days', tone: 'var(--color-accent-amber)' },
          { key: '90', label: '61-90 days', tone: 'var(--color-info-ios)' },
        ].map(b => (
          <div key={b.key} className="p-3 rounded-xl border" data-testid={`renewal-bucket-${b.key}`}
               style={{ background: isDark ? '#111' : '#fff',
                        borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs font-bold uppercase tracking-wider" style={{ color: b.tone }}>{b.label}</p>
              <span className="text-[11px] font-semibold" style={{ color: c.text }}>{buckets[b.key].length}</span>
            </div>
            <div className="space-y-1.5 max-h-[40vh] overflow-y-auto">
              {buckets[b.key].map(item => (
                <button key={item.id} onClick={() => onOpen?.(item.id)}
                        data-testid={`renewal-card-${item.id}`}
                        className="w-full text-left p-2 rounded border hover:bg-blue-500/5"
                        style={{ borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
                  <div className="flex items-center gap-2 mb-0.5">
                    <Shield size={11} style={{ color: 'var(--color-info-ios)' }} />
                    <span className="text-xs font-semibold flex-1 truncate" style={{ color: c.text }}>{item.title || item.contract_number}</span>
                    <span className="text-[10px] font-bold" style={{ color: b.tone }}>{item.days_remaining}d</span>
                  </div>
                  <p className="text-[10px]" style={{ color: c.textDim }}>{item.company_name || '—'}</p>
                  <p className="text-[10px] mt-1" style={{ color: c.textDim }}>
                    Current {fmtMoney(item.annual_value)}/yr →{' '}
                    <span style={{ color: 'var(--color-success-alt)', fontWeight: 700 }}>
                      {fmtMoney(item.suggested_renewal_value)} (+{item.suggested_uplift_percent}%)
                    </span>
                  </p>
                </button>
              ))}
              {buckets[b.key].length === 0 && (
                <p className="text-center text-[10px] py-4" style={{ color: c.textDim }}>Nothing in this window.</p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

ContractsReportsDashboard.displayName = 'ContractsReportsDashboard';
ContractsRenewalsDashboard.displayName = 'ContractsRenewalsDashboard';
export const Icons = { BarChart3, Calendar };
