import { useState } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import { ChevronDown, ChevronRight } from 'lucide-react';

const show = (v) => (v === null || v === undefined || v === '' ? '—' : String(v));

export default function SiconDifferencesList({ API, headers, openCount, conflictCount, onChange }) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);

  const load = async () => {
    try { setItems((await axios.get(`${API}/sicon/read/differences`, { headers })).data.differences || []); }
    catch (e) { notifyApiError(notify, e, 'Could not load differences'); }
  };

  const toggle = () => { if (!open) load(); setOpen(!open); };

  const resolve = async (d, action) => {
    try {
      await axios.post(`${API}/sicon/read/differences/${d.id}/resolve`, { action }, { headers });
      notify.success(action === 'use_sicon' ? 'Updated with the Sicon value' : 'Kept the Pulse value');
      setItems(items.filter(i => i.id !== d.id));
      onChange();
    } catch (e) { notifyApiError(notify, e, 'Could not resolve'); }
  };

  if (!openCount && !conflictCount) return null;
  return (
    <div className="rounded-lg border border-amber-200 dark:border-amber-900 bg-amber-50/60 dark:bg-amber-950/20" data-testid="sicon-differences-panel">
      <button type="button" onClick={toggle} className="w-full flex items-center gap-2 p-3 text-sm text-amber-900 dark:text-amber-200" data-testid="sicon-differences-toggle">
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <b>{openCount}</b> difference(s) to review
        {conflictCount > 0 && <span className="text-xs">· {conflictCount} record(s) need matching in the Equipment IDs / conflict queue</span>}
      </button>
      {open && (
        <div className="max-h-96 overflow-y-auto border-t border-amber-200 dark:border-amber-900" data-testid="sicon-differences-list">
          {items.length === 0 && <p className="p-3 text-xs text-zinc-500">Nothing left to review.</p>}
          {items.map(d => (
            <div key={d.id} className="flex flex-wrap items-center gap-3 px-3 py-2 border-b border-amber-100 dark:border-amber-900/50 text-xs" data-testid={`sicon-difference-${d.id}`}>
              <span className="w-20 font-semibold capitalize">{d.entity}</span>
              <span className="w-28 font-mono">{d.field}</span>
              <span className="flex-1 min-w-[12rem]">Pulse: <b>{show(d.pulse_value)}</b> · Sicon: <b>{show(d.sicon_value)}</b></span>
              <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => resolve(d, 'keep_pulse')} data-testid={`sicon-difference-keep-${d.id}`}>Keep Pulse</Button>
              <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => resolve(d, 'use_sicon')} data-testid={`sicon-difference-use-${d.id}`}>Use Sicon</Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
