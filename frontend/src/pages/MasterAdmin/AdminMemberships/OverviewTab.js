import {
  Users, PoundSterling, Calendar, AlertTriangle, TrendingUp, Activity,
} from 'lucide-react';
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
} from 'recharts';
import { StatCard, SectionCard, Pill, fmtMoney, fmtPct } from './shared';

const OverviewTab = ({ overview, onDrillOrg }) => {
  if (!overview) return null;
  const { kpis, high_risk_orgs, trend } = overview;

  return (
    <div className="space-y-5" data-testid="memberships-admin-overview">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 lg:gap-4">
        <StatCard label="Total Organisations" value={kpis.total_organizations?.toLocaleString() || 0} icon={Users} color="text-blue-600" bg="bg-blue-50" testid="mkpi-orgs" />
        <StatCard label="Active Members" value={kpis.active_members?.toLocaleString() || 0} hint={`${kpis.inactive_members || 0} inactive`} icon={Activity} color="text-emerald-600" bg="bg-emerald-50" testid="mkpi-active" />
        <StatCard label="Total MRR" value={fmtMoney(kpis.total_mrr_pence)} hint="across all orgs" icon={PoundSterling} color="text-violet-600" bg="bg-violet-50" testid="mkpi-mrr" />
        <StatCard label="Bookings 30d" value={kpis.bookings_30d?.toLocaleString() || 0} hint={`${kpis.bookings_7d || 0} this week`} icon={Calendar} color="text-amber-600" bg="bg-amber-50" testid="mkpi-bookings" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 lg:gap-4">
        <StatCard label="Churn 30d" value={fmtPct(kpis.churn_pct_30d)} hint={`${kpis.cancelled_30d || 0} cancellations`} icon={TrendingUp} color="text-red-600" bg="bg-red-50" testid="mkpi-churn" />
        <StatCard label="Occupancy 7d" value={fmtPct(kpis.occupancy_pct_7d)} icon={Activity} color="text-teal-600" bg="bg-teal-50" testid="mkpi-occupancy" />
        <StatCard label="No-shows 30d" value={kpis.no_shows_30d?.toLocaleString() || 0} icon={AlertTriangle} color="text-orange-600" bg="bg-orange-50" testid="mkpi-noshow" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3 lg:gap-4">
        <SectionCard title="Platform growth (bookings + new members)" className="lg:col-span-8">
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={trend}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-paper-alt)" />
              <XAxis dataKey="month" tick={{ fontSize: 11, fill: 'var(--color-text-faint)' }} />
              <YAxis tick={{ fontSize: 11, fill: 'var(--color-text-faint)' }} width={40} />
              <Tooltip contentStyle={{ background: 'var(--color-neutral-950-alt)', border: 'none', borderRadius: 6, color: '#fff', fontSize: 12 }} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Line type="monotone" dataKey="bookings" stroke="var(--color-blue-600)" strokeWidth={2} dot={false} name="Bookings" />
              <Line type="monotone" dataKey="new_members" stroke="var(--color-success)" strokeWidth={2} dot={false} name="New members" />
            </LineChart>
          </ResponsiveContainer>
        </SectionCard>

        <SectionCard title="High-risk organisations" className="lg:col-span-4">
          {(!high_risk_orgs || !high_risk_orgs.length) ? (
            <p className="text-sm text-zinc-400">No high-risk organisations — churn below 5% threshold.</p>
          ) : (
            <div className="space-y-2" data-testid="high-risk-list">
              {high_risk_orgs.slice(0, 6).map((o) => (
                <button
                  key={o.organization_id}
                  onClick={() => onDrillOrg?.(o.organization_id)}
                  className="w-full flex items-center justify-between p-2.5 rounded-md border border-red-100 bg-red-50/40 hover:bg-red-50 transition-colors text-left"
                  data-testid={`high-risk-${o.organization_id}`}
                >
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-zinc-900 truncate">{o.name}</p>
                    <p className="text-[11px] text-zinc-500">{o.members} members · {o.cancelled_30d} cancelled</p>
                  </div>
                  <Pill tone="red">{fmtPct(o.churn_rate)}</Pill>
                </button>
              ))}
            </div>
          )}
        </SectionCard>
      </div>
    </div>
  );
};

export default OverviewTab;
