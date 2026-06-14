/**
 * Master Admin — Engineer Health board (iter 273).
 *
 * Surfaces approved partner engineers who are silently stuck so the team
 * can nudge them before they churn:
 *   • Never activated  — approved but never set up their account.
 *   • Missing workspace — activated but no org context (legacy rows).
 *   • Not subscribed    — activated but no live Engineer App access.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  Loader2, RefreshCw, MailWarning, UserX, CreditCard, CheckCircle2, Activity,
} from 'lucide-react';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL;

const BUCKETS = [
  {
    key: 'pending_link', label: 'Never activated', icon: MailWarning,
    color: '#d97706',
    blurb: 'Approved but never set up their account — resend the activation email.',
  },
  {
    key: 'org_less', label: 'Missing workspace', icon: UserX,
    color: '#dc2626',
    blurb: 'Activated but no workspace context. Auto-heals on their next sign-in.',
  },
  {
    key: 'not_subscribed', label: 'Not subscribed', icon: CreditCard,
    color: '#7c3aed',
    blurb: "Activated but can't take jobs yet — no active trial/subscription.",
  },
];

const CCY = { GB: '£', US: '$', IE: '€', CA: 'C$', AU: 'A$' };

export default function AdminEngineerHealth() {
  const token = useMemo(() => localStorage.getItem('token'), []);
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [active, setActive] = useState('pending_link');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/api/master-admin/partners/health`, { headers });
      setData(r.data);
    } catch (e) {
      notify.error('Failed to load engineer health', e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  const summary = data?.summary || {};
  const rows = data?.[active] || [];

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center py-24 text-zinc-500" data-testid="engineer-health-loading">
        <Loader2 className="animate-spin mr-2" size={18} /> Loading engineer health…
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="admin-engineer-health">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-black flex items-center gap-2">
            <Activity size={18} className="text-purple-600" /> Engineer Health
          </h2>
          <p className="text-sm text-zinc-500 mt-0.5">
            Approved engineers who are stuck — catch onboarding drop-offs early.
          </p>
        </div>
        <button
          onClick={load}
          className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-semibold rounded-md border border-zinc-300 hover:bg-zinc-50"
          data-testid="engineer-health-refresh"
        >
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3" data-testid="engineer-health-summary">
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4">
          <div className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wide text-emerald-700">
            <CheckCircle2 size={13} /> Healthy
          </div>
          <div className="text-3xl font-black text-emerald-700 mt-1" data-testid="health-count-healthy">
            {summary.healthy ?? 0}
          </div>
          <div className="text-[11px] text-emerald-600/80 mt-0.5">of {summary.total_approved ?? 0} approved</div>
        </div>
        {BUCKETS.map((b) => {
          const Icon = b.icon;
          return (
            <button
              key={b.key}
              onClick={() => setActive(b.key)}
              className={`text-left rounded-xl border p-4 transition ${active === b.key ? 'ring-2 ring-offset-1' : ''}`}
              style={{
                borderColor: `${b.color}40`, background: `${b.color}10`,
                ...(active === b.key ? { '--tw-ring-color': b.color } : {}),
              }}
              data-testid={`health-card-${b.key}`}
            >
              <div className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wide" style={{ color: b.color }}>
                <Icon size={13} /> {b.label}
              </div>
              <div className="text-3xl font-black mt-1" style={{ color: b.color }} data-testid={`health-count-${b.key}`}>
                {summary[b.key] ?? 0}
              </div>
              <div className="text-[11px] mt-0.5" style={{ color: `${b.color}cc` }}>{b.blurb}</div>
            </button>
          );
        })}
      </div>

      {/* Detail table for the active bucket */}
      <div className="rounded-xl border border-zinc-200 overflow-hidden">
        <div className="px-4 py-3 border-b border-zinc-200 bg-zinc-50 text-sm font-bold">
          {BUCKETS.find((b) => b.key === active)?.label} — {rows.length} shown
          {summary[active] > rows.length ? ` (of ${summary[active]})` : ''}
        </div>
        {rows.length === 0 ? (
          <div className="px-4 py-10 text-center text-sm text-zinc-500" data-testid="engineer-health-empty">
            Nothing here — all clear in this category. 🎉
          </div>
        ) : (
          <div className="divide-y divide-zinc-100" data-testid="engineer-health-rows">
            {rows.map((r) => (
              <div key={r.id} className="px-4 py-3 flex items-center justify-between gap-3 hover:bg-zinc-50" data-testid={`health-row-${r.id}`}>
                <div className="min-w-0">
                  <div className="font-semibold truncate">{r.full_name}</div>
                  <div className="text-xs text-zinc-500 truncate">{r.email}</div>
                </div>
                <div className="flex items-center gap-4 shrink-0 text-xs">
                  <span className="px-2 py-0.5 rounded-full bg-zinc-100 font-semibold">
                    {CCY[r.country_code] || ''}{r.country_code}
                  </span>
                  {active === 'not_subscribed' && (
                    <span className="text-zinc-500">
                      {r.subscription_status ? `sub: ${r.subscription_status}` : 'no subscription'}
                    </span>
                  )}
                  {r.created_at && (
                    <span className="text-zinc-400 hidden sm:inline">
                      {new Date(r.created_at).toLocaleDateString()}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
