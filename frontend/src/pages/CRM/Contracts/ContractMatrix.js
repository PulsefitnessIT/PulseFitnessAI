/**
 * Iter 220e3 — Contract Comparison Matrix (Phase C).
 *
 * Visual tick / cross / percentage matrix used by:
 *   • CRM → Contracts → wizard (step 10 preview)
 *   • Contract detail → "Comparison" tab
 *   • Template manager (compare side-by-side)
 *   • PDF generator (Phase D will reuse the same row data)
 *
 * Columns are templates (or a single ad-hoc draft) and rows are
 * grouped inclusion items + response-time bands. Rendered as a plain
 * accessible table so the PDF backend can reuse the row data on the
 * server side without re-deriving labels.
 */
import { Check, X, Minus } from 'lucide-react';

const TIER_COLOR = {
  silver: 'var(--color-silver)',
  gold: 'var(--color-gold)',
  platinum: '#E5E4E2',
  custom: 'var(--color-accent-violet)',
};

function CellTick({ included, value }) {
  if (value && /%/.test(String(value))) {
    return (
      <span className="text-[11px] font-bold text-emerald-700">
        {value}
      </span>
    );
  }
  if (included) {
    return <Check size={14} className="text-emerald-600 mx-auto" />;
  }
  return <Minus size={14} className="text-slate-400 mx-auto" />;
}
CellTick.displayName = 'CellTick';

export function ContractMatrix({ catalog, columns, isDark, c }) {
  // `columns` is [{ id, name, tier_slug, inclusions, response_times, exclusions, pricing }, …]
  if (!columns?.length) {
    return (
      <p className="text-xs text-center py-4" style={{ color: c.textDim }}>
        Nothing to compare.
      </p>
    );
  }
  const headerBg = isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-50)';
  const rowBg = isDark ? '#111' : '#fff';
  const border = isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)';

  return (
    <div
      className="rounded-xl border overflow-hidden"
      style={{ borderColor: border, background: rowBg }}
      data-testid="contract-comparison-matrix"
    >
      <table className="w-full text-xs">
        <thead>
          <tr style={{ background: headerBg, borderBottom: `1px solid ${border}` }}>
            <th className="text-left px-3 py-2 font-bold uppercase tracking-wide text-[10px]"
                style={{ color: c.textDim, width: '40%' }}>Feature</th>
            {columns.map(col => (
              <th key={col.id} className="text-center px-3 py-2"
                  style={{ color: TIER_COLOR[col.tier_slug] || c.text }}
                  data-testid={`matrix-col-${col.tier_slug || col.id}`}>
                <span className="font-extrabold text-xs uppercase tracking-wide">{col.name}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {catalog.inclusion_groups.map(group => (
            <GroupRows key={group.key} group={group} columns={columns}
                       headerBg={headerBg} border={border} c={c} />
          ))}
          {/* Response times — numeric values, render as text */}
          <tr style={{ background: headerBg }}>
            <td colSpan={1 + columns.length}
                className="px-3 py-1.5 font-bold uppercase tracking-wide text-[10px]"
                style={{ color: c.textDim }}>
              Response Times
            </td>
          </tr>
          {catalog.response_time_bands.map(band => (
            <tr key={band.key} style={{ borderBottom: `1px solid ${border}` }}
                data-testid={`matrix-row-rt-${band.key}`}>
              <td className="px-3 py-1.5" style={{ color: c.text }}>{band.label}</td>
              {columns.map(col => {
                const rt = col.response_times?.[band.key];
                return (
                  <td key={col.id} className="px-3 py-1.5 text-center"
                      style={{ color: rt ? c.text : c.textDim }}>
                    {rt ? `${rt.hours}h` : <Minus size={14} className="text-slate-400 mx-auto" />}
                  </td>
                );
              })}
            </tr>
          ))}
          {/* Exclusions row — chips per column */}
          {columns.some(col => (col.exclusions || []).length > 0) && (
            <>
              <tr style={{ background: headerBg }}>
                <td colSpan={1 + columns.length}
                    className="px-3 py-1.5 font-bold uppercase tracking-wide text-[10px]"
                    style={{ color: c.textDim }}>
                  Exclusions
                </td>
              </tr>
              <tr style={{ borderBottom: `1px solid ${border}` }}>
                <td className="px-3 py-1.5" style={{ color: c.text }}>Notable</td>
                {columns.map(col => {
                  const excls = (col.exclusions || []).slice(0, 4);
                  return (
                    <td key={col.id} className="px-3 py-1.5 text-center"
                        style={{ color: c.textDim, fontSize: 10 }}>
                      {excls.length
                        ? excls.map(e => labelForExclusion(catalog, e)).join(', ')
                        : <Minus size={12} className="mx-auto text-slate-400" />}
                    </td>
                  );
                })}
              </tr>
            </>
          )}
        </tbody>
      </table>
    </div>
  );
}

function GroupRows({ group, columns, headerBg, border, c }) {
  return (
    <>
      <tr style={{ background: headerBg }}>
        <td colSpan={1 + columns.length}
            className="px-3 py-1.5 font-bold uppercase tracking-wide text-[10px]"
            style={{ color: c.textDim }}>
          {group.label}
        </td>
      </tr>
      {group.items.map(item => (
        <tr key={item.key} style={{ borderBottom: `1px solid ${border}` }}
            data-testid={`matrix-row-${item.key}`}>
          <td className="px-3 py-1.5" style={{ color: c.text }}>{item.label}</td>
          {columns.map(col => {
            const included = (col.inclusions?.[group.key] || []).includes(item.key);
            return (
              <td key={col.id} className="px-3 py-1.5 text-center"
                  data-testid={`matrix-cell-${col.id}-${item.key}`}>
                {included ? (
                  <Check size={14} className="text-emerald-600 mx-auto" />
                ) : (
                  <X size={12} className="text-rose-400 mx-auto opacity-50" />
                )}
              </td>
            );
          })}
        </tr>
      ))}
    </>
  );
}
GroupRows.displayName = 'GroupRows';

function labelForExclusion(catalog, key) {
  return catalog.exclusion_items.find(e => e.key === key)?.label || key;
}

export default ContractMatrix;
