import React, { useEffect, useState } from 'react';
import { ClipboardList, ChevronDown, CheckCircle2 } from 'lucide-react';
import { bfpo } from '../bfpoApi';
import { Card, Btn, Badge, inputCls } from '../ui';

const LABEL = {
  name: 'Description', location: 'Location', sub_location: 'Sublocation', manufacturer: 'Make',
  model: 'Model', serial_number: 'Serial Number', install_date: 'Install Date',
  last_service_date: 'Last Service Date', id_number: 'ID Number',
};
const DATES = new Set(['install_date', 'last_service_date']);

function AssetForm({ jobId, item, onSaved }) {
  const [vals, setVals] = useState({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const fields = [...new Set([...item.missing, 'sub_location'])];
  const save = async () => {
    setBusy(true); setErr('');
    try {
      const r = await bfpo.post(`/jobs/${jobId}/equipment/${item.id}/details`, vals);
      onSaved(item.id, r?.data?.queued);
    } catch (e) { setErr(e?.response?.data?.detail || 'Could not save'); }
    finally { setBusy(false); }
  };
  return (
    <div className="rounded-xl border border-slate-200 p-3 space-y-2" data-testid={`asset-gap-${item.id}`}>
      <div>
        <p className="font-semibold text-slate-900 text-sm">{item.name || 'Unnamed machine'}</p>
        <p className="text-xs text-slate-500">{[item.manufacturer, item.model, item.location].filter((v) => v && !/^\s*(unknown|n\/?a|tbc|tbd|none|-|0)\s*$/i.test(v)).join(' · ') || 'No details yet'}</p>
      </div>
      {fields.map((f) => (
        <label key={f} className="block">
          <span className="text-xs font-semibold text-slate-600">{LABEL[f] || f}{item.missing.includes(f) && <span className="text-red-600"> *</span>}</span>
          <input type={DATES.has(f) ? 'date' : 'text'} className={`${inputCls} mt-1`} defaultValue={item[f] && item[f] !== 'UNKNOWN' ? item[f] : ''}
            onChange={(e) => setVals((v) => ({ ...v, [f]: e.target.value }))} data-testid={`asset-gap-${f}-${item.id}`} />
        </label>
      ))}
      {err && <p className="text-xs text-red-600">{err}</p>}
      <Btn full onClick={save} disabled={busy || !Object.values(vals).some((v) => String(v).trim())} data-testid={`asset-gap-save-${item.id}`}>
        {busy ? 'Saving…' : 'Save details'}
      </Btn>
    </div>
  );
}

export default function MissingAssetDetails({ jobId }) {
  const [data, setData] = useState(null);
  const [open, setOpen] = useState(false);
  const [done, setDone] = useState({});
  useEffect(() => { bfpo.get(`/jobs/${jobId}/equipment-gaps`).then((r) => setData(r.data)).catch(() => {}); }, [jobId]);
  if (!data?.items?.length) return null;
  const left = data.items.filter((i) => !done[i.id]);
  return (
    <Card className="p-4 border-l-4 border-l-amber-500" data-testid="missing-asset-details">
      <button className="w-full flex items-center gap-3 text-left" onClick={() => setOpen((o) => !o)} data-testid="missing-asset-details-toggle">
        <ClipboardList className="w-5 h-5 text-amber-600 shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-xs font-semibold text-amber-700 uppercase">While you're on site</p>
          <p className="font-semibold text-slate-900 text-sm">{left.length ? `${left.length} machine${left.length > 1 ? 's' : ''} here need details` : 'All captured — thank you'}</p>
        </div>
        <ChevronDown className={`w-5 h-5 text-slate-400 transition-transform duration-200 ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="mt-3 space-y-3">
          <p className="text-xs text-slate-500">Check the plate on each machine and fill in what's missing. Red * items are required for the service record.</p>
          {data.items.map((it) => (done[it.id]
            ? <Badge key={it.id} className="bg-emerald-50 text-emerald-700 border-emerald-200" data-testid={`asset-gap-done-${it.id}`}><CheckCircle2 className="w-3 h-3" /> {it.name} — {done[it.id] === 'queued' ? 'saved on phone' : 'saved'}</Badge>
            : <AssetForm key={it.id} jobId={jobId} item={it} onSaved={(id, q) => setDone((d) => ({ ...d, [id]: q ? 'queued' : 'sent' }))} />))}
        </div>
      )}
    </Card>
  );
}
