import { Button } from '@/components/ui/button';
import {
  Building2, Users, AlertTriangle, Ban, CheckCircle,
  PoundSterling, Zap, BarChart3, RefreshCw,
} from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, PieChart, Pie, Cell
} from 'recharts';
import OnboardingFunnelStrip from './OnboardingFunnelStrip';
import PulseUpgradeRequestsStrip from './PulseUpgradeRequestsStrip';
import ArchiveAlertsStrip from './ArchiveAlertsStrip';
import AdminNpsPanel from './AdminNpsPanel';
import PlatformIssuesTile from './PlatformIssuesTile';
import UnifiedTrialsCard from './UnifiedTrialsCard';

/**
 * Master Admin → Dashboard Overview.
 *
 * Iter 220ea·45 — decluttered redesign. The old "wall of strips" (12
 * stacked full-width blocks, with trial data duplicated across a Trial
 * Funnel strip AND a Fresh Trials tile) is reorganised into a clear,
 * grouped, responsive bento layout with ONE source of truth per concern:
 *   1. Actionable alerts (self-hiding banners)
 *   2. Core KPIs
 *   3. Trial Pipeline — single UnifiedTrialsCard (cross-module)
 *   4. Onboarding funnel
 *   5. Growth + Subscriptions (paired)
 *   6. Platform issues + secondary stats (paired)
 *   7. NPS roll-up
 * Same visual system as the rest of Master Admin (white Panel cards,
 * slate palette, brand-blue/violet accents). All testids preserved.
 */
const PIE_COLORS = ['#2563EB', '#10B981', '#F59E0B', '#9D4CDD'];

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

