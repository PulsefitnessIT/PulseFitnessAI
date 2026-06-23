/**
 * Pulse Fitness AI — Comms intelligence views (Phase 2).
 * Engagement scoring, inactive detection, best-send-time, benchmarking and
 * the Deliverability Centre. All themed with platform tokens.
 */
import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import {
  TrendingUp, Clock, Award, ShieldCheck, AlertTriangle, CheckCircle2, Users, Building2, Flame,
} from 'lucide-react';

const apiRoot = (API) => (API || process.env.REACT_APP_BACKEND_URL || '').replace(/\/api\/?$/, '');

const BAND_STYLE = {
  highly_engaged: 'bg-emerald-500/15 text-emerald-600',
  engaged: 'bg-cyan-500/15 text-cyan-700',
  neutral: 'bg-slate-500/15 text-slate-500',
  disengaged: 'bg-amber-500/15 text-amber-600',
  inactive: 'bg-rose-500/15 text-rose-600',
};
const BAND_LABEL = {
  highly_engaged: 'Highly engaged', engaged: 'Engaged', neutral: 'Neutral',
  disengaged: 'Disengaged', inactive: 'Inactive',
};

const card = { background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' };
const muted = { color: 'var(--theme-text-muted)' };
const txt = { color: 'var(--theme-text)' };

function Empty({ icon: Icon, msg }) {
  return (
    <div className="rounded-2xl border p-12 text-center" style={card}>
      <Icon size={28} className="mx-auto mb-2" style={muted} />
      <p className="text-sm" style={muted}>{msg}</p>
    </div>
  );
}

function ScoreBar({ score }) {
  return (
    <div className="w-24 h-2 rounded-full overflow-hidden" style={{ background: 'var(--theme-border)' }}>
      <div className="h-full rounded-full" style={{ width: `${score}%`, background: 'var(--color-brand-cyan)' }} />
    </div>
  );
}

export function EngagementView({ API, headers, module }) {
  const [data, setData] = useState(null);
  const [tab, setTab] = useState('contacts');
  const load = useCallback(async () => {
    try {
      const url = tab === 'contacts'
        ? `${apiRoot(API)}/api/comms/engagement/contacts?module=${module}`
        : `${apiRoot(API)}/api/comms/engagement/companies`;
      const r = await axios.get(url, { headers });
      setData(r.data);
    } catch { toast.error('Failed to load engagement'); }
  }, [API, headers, module, tab]);
  useEffect(() => { load(); }, [load]);

  return (
    <div data-testid="engagement-view">
      <div className="flex gap-2 mb-4">
        {['contacts', 'companies'].map((x) => (
          <button key={x} onClick={() => { setData(null); setTab(x); }} className="px-3 py-1.5 rounded-full text-xs font-bold capitalize" style={tab === x ? { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' } : { color: 'var(--theme-text-muted)', border: '1px solid var(--theme-border)' }} data-testid={`engagement-tab-${x}`}>{x}</button>
        ))}
      </div>
      {!data ? <Empty icon={Flame} msg="Loading…" />
        : tab === 'contacts' ? (
          (data.contacts || []).length === 0 ? <Empty icon={Users} msg="No engagement data yet — it appears once campaigns are sent." /> : (
            <div className="rounded-2xl border overflow-hidden" style={card}>
              <table className="w-full text-sm">
                <thead style={{ background: 'var(--theme-bg)', ...muted }} className="text-xs uppercase tracking-wide">
                  <tr><th className="text-left font-bold px-4 py-3">Contact</th><th className="text-left px-4 py-3 hidden sm:table-cell">Opens</th><th className="text-left px-4 py-3 hidden sm:table-cell">Clicks</th><th className="text-left px-4 py-3">Score</th><th className="text-left px-4 py-3">Band</th></tr>
                </thead>
                <tbody>
                  {data.contacts.map((c) => (
                    <tr key={c.email} className="border-t" style={{ borderColor: 'var(--theme-border)' }}>
                      <td className="px-4 py-3 font-semibold" style={txt}>{c.email}</td>
                      <td className="px-4 py-3 hidden sm:table-cell" style={muted}>{c.opened}</td>
                      <td className="px-4 py-3 hidden sm:table-cell" style={muted}>{c.clicked}</td>
                      <td className="px-4 py-3"><div className="flex items-center gap-2"><ScoreBar score={c.score} /><span className="font-bold" style={txt}>{c.score}</span></div></td>
                      <td className="px-4 py-3"><span className={`text-[11px] font-bold px-2 py-1 rounded-full ${BAND_STYLE[c.band]}`}>{BAND_LABEL[c.band]}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        ) : (
          (data.companies || []).length === 0 ? <Empty icon={Building2} msg="No company engagement yet — link CRM contacts to companies and send campaigns." /> : (
            <div className="rounded-2xl border overflow-hidden" style={card}>
              <table className="w-full text-sm">
                <thead style={{ background: 'var(--theme-bg)', ...muted }} className="text-xs uppercase tracking-wide">
                  <tr><th className="text-left font-bold px-4 py-3">Company</th><th className="text-left px-4 py-3 hidden sm:table-cell">Contacts</th><th className="text-left px-4 py-3">Score</th><th className="text-left px-4 py-3">Band</th></tr>
                </thead>
                <tbody>
                  {data.companies.map((c) => (
                    <tr key={c.company_id} className="border-t" style={{ borderColor: 'var(--theme-border)' }}>
                      <td className="px-4 py-3 font-semibold" style={txt}>{c.company_name}</td>
                      <td className="px-4 py-3 hidden sm:table-cell" style={muted}>{c.engaged_contacts}</td>
                      <td className="px-4 py-3"><div className="flex items-center gap-2"><ScoreBar score={c.score} /><span className="font-bold" style={txt}>{c.score}</span></div></td>
                      <td className="px-4 py-3"><span className={`text-[11px] font-bold px-2 py-1 rounded-full ${BAND_STYLE[c.band]}`}>{BAND_LABEL[c.band]}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        )}
    </div>
  );
}

export function InactiveView({ API, headers, module }) {
  const [days, setDays] = useState(60);
  const [data, setData] = useState(null);
  const load = useCallback(async () => {
    try { const r = await axios.get(`${apiRoot(API)}/api/comms/insights/inactive?days=${days}&module=${module}`, { headers }); setData(r.data); }
    catch { toast.error('Failed to load inactive list'); }
  }, [API, headers, module, days]);
  useEffect(() => { load(); }, [load]);
  return (
    <div data-testid="inactive-view">
      <div className="flex items-center gap-2 mb-4">
        <span className="text-sm font-semibold" style={muted}>No opens in the last</span>
        <select value={days} onChange={(e) => setDays(Number(e.target.value))} className="px-3 py-1.5 rounded-full text-sm border" style={{ ...card, ...txt }} data-testid="inactive-days">
          {[30, 60, 90, 180].map((d) => <option key={d} value={d}>{d} days</option>)}
        </select>
      </div>
      {!data ? <Empty icon={Clock} msg="Loading…" />
        : (data.inactive || []).length === 0 ? <Empty icon={CheckCircle2} msg="No inactive contacts found for this window. 🎉" />
          : (
            <div className="rounded-2xl border overflow-hidden" style={card}>
              <div className="px-4 py-3 text-sm font-bold" style={{ background: 'var(--theme-bg)', ...txt }}>{data.count} contacts haven't opened in {days}+ days</div>
              <table className="w-full text-sm">
                <tbody>
                  {data.inactive.map((c) => (
                    <tr key={c.email} className="border-t" style={{ borderColor: 'var(--theme-border)' }}>
                      <td className="px-4 py-3 font-semibold" style={txt}>{c.email}</td>
                      <td className="px-4 py-3 text-right" style={muted}>{c.days_since_open == null ? 'Never opened' : `${c.days_since_open} days ago`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
    </div>
  );
}

export function BestTimeView({ API, headers, module }) {
  const [data, setData] = useState(null);
  useEffect(() => {
    axios.get(`${apiRoot(API)}/api/comms/insights/best-send-time?module=${module}`, { headers })
      .then((r) => setData(r.data)).catch(() => toast.error('Failed to load best send time'));
  }, [API, headers, module]);
  if (!data) return <Empty icon={Clock} msg="Loading…" />;
  const max = Math.max(1, ...data.grid.flat());
  return (
    <div data-testid="best-time-view">
      <div className="rounded-2xl border p-5 mb-4" style={card}>
        <div className="flex items-center gap-2 mb-1" style={muted}><Clock size={16} /><span className="text-xs font-bold uppercase tracking-wide">Recommended send time</span></div>
        <p className="text-2xl font-extrabold pulse-font-heading" style={txt}>{data.recommendation.label}</p>
        {!data.enough_data && <p className="text-xs mt-1" style={muted}>{data.note}</p>}
      </div>
      <div className="rounded-2xl border p-4 overflow-x-auto" style={card}>
        <p className="text-xs font-bold uppercase tracking-wide mb-3" style={muted}>Opens heat-map (day × hour)</p>
        <div className="inline-block">
          {data.grid.map((row, d) => (
            <div key={d} className="flex items-center gap-1 mb-1">
              <span className="text-[10px] w-8" style={muted}>{data.days[d]}</span>
              {row.map((v, h) => (
                <div key={h} title={`${data.days[d]} ${h}:00 — ${v} opens`} className="w-3.5 h-3.5 rounded-sm" style={{ background: v ? `rgba(25,205,255,${0.15 + 0.85 * (v / max)})` : 'var(--theme-border)' }} />
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function BenchmarksView({ API, headers, module }) {
  const [data, setData] = useState(null);
  useEffect(() => {
    axios.get(`${apiRoot(API)}/api/comms/insights/benchmarks?module=${module}`, { headers })
      .then((r) => setData(r.data)).catch(() => toast.error('Failed to load benchmarks'));
  }, [API, headers, module]);
  if (!data) return <Empty icon={Award} msg="Loading…" />;
  if (!data.count) return <Empty icon={Award} msg="No sent campaigns yet — benchmarks appear after your first send." />;
  return (
    <div data-testid="benchmarks-view">
      <div className="grid grid-cols-3 gap-3 mb-4">
        {[['Avg open rate', data.averages.open_rate, '%'], ['Avg click rate', data.averages.click_rate, '%'], ['Avg unsub rate', data.averages.unsub_rate, '%']].map(([l, v, s]) => (
          <div key={l} className="rounded-2xl border p-4" style={card}><p className="text-xs font-bold uppercase tracking-wide" style={muted}>{l}</p><p className="text-2xl font-extrabold pulse-font-heading" style={txt}>{v}{s}</p></div>
        ))}
      </div>
      <div className="rounded-2xl border overflow-hidden" style={card}>
        <table className="w-full text-sm">
          <thead style={{ background: 'var(--theme-bg)', ...muted }} className="text-xs uppercase tracking-wide">
            <tr><th className="text-left font-bold px-4 py-3">Campaign</th><th className="text-left px-4 py-3">Open %</th><th className="text-left px-4 py-3">Click %</th><th className="text-left px-4 py-3 hidden sm:table-cell">Sent</th></tr>
          </thead>
          <tbody>
            {data.campaigns.map((c) => (
              <tr key={c.id} className="border-t" style={{ borderColor: 'var(--theme-border)' }}>
                <td className="px-4 py-3 font-semibold" style={txt}>{c.name}</td>
                <td className="px-4 py-3"><span style={{ color: c.open_rate >= data.averages.open_rate ? 'var(--color-brand-cyan)' : 'var(--theme-text-muted)' }} className="font-bold">{c.open_rate}%</span></td>
                <td className="px-4 py-3" style={muted}>{c.click_rate}%</td>
                <td className="px-4 py-3 hidden sm:table-cell" style={muted}>{c.sent}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function DeliverabilityView({ API, headers }) {
  const [data, setData] = useState(null);
  useEffect(() => {
    axios.get(`${apiRoot(API)}/api/comms/deliverability`, { headers })
      .then((r) => setData(r.data)).catch(() => toast.error('Failed to load deliverability'));
  }, [API, headers]);
  if (!data) return <Empty icon={ShieldCheck} msg="Loading…" />;
  const healthStyle = { good: 'bg-emerald-500/15 text-emerald-600', warning: 'bg-amber-500/15 text-amber-600', at_risk: 'bg-rose-500/15 text-rose-600' }[data.health];
  return (
    <div data-testid="deliverability-view">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
        <div className="rounded-2xl border p-4" style={card}><p className="text-xs font-bold uppercase tracking-wide" style={muted}>Health</p><span className={`inline-block mt-1 text-sm font-bold px-2.5 py-1 rounded-full ${healthStyle}`}>{data.health.replace('_', ' ')}</span></div>
        <div className="rounded-2xl border p-4" style={card}><p className="text-xs font-bold uppercase tracking-wide" style={muted}>Bounce rate</p><p className="text-2xl font-extrabold pulse-font-heading" style={txt}>{data.rates.bounce_rate}%</p></div>
        <div className="rounded-2xl border p-4" style={card}><p className="text-xs font-bold uppercase tracking-wide" style={muted}>Unsub rate</p><p className="text-2xl font-extrabold pulse-font-heading" style={txt}>{data.rates.unsubscribe_rate}%</p></div>
        <div className="rounded-2xl border p-4" style={card}><p className="text-xs font-bold uppercase tracking-wide" style={muted}>Suppressed</p><p className="text-2xl font-extrabold pulse-font-heading" style={txt}>{data.suppression_count}</p></div>
      </div>
      {data.warnings.length > 0 && (
        <div className="mb-4 space-y-2" data-testid="deliverability-warnings">
          {data.warnings.map((w, i) => (
            <div key={i} className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm ${w.level === 'error' ? 'bg-rose-500/12 text-rose-600' : 'bg-amber-500/12 text-amber-700'}`}><AlertTriangle size={15} />{w.message}</div>
          ))}
        </div>
      )}
      <div className="rounded-2xl border overflow-hidden" style={card}>
        <div className="px-4 py-3 text-sm font-bold" style={{ background: 'var(--theme-bg)', ...txt }}>Verified sending domains · {data.provider}</div>
        <table className="w-full text-sm">
          <thead style={{ ...muted }} className="text-xs uppercase tracking-wide">
            <tr><th className="text-left font-bold px-4 py-2">Domain</th><th className="text-left px-4 py-2">SPF</th><th className="text-left px-4 py-2">DKIM</th><th className="text-left px-4 py-2">DMARC</th><th className="text-left px-4 py-2">Status</th></tr>
          </thead>
          <tbody>
            {data.domains.map((d) => (
              <tr key={d.domain} className="border-t" style={{ borderColor: 'var(--theme-border)' }}>
                <td className="px-4 py-3 font-semibold" style={txt}>{d.domain}</td>
                {['spf', 'dkim', 'dmarc'].map((k) => <td key={k} className="px-4 py-3"><CheckCircle2 size={15} className="text-emerald-500" /></td>)}
                <td className="px-4 py-3"><span className={`text-[11px] font-bold px-2 py-1 rounded-full ${d.verified ? 'bg-emerald-500/15 text-emerald-600' : 'bg-rose-500/15 text-rose-600'}`}>{d.verified ? 'Verified' : 'Unverified'}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
