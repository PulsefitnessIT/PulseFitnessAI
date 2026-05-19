/**
 * Estate Modules Rollup — Iter 216av · Phase 3 #8.
 *
 * Read-only finance panel. Surfaces every paying org's module
 * entitlement so HQ-tier finance operators can:
 *   • Audit license usage across the estate
 *   • See which modules are paid vs trial vs orphan
 *   • Catch trials expiring within 7 days
 *   • Spot orgs with NO modules enabled (billing red flag)
 */
import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import {
  BarChart3, Loader2, AlertTriangle, Clock, Building2, Activity,
  Calendar, Briefcase, Rocket,
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

const MODULE_META = {
  operations:  { label: 'Operations',  icon: Activity,  accent: '#0EA5E9' },
  memberships: { label: 'Memberships', icon: Calendar,  accent: '#10B981' },
  marketing:   { label: 'Marketing',   icon: Rocket,    accent: '#F43F5E' },
  crm:         { label: 'CRM',         icon: Briefcase, accent: '#8B5CF6' },
};

export default function EstateRollupPanel() {
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    setLoading(true); setErr('');
    try {
      const r = await axios.get(
        `${API}/api/master-admin/estate/modules-rollup`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      setData(r.data);
    } catch (e) {
      setErr(e.response?.data?.detail || e.message || 'Failed to load');
    }
    setLoading(false);
  }, [token]);
  useEffect(() => { load(); }, [load]);

  if (loading) return <div className="p-8 text-center" data-testid="estate-rollup-loading"><Loader2 size={24} className="animate-spin inline" /></div>;
  if (err)     return <div className="p-8 text-center text-rose-500 text-sm" data-testid="estate-rollup-error">{err}</div>;
  if (!data)   return null;

  return (
    <div className="space-y-6" data-testid="estate-rollup">
      <div className="flex items-center gap-2 text-zinc-700 dark:text-zinc-300">
        <BarChart3 size={16} />
        <span className="text-sm">{data.total_orgs} organisations · as of {new Date(data.as_of).toLocaleString()}</span>
      </div>

      {/* By module */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
        {Object.entries(data.by_module).map(([key, stats]) => {
          const meta = MODULE_META[key] || { label: key, icon: BarChart3, accent: '#64748B' };
          const Icon = meta.icon;
          return (
            <div key={key} className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-4" data-testid={`estate-module-${key}`}>
              <div className="flex items-center gap-2 mb-3">
                <div className="w-9 h-9 rounded-lg flex items-center justify-center text-white" style={{ background: meta.accent }}>
                  <Icon size={16} />
                </div>
                <div>
                  <p className="text-sm font-bold text-zinc-900 dark:text-zinc-100 pulse-font-heading">{meta.label}</p>
                  <p className="text-[10px] uppercase tracking-wider font-bold text-zinc-500">{stats.enabled} of {data.total_orgs} orgs</p>
                </div>
              </div>
              <div className="grid grid-cols-3 gap-1.5 text-center">
                <Mini label="Paid"          value={stats.paid} />
                <Mini label="Trial active"  value={stats.trial_active} accent="#F59E0B" />
                <Mini label="Expiring 7d"   value={stats.trial_expiring_7d} accent={stats.trial_expiring_7d > 0 ? '#EF4444' : undefined} />
              </div>
            </div>
          );
        })}
      </div>

      {/* By tier */}
      <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-4">
        <p className="text-sm font-bold text-zinc-900 dark:text-zinc-100 mb-3 inline-flex items-center gap-2">
          <Building2 size={14} /> By account tier
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-zinc-500 dark:text-zinc-400 border-b border-zinc-200 dark:border-zinc-800">
                <th className="py-2 font-bold uppercase tracking-wider">Tier</th>
                <th className="py-2 font-bold uppercase tracking-wider text-right">Orgs</th>
                {Object.keys(MODULE_META).map((k) => (
                  <th key={k} className="py-2 font-bold uppercase tracking-wider text-right">{MODULE_META[k].label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Object.entries(data.by_tier).map(([tier, t]) => (
                <tr key={tier} className="border-b border-zinc-100 dark:border-zinc-800/50" data-testid={`estate-tier-${tier}`}>
                  <td className="py-2 font-bold text-zinc-900 dark:text-zinc-100">{tier}</td>
                  <td className="py-2 text-right tabular-nums">{t.count}</td>
                  {Object.keys(MODULE_META).map((k) => (
                    <td key={k} className="py-2 text-right tabular-nums">{t.modules?.[k] || 0}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Trials expiring */}
      <div className="rounded-xl border border-amber-200 dark:border-amber-800/50 bg-amber-50 dark:bg-amber-950/20 p-4">
        <p className="text-sm font-bold text-amber-900 dark:text-amber-200 mb-3 inline-flex items-center gap-2">
          <Clock size={14} /> Trials expiring in 7 days ({data.trials_expiring_7d.length})
        </p>
        {data.trials_expiring_7d.length === 0 ? (
          <p className="text-xs text-amber-800 dark:text-amber-300">No trials expiring soon.</p>
        ) : (
          <ul className="space-y-1.5">
            {data.trials_expiring_7d.map((t, i) => (
              <li key={i} className="flex items-center gap-3 text-xs" data-testid={`estate-trial-expiring-${i}`}>
                <span className="font-bold text-zinc-900 dark:text-zinc-100">{t.organization_name}</span>
                <span className="text-amber-700 dark:text-amber-300 uppercase tracking-wider font-bold text-[10px]">{t.module}</span>
                <span className="ml-auto text-zinc-600 dark:text-zinc-400">{new Date(t.expires_at).toLocaleString()}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Orphans */}
      {data.orphans_count > 0 && (
        <div className="rounded-xl border border-rose-200 dark:border-rose-800/50 bg-rose-50 dark:bg-rose-950/20 p-4" data-testid="estate-orphans">
          <p className="text-sm font-bold text-rose-900 dark:text-rose-200 mb-3 inline-flex items-center gap-2">
            <AlertTriangle size={14} /> Orphan orgs — no modules enabled ({data.orphans_count})
          </p>
          <ul className="space-y-1.5">
            {data.orphans.map((o) => (
              <li key={o.organization_id} className="flex items-center gap-3 text-xs">
                <span className="font-bold text-zinc-900 dark:text-zinc-100">{o.organization_name || o.organization_id.slice(0, 8)}</span>
                <span className="text-rose-700 dark:text-rose-300 uppercase tracking-wider font-bold text-[10px]">{o.account_type || '—'}</span>
                {o.subscription_status && <span className="ml-auto text-zinc-600 dark:text-zinc-400">{o.subscription_status}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function Mini({ label, value, accent }) {
  return (
    <div className="text-center">
      <p className="text-lg font-bold tabular-nums" style={{ color: accent || 'var(--theme-text)' }}>{value}</p>
      <p className="text-[9px] uppercase tracking-wider font-bold text-zinc-500">{label}</p>
    </div>
  );
}
