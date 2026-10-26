import { useState, useEffect } from 'react';
import { Loader2 } from 'lucide-react';

export const PERIODS = ['Days', 'Weeks', 'Months', 'Years'];
export const CONDITIONS = ['New', 'Good', 'Fair', 'Poor', 'Out of Service'];
const DATE_FIELDS = new Set(['install_date', 'last_service_date', 'next_service_date', 'warranty_expiry', 'manufacturing_date', 'contract_start_date', 'contract_end_date']);
const OPTIONS = { service_period: PERIODS, condition: CONDITIONS };

const PLACEHOLDER = /^\s*(unknown|n\/?a|tbc|tbd|none|null|-|0)\s*$/i;
const shown = (v, missing) => (missing && PLACEHOLDER.test(String(v ?? '')) ? '' : (v ?? ''));

export const GapCell = ({ item, field, missing, onSave, width = 'w-36' }) => {
  const initial = shown(item[field], missing);
  const [val, setVal] = useState(initial);
  const [busy, setBusy] = useState(false);
  useEffect(() => { setVal(shown(item[field], missing)); }, [item, field, missing]);

  const commit = async (next) => {
    if (String(next ?? '') === String(initial ?? '')) return;
    setBusy(true);
    try { await onSave(item.id, field, next); } catch { setVal(initial); } finally { setBusy(false); }
  };

  const tone = missing
    ? 'border-red-300 bg-red-50 placeholder:text-red-400 focus:ring-red-400'
    : 'border-zinc-200 bg-white focus:ring-[var(--color-brand-blue)]';
  const cls = `${width} h-8 rounded-md border px-2 text-xs text-zinc-900 focus:outline-none focus:ring-2 transition-colors duration-150 ${tone}`;
  const tid = `gap-cell-${field}-${item.id}`;

  return (
    <div className="relative">
      {OPTIONS[field] ? (
        <select value={val || ''} onChange={(e) => { setVal(e.target.value); commit(e.target.value); }} className={cls} data-testid={tid}>
          <option value="">—</option>
          {OPTIONS[field].map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
      ) : (
        <input
          type={DATE_FIELDS.has(field) ? 'date' : field === 'service_interval' ? 'number' : 'text'}
          value={val || ''}
          placeholder={missing ? 'Needed' : ''}
          onChange={(e) => setVal(e.target.value)}
          onBlur={() => commit(val)}
          onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur(); }}
          className={cls}
          data-testid={tid}
        />
      )}
      {busy && <Loader2 size={12} className="absolute right-1.5 top-2 animate-spin text-zinc-400" />}
    </div>
  );
};
