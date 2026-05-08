import React from 'react';
import {
  ResponsiveContainer, LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
} from 'recharts';
import { StatCard, SectionCard, Pill, fmtPct } from './shared';
import { Activity, AlertTriangle, TrendingDown } from 'lucide-react';

const EngagementTab = ({ engagement }) => {
  if (!engagement) return null;
  const { daily, peak_hours, utilisation, no_show, churn } = engagement;

  return (
    <div className="space-y-5" data-testid="memberships-admin-engagement">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard label="No-show rate 30d" value={fmtPct(no_show.pct)} hint={`${no_show.no_shows_30d} of ${no_show.total_30d}`} icon={AlertTriangle} color="text-red-600" bg="bg-red-50" testid="eng-noshow" />
        <StatCard label="Bookings 30d" value={no_show.total_30d.toLocaleString()} icon={Activity} color="text-blue-600" bg="bg-blue-50" testid="eng-total" />
        <StatCard label="High-churn orgs" value={churn.filter((c) => c.churn_rate_30d > 5).length} icon={TrendingDown} color="text-red-600" bg="bg-red-50" testid="eng-high-churn" />
        <StatCard label="Low-utilisation orgs" value={utilisation.filter((u) => u.utilisation_pct < 40).length} icon={TrendingDown} color="text-amber-600" bg="bg-amber-50" testid="eng-low-util" />
      </div>

      <SectionCard title="Daily bookings & check-ins — last 30 days">
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={daily}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-paper-alt)" />
            <XAxis dataKey="date" tick={{ fontSize: 10, fill: 'var(--color-text-faint)' }} />
            <YAxis tick={{ fontSize: 11, fill: 'var(--color-text-faint)' }} width={30} />
            <Tooltip contentStyle={{ background: 'var(--color-neutral-950-alt)', border: 'none', borderRadius: 6, color: '#fff', fontSize: 12 }} />
            <Line type="monotone" dataKey="bookings" stroke="var(--color-blue-600)" strokeWidth={2} dot={false} name="Bookings" />
            <Line type="monotone" dataKey="checkins" stroke="var(--color-success)" strokeWidth={2} dot={false} name="Check-ins" />
          </LineChart>
        </ResponsiveContainer>
      </SectionCard>

      <SectionCard title="Peak hours (bookings last 30d)">
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={peak_hours}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-paper-alt)" />
            <XAxis dataKey="hour" tick={{ fontSize: 10, fill: 'var(--color-text-faint)' }} interval={1} />
            <YAxis tick={{ fontSize: 11, fill: 'var(--color-text-faint)' }} width={30} />
            <Tooltip contentStyle={{ background: 'var(--color-neutral-950-alt)', border: 'none', borderRadius: 6, color: '#fff', fontSize: 12 }} />
            <Bar dataKey="bookings" fill="var(--color-accent-violet)" radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </SectionCard>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <SectionCard title="Class utilisation — by organisation">
          <div className="max-h-72 overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-white">
                <tr className="text-[11px] uppercase tracking-wider text-zinc-400 border-b border-zinc-100">
                  <th className="text-left px-2 py-2">Organisation</th>
                  <th className="text-right px-2 py-2">Bookings / capacity</th>
                  <th className="text-right px-2 py-2">Util.</th>
                </tr>
              </thead>
              <tbody>
                {utilisation.length === 0 ? (
                  <tr><td colSpan={3} className="text-center text-zinc-400 py-6">No utilisation data.</td></tr>
                ) : utilisation.map((u) => (
                  <tr key={u.organization_id} className="border-b border-zinc-50" data-testid={`util-${u.organization_id}`}>
                    <td className="px-2 py-2 font-medium text-zinc-800 truncate max-w-[180px]">{u.name}</td>
                    <td className="px-2 py-2 text-right tabular-nums text-zinc-500">{u.booked_30d} / {u.capacity_30d}</td>
                    <td className="px-2 py-2 text-right">
                      <Pill tone={u.utilisation_pct >= 70 ? 'green' : u.utilisation_pct >= 40 ? 'amber' : 'red'}>
                        {fmtPct(u.utilisation_pct)}
                      </Pill>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>

        <SectionCard title="Churn leaderboard (30d)">
          <div className="max-h-72 overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-white">
                <tr className="text-[11px] uppercase tracking-wider text-zinc-400 border-b border-zinc-100">
                  <th className="text-left px-2 py-2">Organisation</th>
                  <th className="text-right px-2 py-2">Cancelled</th>
                  <th className="text-right px-2 py-2">Churn</th>
                </tr>
              </thead>
              <tbody>
                {churn.length === 0 ? (
                  <tr><td colSpan={3} className="text-center text-zinc-400 py-6">No churn data.</td></tr>
                ) : churn.map((c) => (
                  <tr key={c.organization_id} className="border-b border-zinc-50" data-testid={`churn-${c.organization_id}`}>
                    <td className="px-2 py-2 font-medium text-zinc-800 truncate max-w-[180px]">{c.name}</td>
                    <td className="px-2 py-2 text-right tabular-nums">{c.cancelled_30d} / {c.members}</td>
                    <td className="px-2 py-2 text-right">
                      <Pill tone={c.churn_rate_30d >= 5 ? 'red' : c.churn_rate_30d >= 2 ? 'amber' : 'green'}>
                        {fmtPct(c.churn_rate_30d)}
                      </Pill>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>
      </div>
    </div>
  );
};

export default EngagementTab;
