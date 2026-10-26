import { useState } from 'react';
import { Loader2, Wand2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { PERIODS, CONDITIONS } from './GapCell';

const BULK_FIELDS = [
  ['sicon_customer_ref', 'Customer Ref'],
  ['location', 'Location'],
  ['sub_location', 'Sublocation'],
  ['manufacturer', 'Make'],
  ['equipment_group', 'Equipment Group'],
  ['service_interval', 'Service Interval'],
  ['service_period', 'Service Period'],
  ['last_service_date', 'Last Service Date'],
  ['install_date', 'Install Date'],
  ['condition', 'Condition'],
  ['equipment_type', 'Equipment Type'],
];
const OPTIONS = { service_period: PERIODS, condition: CONDITIONS };

export const BulkFillBar = ({ onApply, siteName }) => {
  const [field, setField] = useState('sicon_customer_ref');
  const [value, setValue] = useState('');
  const [onlyBlank, setOnlyBlank] = useState(true);
  const [busy, setBusy] = useState(false);
  const isDate = field.endsWith('_date');

  const apply = async () => {
    setBusy(true);
    try { await onApply(field, value, onlyBlank); setValue(''); } finally { setBusy(false); }
  };

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2.5" data-testid="gaps-bulk-bar">
      <Wand2 size={14} className="text-[var(--color-brand-blue)]" />
      <span className="text-xs font-semibold text-zinc-700">Fill a column{siteName ? ` for ${siteName}` : ' for every asset'}</span>
      <select value={field} onChange={(e) => { setField(e.target.value); setValue(''); }} className="h-8 rounded-md border border-zinc-200 bg-white px-2 text-xs" data-testid="gaps-bulk-field">
        {BULK_FIELDS.map(([f, l]) => <option key={f} value={f}>{l}</option>)}
      </select>
      {OPTIONS[field] ? (
        <select value={value} onChange={(e) => setValue(e.target.value)} className="h-8 rounded-md border border-zinc-200 bg-white px-2 text-xs" data-testid="gaps-bulk-value">
          <option value="">Choose…</option>
          {OPTIONS[field].map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
      ) : (
        <input type={isDate ? 'date' : field === 'service_interval' ? 'number' : 'text'} value={value} onChange={(e) => setValue(e.target.value)}
          placeholder="Value" className="h-8 w-44 rounded-md border border-zinc-200 bg-white px-2 text-xs" data-testid="gaps-bulk-value" />
      )}
      <label className="flex items-center gap-1.5 text-xs text-zinc-600">
        <input type="checkbox" checked={onlyBlank} onChange={(e) => setOnlyBlank(e.target.checked)} data-testid="gaps-bulk-only-blank" />
        Only blank cells
      </label>
      <Button size="sm" onClick={apply} disabled={busy || !String(value).trim()} className="h-8 bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white" data-testid="gaps-bulk-apply">
        {busy && <Loader2 size={12} className="mr-1.5 animate-spin" />} Apply
      </Button>
    </div>
  );
};
