import { Trophy, AlertCircle } from 'lucide-react';
import { SectionCard, Pill, fmtPct } from './shared';

const InstructorsTab = ({ instructors }) => {
  if (!instructors) return null;
  const { leaderboard, top, underperformers } = instructors;

  const Row = ({ r, rank, tone }) => (
    <div className="flex items-center justify-between py-2 border-b border-zinc-50 last:border-b-0" data-testid={`instr-${r.organization_id}-${r.instructor_name}`}>
      <div className="flex items-center gap-3 min-w-0">
        {rank != null && (
          <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold ${tone === 'top' ? 'bg-amber-100 text-amber-700' : 'bg-red-100 text-red-700'}`}>
            {rank + 1}
          </div>
        )}
        <div className="min-w-0">
          <p className="text-sm font-medium text-zinc-900 truncate">{r.instructor_name}</p>
          <p className="text-[11px] text-zinc-500 truncate">{r.org_name}</p>
        </div>
      </div>
      <div className="flex items-center gap-3 flex-shrink-0">
        <div className="text-right">
          <p className="text-xs text-zinc-500">{r.classes_delivered_30d} classes · {r.bookings_30d}/{r.capacity_30d}</p>
        </div>
        <Pill tone={r.utilisation_pct >= 70 ? 'green' : r.utilisation_pct >= 40 ? 'amber' : 'red'}>{fmtPct(r.utilisation_pct)}</Pill>
      </div>
    </div>
  );

  return (
    <div className="space-y-4" data-testid="memberships-admin-instructors">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <SectionCard
          title="Top performing instructors"
          action={<Trophy size={16} className="text-amber-500" />}
        >
          {top.length === 0 ? (
            <p className="text-sm text-zinc-400 py-4 text-center">No instructor data yet.</p>
          ) : (
            <div>{top.map((r, i) => <Row key={`${r.organization_id}-${r.instructor_name}-t`} r={r} rank={i} tone="top" />)}</div>
          )}
        </SectionCard>

        <SectionCard
          title="Underperforming instructors"
          action={<AlertCircle size={16} className="text-red-500" />}
        >
          {underperformers.length === 0 ? (
            <p className="text-sm text-zinc-400 py-4 text-center">No instructors below 40% utilisation — strong overall performance.</p>
          ) : (
            <div>{underperformers.map((r, i) => <Row key={`${r.organization_id}-${r.instructor_name}-u`} r={r} rank={i} tone="under" />)}</div>
          )}
        </SectionCard>
      </div>

      <SectionCard title={`Full instructor leaderboard · ${leaderboard.length} instructors`}>
        <div className="max-h-96 overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-white">
              <tr className="text-[11px] uppercase tracking-wider text-zinc-400 border-b border-zinc-100">
                <th className="text-left px-2 py-2">Instructor</th>
                <th className="text-left px-2 py-2">Org</th>
                <th className="text-right px-2 py-2">Classes 30d</th>
                <th className="text-right px-2 py-2">Bookings / Capacity</th>
                <th className="text-right px-2 py-2">Utilisation</th>
              </tr>
            </thead>
            <tbody>
              {leaderboard.length === 0 ? (
                <tr><td colSpan={5} className="text-center text-zinc-400 py-6">No instructor data.</td></tr>
              ) : leaderboard.map((r) => (
                <tr key={`${r.organization_id}-${r.instructor_name}`} className="border-b border-zinc-50">
                  <td className="px-2 py-2 font-medium text-zinc-800">{r.instructor_name}</td>
                  <td className="px-2 py-2 text-zinc-500">{r.org_name}</td>
                  <td className="px-2 py-2 text-right tabular-nums">{r.classes_delivered_30d}</td>
                  <td className="px-2 py-2 text-right tabular-nums text-zinc-500">{r.bookings_30d} / {r.capacity_30d}</td>
                  <td className="px-2 py-2 text-right">
                    <Pill tone={r.utilisation_pct >= 70 ? 'green' : r.utilisation_pct >= 40 ? 'amber' : 'red'}>{fmtPct(r.utilisation_pct)}</Pill>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>
    </div>
  );
};

export default InstructorsTab;
