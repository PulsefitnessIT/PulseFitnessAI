const LABELS = {
  sicon_customer_ref: 'Customer Ref', location: 'Location', name: 'Description',
  manufacturer: 'Make', model: 'Model', serial_number: 'Serial Number',
};

export const GapsSummary = ({ summary }) => {
  const pct = summary?.percent_complete ?? 0;
  const tone = pct >= 90 ? 'bg-emerald-500' : pct >= 50 ? 'bg-amber-500' : 'bg-red-500';
  return (
    <div className="space-y-2" data-testid="gaps-summary">
      <div className="flex items-baseline gap-3">
        <span className="text-2xl font-extrabold tracking-tight text-zinc-900" data-testid="gaps-percent">{pct}%</span>
        <span className="text-xs text-zinc-500">
          complete · <b className="text-zinc-800">{summary?.incomplete ?? 0}</b> of {summary?.total ?? 0} assets need information
        </span>
      </div>
      <div className="h-2 w-full rounded-full bg-zinc-100 overflow-hidden">
        <div className={`h-full ${tone} transition-[width] duration-500`} style={{ width: `${pct}%` }} />
      </div>
      <div className="flex flex-wrap gap-1.5">
        {Object.entries(summary?.by_field || {}).map(([f, n]) => (
          <span key={f} data-testid={`gaps-missing-${f}`}
            className={`text-[11px] px-2 py-0.5 rounded-full border ${n ? 'border-red-200 bg-red-50 text-red-700' : 'border-emerald-200 bg-emerald-50 text-emerald-700'}`}>
            {LABELS[f] || f}: {n ? `${n} missing` : 'done'}
          </span>
        ))}
      </div>
    </div>
  );
};
