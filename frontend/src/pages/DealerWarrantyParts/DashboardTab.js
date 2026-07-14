import { useEffect, useState } from 'react';
import { dpApi } from './api';
import { StatCard, StatusBadge, Spinner, money } from './shared';

export default function DashboardTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    dpApi.dashboard().then(setData).catch(() => setData(null)).finally(() => setLoading(false));
  }, []);

  if (loading) return <Spinner />;
  const c = data?.cards || {};
  const byCountry = data?.allowance_by_country || [];
  const maxC = Math.max(1, ...byCountry.map((x) => x.allowance));

  return (
    <div className="space-y-6" data-testid="dp-dashboard">
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
        <StatCard testid="dp-card-dealers" label="Active dealers" value={c.dealers ?? 0} tone="brand" />
        <StatCard testid="dp-card-stores" label="Remote stores" value={c.stores ?? 0} />
        <StatCard testid="dp-card-stock-value" label="Dealer stock value" value={money(c.stock_value)} tone="emerald" />
        <StatCard testid="dp-card-allowance" label="Warranty allowance" value={money(c.allowance_total)} />
        <StatCard testid="dp-card-remaining" label="Allowance remaining" value={money(c.allowance_remaining)} tone="brand" />
        <StatCard testid="dp-card-orders" label="Orders imported" value={c.orders_count ?? 0} />
        <StatCard testid="dp-card-approved" label="Parts approved" value={money(c.approved_value)} />
        <StatCard testid="dp-card-awaiting-approval" label="Awaiting approval" value={c.awaiting_approval ?? 0} tone={c.awaiting_approval ? 'amber' : 'slate'} />
        <StatCard testid="dp-card-awaiting-receipt" label="Awaiting receipt" value={c.awaiting_receipt ?? 0} tone={c.awaiting_receipt ? 'amber' : 'slate'} />
        <StatCard testid="dp-card-low-stock" label="Low / out of stock" value={c.low_stock ?? 0} tone={c.low_stock ? 'red' : 'slate'} />
      </div>

      <div className="grid md:grid-cols-2 gap-5">
        <div className="rounded-xl border border-slate-200 bg-white p-5" data-testid="dp-allowance-by-country">
          <h3 className="text-sm font-bold text-slate-900 mb-4">Warranty allowance by country</h3>
          {byCountry.length === 0 && <p className="text-sm text-slate-400">No orders imported yet.</p>}
          <div className="space-y-3">
            {byCountry.map((row) => (
              <div key={row.country}>
                <div className="flex justify-between text-xs mb-1">
                  <span className="font-medium text-slate-700">{row.country}</span>
                  <span className="tabular-nums text-slate-500">{money(row.allowance)}</span>
                </div>
                <div className="h-2 rounded-full bg-slate-100 overflow-hidden">
                  <div className="h-full rounded-full bg-gradient-to-r from-[var(--gx-brand-from)] to-[var(--gx-brand-to)]" style={{ width: `${(row.allowance / maxC) * 100}%` }} />
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-5" data-testid="dp-recent-allocations">
          <h3 className="text-sm font-bold text-slate-900 mb-4">Recent allocations</h3>
          {(data?.recent_allocations || []).length === 0 && <p className="text-sm text-slate-400">No allocations yet.</p>}
          <div className="space-y-2">
            {(data?.recent_allocations || []).map((a) => (
              <div key={a.id} className="flex items-center justify-between py-2 border-b border-slate-50 last:border-0">
                <div className="min-w-0">
                  <div className="text-sm font-medium text-slate-800 truncate">{a.dealer_name}</div>
                  <div className="text-xs text-slate-400">{money(a.recommended_value)} · {(a.items || []).length} parts</div>
                </div>
                <StatusBadge status={a.status} />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