const AdminOverview = ({ stats, onGoPayments, onGoSuspended, onGoOnboardingPackets, onGoTrials, onGoArchive, onGoSection, isPulseAdmin }) => {
  if (!stats) return <div className="flex items-center justify-center h-64"><RefreshCw className="animate-spin text-slate-400" size={24} /></div>;

  const kpiCards = [
    { label: 'Organisations', value: stats.total_organizations, icon: Building2, palette: KPI_PALETTES.organisations, testid: 'kpi-organisations',
      onClick: () => onGoSection?.('organizations'),
      tip: 'Total tenants on the platform — counts every organisation in the directory regardless of subscription tier or status (excludes the GymAxis Master Admin tenant).' },
    { label: 'Active Users', value: stats.total_users, icon: Users, palette: KPI_PALETTES.users, testid: 'kpi-active-users',
      onClick: () => onGoSection?.('roles'),
      tip: 'All user accounts across every organisation that have logged in at least once and aren\'t suspended.' },
    { label: 'Monthly Revenue', value: `£${stats.mrr.toLocaleString()}`, icon: PoundSterling, palette: KPI_PALETTES.revenue, testid: 'kpi-mrr',
      onClick: () => onGoPayments?.(),
      tip: 'Monthly Recurring Revenue — sum of every active paid plan\'s monthly billing amount. Trial / failed / suspended subscriptions are excluded.' },
    { label: 'Open Cases', value: stats.open_issues, icon: AlertTriangle, palette: KPI_PALETTES.cases, testid: 'kpi-open-cases',
      onClick: () => onGoSection?.('support'),
      tip: 'Faults across all gyms with status = open or in_progress. Resolved or closed faults are excluded.' },
  ];

  const subData = [
    { name: 'Free', value: stats.subscriptions.free },
    { name: 'Pro', value: stats.subscriptions.pro },
    { name: 'Premium', value: stats.subscriptions.premium },
    { name: 'Enterprise', value: stats.subscriptions.enterprise },
  ].filter(d => d.value > 0);

  // Secondary stats — Failed Payments deliberately omitted here: it has a
  // dedicated alert banner above, so showing it twice was a duplication.
  const secondaryStats = [
    { label: 'AI Calls', value: stats.ai_usage.total, icon: Zap, color: '#9D4CDD', testid: 'stat-ai-calls',
      tip: 'Total LLM API calls (Claude, GPT, Gemini) made by users across all features in the current month.' },
    { label: 'Equipment Tracked', value: stats.total_equipment, icon: BarChart3, color: '#0EA5E9', testid: 'stat-equip-tracked',
      tip: 'Every equipment record across every gym, regardless of status (in_service / out_of_service / decommissioned).' },
    { label: 'Resolved Cases', value: stats.resolved_issues, icon: CheckCircle, color: '#059669', testid: 'stat-resolved-cases',
      tip: 'Faults closed across all gyms in the last 30 days (status = resolved or closed).' },
  ];

  return (
    <div className="space-y-4 lg:space-y-6">
      {/* 1 · Actionable alerts — each self-hides when there's nothing to action */}
      {(stats.payments.failed > 0 || stats.suspended_orgs > 0) && (
        <div className="space-y-2" data-testid="overview-alerts">
          {stats.payments.failed > 0 && (
            <Panel className="bg-rose-50 border-rose-200 p-4 flex items-center gap-3" data-testid="alert-failed-payments">
              <AlertTriangle size={18} className="text-rose-600 shrink-0" />
              <p className="text-sm text-rose-700 font-semibold flex-1">{stats.payments.failed} failed payment{stats.payments.failed > 1 ? 's' : ''} require attention</p>
              <Button size="sm" className="bg-rose-600 text-white hover:bg-rose-700 rounded-full" onClick={onGoPayments} data-testid="alert-go-payments">View Payments</Button>
            </Panel>
          )}
          {stats.suspended_orgs > 0 && (
            <Panel className="bg-amber-50 border-amber-200 p-4 flex items-center gap-3" data-testid="alert-suspended-orgs">
              <Ban size={18} className="text-amber-600 shrink-0" />
              <p className="text-sm text-amber-700 font-semibold flex-1">{stats.suspended_orgs} suspended organisation{stats.suspended_orgs > 1 ? 's' : ''}</p>
              <Button size="sm" variant="outline" className="border-amber-300 text-amber-700 hover:bg-amber-100 rounded-full" onClick={onGoSuspended} data-testid="alert-go-suspended">View</Button>
            </Panel>
          )}
        </div>
      )}
      <ArchiveAlertsStrip onOpen={onGoArchive} />
      <PulseUpgradeRequestsStrip />

      {/* 2 · Core KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 lg:gap-4">
        {kpiCards.map(k => (
          <Panel
            key={k.label}
            onClick={k.onClick}
            role={k.onClick ? 'button' : undefined}
            tabIndex={k.onClick ? 0 : undefined}
            onKeyDown={k.onClick ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); k.onClick(); } } : undefined}
            className={`p-5 transition-all ${k.onClick ? 'cursor-pointer hover:-translate-y-0.5 hover:shadow-[0_12px_28px_-8px_rgba(15,23,42,0.18)]' : 'cursor-help hover:shadow-[0_8px_24px_-8px_rgba(15,23,42,0.10)]'}`}
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

      {/* 3 · Trial Pipeline — single source of truth (cross-module).
           Hidden for Pulse Master Admins (the GymAxis trial pipeline is
           platform self-promo data, not Pulse-scoped). */}
      {!isPulseAdmin && <UnifiedTrialsCard onGoTrials={onGoTrials} />}

      {/* 4 · Onboarding funnel (self-hides when empty) */}
      <OnboardingFunnelStrip onOpen={onGoOnboardingPackets} />

      {/* 5 · Growth + Subscriptions */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3 lg:gap-4">
        <Panel className="lg:col-span-8 p-5 lg:p-6" data-testid="chart-platform-growth">
          <h3 className="text-base lg:text-lg font-bold text-slate-900 tracking-tight mb-4">Platform Growth</h3>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={stats.growth_data}>
              <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
              <XAxis dataKey="month" tick={{ fontSize: 10, fill: '#94A3B8' }} />
              <YAxis tick={{ fontSize: 10, fill: '#94A3B8' }} width={30} />
              <Tooltip contentStyle={{ background: '#0F172A', border: 'none', borderRadius: 8, color: '#fff', fontSize: 12 }} />
              <Line type="monotone" dataKey="users" stroke="#2563EB" strokeWidth={2.5} dot={false} name="Users" />
              <Line type="monotone" dataKey="organizations" stroke="#9D4CDD" strokeWidth={2.5} dot={false} name="Orgs" />
            </LineChart>
          </ResponsiveContainer>
        </Panel>

        <Panel className="lg:col-span-4 p-5 lg:p-6" data-testid="chart-subscriptions-pie">
          <h3 className="text-base lg:text-lg font-bold text-slate-900 tracking-tight mb-4">Subscriptions</h3>
          <ResponsiveContainer width="100%" height={160}>
            <PieChart>
              <Pie data={subData} cx="50%" cy="50%" innerRadius={45} outerRadius={65} paddingAngle={3} dataKey="value">
                {subData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
              </Pie>
              <Tooltip contentStyle={{ background: '#0F172A', border: 'none', borderRadius: 8, color: '#fff', fontSize: 12 }} />
            </PieChart>
          </ResponsiveContainer>
          <div className="mt-2 space-y-1">
            {subData.map((d, i) => (
              <div key={d.name} className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <div className="w-2.5 h-2.5 rounded-sm" style={{ background: PIE_COLORS[i % PIE_COLORS.length] }} />
                  <span className="text-slate-600">{d.name}</span>
                </div>
                <span className="font-semibold text-slate-900">{d.value}</span>
              </div>
            ))}
          </div>
        </Panel>
      </div>

      {/* 6 · Platform issues + secondary stats */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3 lg:gap-4">
        <div className="lg:col-span-4">
          <PlatformIssuesTile onGoSection={onGoSection} />
        </div>
        <div className="lg:col-span-8 grid grid-cols-1 sm:grid-cols-3 gap-3 lg:gap-4">
          {secondaryStats.map(s => (
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

      {/* 7 · NPS roll-up */}
      <AdminNpsPanel />
    </div>
  );
};

export default AdminOverview;
