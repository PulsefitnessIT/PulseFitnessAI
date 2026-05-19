import { Button } from '@/components/ui/button';
import {
  Building2, Users, AlertTriangle, Ban, CheckCircle, XCircle,
  PoundSterling, Zap, BarChart3, RefreshCw,
} from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, PieChart, Pie, Cell
} from 'recharts';
import OnboardingFunnelStrip from './OnboardingFunnelStrip';
import TrialFunnelStrip from './TrialFunnelStrip';
import PulseUpgradeRequestsStrip from './PulseUpgradeRequestsStrip';
import ArchiveAlertsStrip from './ArchiveAlertsStrip';
import AdminNpsPanel from './AdminNpsPanel';
import PlatformIssuesTile from './PlatformIssuesTile';
import FreshTrialsTile from './FreshTrialsTile';

/**
 * Master Admin → Dashboard Overview.
 *
 * Iter 215aw — Phase 2 GymAxis premium UI rollout. Cards use the new
 * `gx-panel` aesthetic (rounded-2xl, soft shadow, slate-200 hairline)
 * and KPI accent backgrounds use a brand-blue → brand-purple bias rather
 * than the legacy mixed Tailwind palette. All testids preserved.
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

const AdminOverview = ({ stats, onGoPayments, onGoSuspended, onGoOnboardingPackets, onGoTrials, onGoArchive, onGoSection }) => {
  if (!stats) return <div className="flex items-center justify-center h-64"><RefreshCw className="animate-spin text-slate-400" size={24} /></div>;

  const kpiCards = [
    { label: 'Organisations', value: stats.total_organizations, icon: Building2, palette: KPI_PALETTES.organisations,
      tip: 'Total tenants on the platform — counts every organisation in the directory regardless of subscription tier or status (excludes the GymAxis Master Admin tenant).' },
    { label: 'Active Users', value: stats.total_users, icon: Users, palette: KPI_PALETTES.users,
      tip: 'All user accounts across every organisation that have logged in at least once and aren\'t suspended.' },
    { label: 'Monthly Revenue', value: `£${stats.mrr.toLocaleString()}`, icon: PoundSterling, palette: KPI_PALETTES.revenue,
      tip: 'Monthly Recurring Revenue — sum of every active paid plan\'s monthly billing amount. Trial / failed / suspended subscriptions are excluded.' },
    { label: 'Open Cases', value: stats.open_issues, icon: AlertTriangle, palette: KPI_PALETTES.cases,
      tip: 'Faults across all gyms with status = open or in_progress. Resolved or closed faults are excluded.' },
  ];

  const subData = [
    { name: 'Free', value: stats.subscriptions.free },
    { name: 'Pro', value: stats.subscriptions.pro },
    { name: 'Premium', value: stats.subscriptions.premium },
    { name: 'Enterprise', value: stats.subscriptions.enterprise },
  ].filter(d => d.value > 0);

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 lg:gap-4">
        {kpiCards.map(k => (
          <Panel
            key={k.label}
            className="p-5 cursor-help transition-shadow hover:shadow-[0_8px_24px_-8px_rgba(15,23,42,0.10)]"
            title={k.tip}
            data-testid={`kpi-${k.label.toLowerCase().replace(/ /g, '-')}`}
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

      {/* Onboarding Funnel Strip */}
      <OnboardingFunnelStrip onOpen={onGoOnboardingPackets} />

      {/* Trial Funnel Strip */}
      <TrialFunnelStrip onOpen={onGoTrials} />

      {/* Pulse Pro Upgrade Requests */}
      <PulseUpgradeRequestsStrip />

      {/* Archive Alerts Strip — GDPR retention warnings */}
      <ArchiveAlertsStrip onOpen={onGoArchive} />

      {/* Charts Row — stacked on mobile. Iter 216h215 — Platform Issues
          tile (24h passive trust signal) sits beside Subscriptions.
          Iter 216h220 — Fresh Trials tile (24h prospect intel) joins
          the same row so the operator's first glance covers
          growth + risk + pipeline together. */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3 lg:gap-4">
        <Panel className="lg:col-span-6 p-5 lg:p-6">
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

        <div className="lg:col-span-3">
          <PlatformIssuesTile onGoSection={onGoSection} />
        </div>

        <div className="lg:col-span-3">
          <FreshTrialsTile onGoTrials={onGoTrials} />
        </div>
      </div>

      {/* Subscriptions pie — moved out of the charts row in 216h220 so
          the Fresh Trials tile can sit next to Platform Issues. */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3 lg:gap-4">
        <Panel className="lg:col-span-4 p-5 lg:p-6">
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

      {/* Secondary Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 lg:gap-4">
        {[
          { label: 'AI Calls', value: stats.ai_usage.total, icon: Zap, color: '#9D4CDD',
            tip: 'Total LLM API calls (Claude, GPT, Gemini) made by users across all features in the current month.' },
          { label: 'Equipment Tracked', value: stats.total_equipment, icon: BarChart3, color: '#0EA5E9',
            tip: 'Every equipment record across every gym, regardless of status (in_service / out_of_service / decommissioned).' },
          { label: 'Failed Payments', value: stats.payments.failed, icon: XCircle, color: '#DC2626',
            tip: 'Subscription invoices that failed to charge in the last 30 days and haven\'t been retried successfully yet.' },
          { label: 'Resolved Cases', value: stats.resolved_issues, icon: CheckCircle, color: '#059669',
            tip: 'Faults closed across all gyms in the last 30 days (status = resolved or closed).' },
        ].map(s => (
          <Panel key={s.label} className="p-5 cursor-help" title={s.tip}>
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

      {/* Alerts */}
      {stats.payments.failed > 0 && (
        <Panel className="bg-red-50 border-red-200 p-5 flex items-center gap-3">
          <AlertTriangle size={18} className="text-red-600" />
          <p className="text-sm text-red-700 font-semibold">{stats.payments.failed} failed payment{stats.payments.failed > 1 ? 's' : ''} require attention</p>
          <Button size="sm" className="ml-auto bg-red-600 text-white hover:bg-red-700 rounded-full" onClick={onGoPayments} data-testid="alert-go-payments">View Payments</Button>
        </Panel>
      )}
      {stats.suspended_orgs > 0 && (
        <Panel className="bg-amber-50 border-amber-200 p-5 flex items-center gap-3">
          <Ban size={18} className="text-amber-600" />
          <p className="text-sm text-amber-700 font-semibold">{stats.suspended_orgs} suspended organization{stats.suspended_orgs > 1 ? 's' : ''}</p>
          <Button size="sm" variant="outline" className="ml-auto border-amber-300 text-amber-700 hover:bg-amber-100 rounded-full" onClick={onGoSuspended} data-testid="alert-go-suspended">View</Button>
        </Panel>
      )}

      {/* Iter 215c0 — In-app NPS roll-up */}
      <AdminNpsPanel />
    </div>
  );
};

export default AdminOverview;
