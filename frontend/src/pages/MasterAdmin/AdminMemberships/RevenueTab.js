import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, PieChart, Pie, Cell,
} from 'recharts';
import { PoundSterling, XCircle, RotateCcw, FileDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { StatCard, SectionCard, fmtMoney, fmtPct } from './shared';

const PIE_COLORS = ['var(--color-blue-600)', 'var(--color-success)', 'var(--color-warning)', 'var(--color-accent-violet)', 'var(--color-danger)'];

const downloadCsv = (rows, filename) => {
  if (!rows.length) return;
  const keys = Object.keys(rows[0]);
  const body = [keys.join(','), ...rows.map((r) => keys.map((k) => `"${String(r[k] ?? '').replace(/"/g, '""')}"`).join(','))].join('\n');
  const blob = new Blob([body], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
};

const RevenueTab = ({ revenue }) => {
  if (!revenue) return null;
  const { by_org, by_kind, payments, trend, total_mrr_pence } = revenue;

  return (
    <div className="space-y-5" data-testid="memberships-admin-revenue">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard label="Platform MRR" value={fmtMoney(total_mrr_pence)} icon={PoundSterling} color="text-emerald-600" bg="bg-emerald-50" testid="rev-mrr" />
        <StatCard label="Failed payments 90d" value={payments.failed_90d} hint={fmtPct(payments.failed_pct)} icon={XCircle} color="text-red-600" bg="bg-red-50" testid="rev-failed" />
        <StatCard label="Refunds 90d" value={payments.refunds_90d} icon={RotateCcw} color="text-amber-600" bg="bg-amber-50" testid="rev-refunds" />
        <StatCard label="Total transactions 90d" value={payments.total_90d} icon={PoundSterling} color="text-violet-600" bg="bg-violet-50" testid="rev-total-txn" />
      </div>

      <SectionCard title="Revenue trend (6 months, booked)">
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={trend}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-paper-alt)" />
            <XAxis dataKey="month" tick={{ fontSize: 11, fill: 'var(--color-text-faint)' }} />
            <YAxis tick={{ fontSize: 11, fill: 'var(--color-text-faint)' }} width={60} tickFormatter={(v) => `£${Math.round(v / 100).toLocaleString()}`} />
            <Tooltip contentStyle={{ background: 'var(--color-neutral-950-alt)', border: 'none', borderRadius: 6, color: '#fff', fontSize: 12 }} formatter={(v) => fmtMoney(v)} />
            <Bar dataKey="revenue_pence" fill="var(--color-blue-600)" name="Revenue" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </SectionCard>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <SectionCard
          title="MRR by organisation (top 50)"
          className="lg:col-span-8"
          action={
            <Button size="sm" variant="outline" onClick={() => downloadCsv(by_org, 'mrr_by_org.csv')} data-testid="export-mrr-org-csv">
              <FileDown size={14} className="mr-1" /> CSV
            </Button>
          }
        >
          <div className="max-h-80 overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-white">
                <tr className="text-[11px] uppercase tracking-wider text-zinc-400 border-b border-zinc-100">
                  <th className="text-left px-2 py-2">Organisation</th>
                  <th className="text-right px-2 py-2">Members</th>
                  <th className="text-right px-2 py-2">MRR</th>
                </tr>
              </thead>
              <tbody>
                {by_org.length === 0 ? (
                  <tr><td colSpan={3} className="text-center text-zinc-400 py-6">No active subscriptions yet.</td></tr>
                ) : by_org.map((r) => (
                  <tr key={r.organization_id} className="border-b border-zinc-50" data-testid={`rev-org-${r.organization_id}`}>
                    <td className="px-2 py-2 font-medium text-zinc-800">{r.name}</td>
                    <td className="px-2 py-2 text-right tabular-nums">{r.members}</td>
                    <td className="px-2 py-2 text-right tabular-nums font-semibold">{fmtMoney(r.mrr_pence)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>

        <SectionCard title="MRR by plan kind" className="lg:col-span-4">
          {by_kind.length === 0 ? (
            <p className="text-sm text-zinc-400">No breakdown yet.</p>
          ) : (
            <>
              <ResponsiveContainer width="100%" height={180}>
                <PieChart>
                  <Pie data={by_kind} cx="50%" cy="50%" innerRadius={50} outerRadius={75} paddingAngle={3} dataKey="mrr_pence" nameKey="kind">
                    {by_kind.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                  </Pie>
                  <Tooltip formatter={(v) => fmtMoney(v)} contentStyle={{ background: 'var(--color-neutral-950-alt)', border: 'none', borderRadius: 6, color: '#fff', fontSize: 12 }} />
                </PieChart>
              </ResponsiveContainer>
              <div className="space-y-1 mt-2">
                {by_kind.map((r, i) => (
                  <div key={r.kind} className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2">
                      <span className="w-2.5 h-2.5 rounded-sm" style={{ background: PIE_COLORS[i % PIE_COLORS.length] }} />
                      <span className="text-zinc-600 capitalize">{r.kind}</span>
                    </div>
                    <span className="font-medium text-zinc-900">{fmtMoney(r.mrr_pence)} · {r.members}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </SectionCard>
      </div>
    </div>
  );
};

export default RevenueTab;
