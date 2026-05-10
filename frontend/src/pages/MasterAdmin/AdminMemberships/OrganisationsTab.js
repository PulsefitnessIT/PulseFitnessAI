import React, { useMemo, useState } from 'react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Lock, Unlock, Search, ShieldCheck, SlidersHorizontal } from 'lucide-react';
import { Pill, fmtMoney, fmtPct } from './shared';

/**
 * OrganisationsTab — single-tier model.
 *
 * Memberships no longer has Lite/Pro tiering at the product level. The
 * `organizations.memberships_tier` field is preserved in the DB for
 * forward-compat but is no longer surfaced or edited in the UI. Per-org
 * controls reduce to: open drawer · lock/unlock.
 */
const OrganisationsTab = ({ organizations, onSetOverrides, onOpenOrg }) => {
  const [q, setQ] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');

  const filtered = useMemo(() => {
    const ql = q.trim().toLowerCase();
    return organizations.filter((o) => {
      if (ql && !(o.name || '').toLowerCase().includes(ql)) return false;
      if (statusFilter === 'locked' && !o.locked) return false;
      if (statusFilter === 'active' && o.locked) return false;
      return true;
    });
  }, [organizations, q, statusFilter]);

  return (
    <div className="space-y-4" data-testid="memberships-admin-orgs">
      <div className="flex flex-col sm:flex-row gap-2 sm:items-center">
        <div className="relative flex-1 max-w-sm">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-400" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search by name…"
            className="pl-8 h-9 text-sm"
            data-testid="orgs-search"
          />
        </div>
        <div className="flex items-center gap-1 p-1 bg-zinc-100 rounded-md">
          {[
            { id: 'all', label: 'All' },
            { id: 'active', label: 'Active' },
            { id: 'locked', label: 'Locked' },
          ].map((t) => (
            <button
              key={t.id}
              onClick={() => setStatusFilter(t.id)}
              className={`px-3 py-1 text-xs rounded-sm font-medium ${statusFilter === t.id ? 'bg-white text-zinc-900 shadow-sm' : 'text-zinc-500 hover:text-zinc-800'}`}
              data-testid={`orgs-status-filter-${t.id}`}
            >
              {t.label}
            </button>
          ))}
        </div>
        <p className="text-xs text-zinc-500 sm:ml-auto">{filtered.length} of {organizations.length}</p>
      </div>

      <div className="bg-white border border-zinc-200 rounded-lg shadow-sm overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[11px] uppercase tracking-wider text-zinc-400 border-b border-zinc-100">
              <th className="text-left px-3 py-2.5 font-semibold">Organisation</th>
              <th className="text-right px-3 py-2.5 font-semibold">Members</th>
              <th className="text-right px-3 py-2.5 font-semibold">Plans</th>
              <th className="text-right px-3 py-2.5 font-semibold">Classes</th>
              <th className="text-right px-3 py-2.5 font-semibold">Bookings 30d</th>
              <th className="text-right px-3 py-2.5 font-semibold">MRR</th>
              <th className="text-right px-3 py-2.5 font-semibold">Churn 30d</th>
              <th className="text-left px-3 py-2.5 font-semibold">Config</th>
              <th className="text-right px-3 py-2.5 font-semibold">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((o) => (
              <tr key={o.id} className="border-b border-zinc-50 hover:bg-zinc-50/50" data-testid={`org-row-${o.id}`}>
                <td className="px-3 py-2.5">
                  <button
                    onClick={() => onOpenOrg?.(o.id)}
                    className="font-medium text-zinc-900 hover:text-blue-600 text-left"
                    data-testid={`org-open-${o.id}`}
                  >
                    {o.name}
                  </button>
                  <p className="text-[11px] text-zinc-400 truncate">{o.slug || '—'}</p>
                </td>
                <td className="px-3 py-2.5 text-right tabular-nums">{o.members}</td>
                <td className="px-3 py-2.5 text-right tabular-nums">{o.plans}</td>
                <td className="px-3 py-2.5 text-right tabular-nums">{o.classes}</td>
                <td className="px-3 py-2.5 text-right tabular-nums">{o.bookings_30d}</td>
                <td className="px-3 py-2.5 text-right tabular-nums font-semibold">{fmtMoney(o.mrr_pence)}</td>
                <td className="px-3 py-2.5 text-right tabular-nums">
                  {o.churn_rate_30d > 5 ? <span className="text-red-600 font-semibold">{fmtPct(o.churn_rate_30d)}</span> : fmtPct(o.churn_rate_30d)}
                </td>
                <td className="px-3 py-2.5">
                  <div className="flex items-center gap-1.5">
                    {o.standardisation === 'standard' ? (
                      <Pill tone="green"><ShieldCheck size={10} className="mr-1" /> Standard</Pill>
                    ) : (
                      <Pill tone="amber"><SlidersHorizontal size={10} className="mr-1" /> Customised</Pill>
                    )}
                    {o.locked && <Pill tone="red"><Lock size={10} className="mr-1" /> Locked</Pill>}
                  </div>
                </td>
                <td className="px-3 py-2.5 text-right whitespace-nowrap">
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 text-[11px] border-zinc-200"
                    onClick={() => onSetOverrides(o.id, { locked: !o.locked })}
                    data-testid={`org-toggle-lock-${o.id}`}
                  >
                    {o.locked ? <><Unlock size={12} className="mr-1" /> Unlock</> : <><Lock size={12} className="mr-1" /> Lock</>}
                  </Button>
                </td>
              </tr>
            ))}
            {!filtered.length && (
              <tr><td colSpan={9} className="px-3 py-6 text-center text-sm text-zinc-400">No organisations match your filters.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default OrganisationsTab;
