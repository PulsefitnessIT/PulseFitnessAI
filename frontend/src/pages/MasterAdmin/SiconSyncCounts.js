const ROWS = [
  ['customers', 'Customers'], ['sites', 'Sites'], ['equipment', 'Equipment'], ['contracts', 'Contracts'], ['cases', 'Cases'],
];
const COLS = [['new', 'New'], ['matched', 'Matched'], ['differences', 'Differences'], ['conflicts', 'To review'], ['failed', 'Failed']];

export default function SiconSyncCounts({ run }) {
  const counts = run.counts || {};
  const totals = run.totals || {};
  const isPreview = run.mode !== 'apply';
  return (
    <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800" data-testid="sicon-sync-counts">
      <table className="w-full text-sm">
        <thead className="bg-zinc-50 dark:bg-zinc-900/40 text-xs text-zinc-500">
          <tr>
            <th className="text-left py-2 px-3 font-medium">{isPreview ? 'Would import' : 'Imported'}</th>
            {COLS.map(([k, l]) => <th key={k} className="text-right py-2 px-3 font-medium">{l}</th>)}
          </tr>
        </thead>
        <tbody>
          {ROWS.map(([k, label]) => {
            const c = counts[k] || {};
            const unavailable = k === 'contracts' && totals.contracts === 'unavailable';
            return (
              <tr key={k} className="border-t border-zinc-100 dark:border-zinc-800" data-testid={`sicon-sync-row-${k}`}>
                <td className="py-2 px-3 font-medium text-zinc-800 dark:text-zinc-200">
                  {label}
                  {unavailable && <span className="ml-2 text-xs font-normal text-amber-600" data-testid="sicon-sync-contracts-unavailable">contract API not available on this Sicon</span>}
                </td>
                {COLS.map(([ck]) => (
                  <td key={ck} className="py-2 px-3 text-right tabular-nums text-zinc-700 dark:text-zinc-300" data-testid={`sicon-sync-${k}-${ck}`}>
                    {(c[ck] || 0).toLocaleString()}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
