import { useEffect, useState } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import {
  Building2, Users, AlertTriangle, Ban, PoundSterling,
  Wrench, CheckCircle, RefreshCw,
} from 'lucide-react';

/**
 * Master Admin → Operations Portal → Overview (Iter 220o).
 *
 * Operations-SCOPED dashboard. The previous default Overview rendered
 * the platform-wide AdminOverview (all-module orgs/users/revenue + a
 * cross-module Trial Pipeline) under the "Operations Portal" pill,
 * which was misleading. That combined view now lives on the dedicated
 * "Platform" pill; this surface shows ONLY operations-module data.
 *
 * Stats come from `GET /master-admin/stats?module=operations`, which
 * narrows every count to orgs that have the Operations module enabled.
 * No Trial Pipeline here (trials live on the Platform tab).
 *
 * Same white-Panel / slate visual system as AdminOverview.
 */
const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const KPI_PALETTES = {
  organisations: { fg: '#2563EB', bg: 'rgba(37,99,235,0.08)' },
  users:         { fg: '#5B5BF5', bg: 'rgba(91,91,245,0.08)' },
  revenue:       { fg: '#059669', bg: 'rgba(5,150,105,0.10)' },
  cases:         { fg: '#D97706', bg: 'rgba(217,119,6,0.10)' },
};

const Panel = ({ children, className = '', ...rest }) => (
  <div
    className={`bg-white border border-slate-200 rounded-2xl shadow-[0_1px_2px_rgba(15,23,42,0.04)] ${className}`}
    {...rest}
  >
    {children}
  </div>
);

const OperationsOverview = ({ token, onGoPayments, onGoSuspended }) => {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    axios.get(`${API}/master-admin/stats`, {
      params: { module: 'operations' },
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => { if (!cancelled) setStats(r.data); })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [token]);

  if (loading || !stats) {
    return (
      <div className="flex items-center justify-center h-64" data-testid="ops-overview-loading">
        <RefreshCw className="animate-spin text-slate-400" size={24} />
      </div>
    );
  }

  const kpiCards = [
    { label: 'Operations Orgs', value: stats.total_organizations, icon: Building2, palette: KPI_PALETTES.organisations, testid: 'ops-kpi-organisations',
      tip: 'Organisations with the Operations module enabled (every non-MOD org, unless Operations is explicitly switched off).' },
    { label: 'Active Users', value: stats.total_users, icon: Users, palette: KPI_PALETTES.users, testid: 'ops-kpi-active-users',
      tip: 'User accounts inside Operations-enabled organisations.' },
    { label: 'Operations MRR', value: `£${(stats.mrr || 0).toLocaleString()}`, icon: PoundSterling, palette: KPI_PALETTES.revenue, testid: 'ops-kpi-mrr',
      tip: 'Monthly Recurring Revenue from active paid plans on Operations-enabled organisations.' },
    { label: 'Open Cases', value: stats.open_issues, icon: AlertTriangle, palette: KPI_PALETTES.cases, testid: 'ops-kpi-open-cases',
      tip: 'Faults across Operations gyms with status = open. Resolved or closed faults are excluded.' },
  ];

  const secondaryStats = [
    { label: 'Equipment Tracked', value: stats.total_equipment, icon: Wrench, color: '#0EA5E9', testid: 'ops-stat-equip-tracked',
      tip: 'Every equipment record across Operations gyms, regardless of status.' },
    { label: 'Resolved Cases', value: stats.resolved_issues, icon: CheckCircle, color: '#059669', testid: 'ops-stat-resolved-cases',
      tip: 'Faults closed across Operations gyms (status = resolved or closed).' },
    { label: 'Supplier Cases', value: stats.total_supplier_cases, icon: Building2, color: '#9D4CDD', testid: 'ops-stat-supplier-cases',
      tip: 'Supplier service cases dispatched from Operations gyms.' },
  ];

  return (
    <div className="space-y-4 lg:space-y-6" data-testid="ops-overview">
      {/* Actionable alerts — operations-scoped, self-hide when empty */}
      {(stats.payments.failed > 0 || stats.suspended_orgs > 0) && (
        <div className="space-y-2" data-testid="ops-overview-alerts">
          {stats.payments.failed > 0 && (
            <Panel className="bg-rose-50 border-rose-200 p-4 flex items-center gap-3" data-testid="ops-alert-failed-payments">
              <AlertTriangle size={18} className="text-rose-600 shrink-0" />
              <p className="text-sm text-rose-700 font-semibold flex-1">{stats.payments.failed} failed payment{stats.payments.failed > 1 ? 's' : ''} require attention</p>
              {onGoPayments && <Button size="sm" className="bg-rose-600 text-white hover:bg-rose-700 rounded-full" onClick={onGoPayments} data-testid="ops-alert-go-payments">View Payments</Button>}
            </Panel>
          )}
          {stats.suspended_orgs > 0 && (
            <Panel className="bg-amber-50 border-amber-200 p-4 flex items-center gap-3" data-testid="ops-alert-suspended-orgs">
              <Ban size={18} className="text-amber-600 shrink-0" />
              <p className="text-sm text-amber-700 font-semibold flex-1">{stats.suspended_orgs} suspended organisation{stats.suspended_orgs > 1 ? 's' : ''}</p>
              {onGoSuspended && <Button size="sm" variant="outline" className="border-amber-300 text-amber-700 hover:bg-amber-100 rounded-full" onClick={onGoSuspended} data-testid="ops-alert-go-suspended">View</Button>}
            </Panel>
          )}
        </div>
      )}

      {/* Core operations KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 lg:gap-4">
        {kpiCards.map((k) => (
          <Panel
            key={k.label}
            className="p-5 cursor-help transition-shadow hover:shadow-[0_8px_24px_-8px_rgba(15,23,42,0.10)]"
            title={k.tip}
            data-testid={k.testid}
          >
            <div className="flex items-center gap-2 lg:justify-between">
              <div
                className="w-9 h-9 lg:w-11 lg:h-11 rounded-xl flex items-center justify-center flex-shrink-0 lg:order-2"
                style={{ background: k.palette.bg }}
              >
                <k.icon size={16} className="lg:w-5 lg:h-5" style={{ color: k.palette.fg }} />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-[10px] lg:text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400 leading-tight">{k.label}</p>
                <p className="text-xl lg:text-2xl font-bold text-slate-900 mt-0.5">{k.value}</p>
              </div>
            </div>
          </Panel>
        ))}
      </div>

      {/* Secondary operations stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 lg:gap-4">
        {secondaryStats.map((s) => (
          <Panel key={s.label} className="p-5 cursor-help flex items-center" title={s.tip} data-testid={s.testid}>
            <div className="flex items-center gap-3">
              <s.icon size={18} style={{ color: s.color }} />
              <div className="min-w-0 flex-1">
                <p className="text-[10px] lg:text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400 leading-tight">{s.label}</p>
                <p className="text-lg lg:text-xl font-bold text-slate-900 mt-0.5">{s.value}</p>
              </div>
            </div>
          </Panel>
        ))}
      </div>
    </div>
  );
};

export default OperationsOverview;
