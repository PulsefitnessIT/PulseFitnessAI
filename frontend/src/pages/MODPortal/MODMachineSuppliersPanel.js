/**
 * MOD site · Machine service suppliers — see who services each machine and
 * bulk-reassign selected machines to Pulse in-house, an estate provider, a
 * site-added third-party supplier, or back to the site default.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Wrench, Plus, Check, RotateCcw } from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import { useAuth } from '@/App';

const PULSE = 'Pulse Fitness (MOD Service)';
const inputCls = 'w-full px-3 py-2 rounded-lg bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 text-sm text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-cyan-500/40';
const auth = () => ({ Authorization: `Bearer ${localStorage.getItem('token')}` });

function AddSupplierForm({ onAdded, onCancel }) {
  const { API } = useAuth();
  const [f, setF] = useState({ name: '', email: '', contact_name: '', phone: '' });
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const save = async () => {
    setBusy(true);
    try {
      const { data } = await axios.post(`${API}/mod/site/machine-suppliers/third-party`, f, { headers: auth() });
      notify.success(`${data.supplier.name} added`);
      onAdded(data.supplier);
    } catch (e) { notifyApiError(notify, e, 'Could not add supplier'); } finally { setBusy(false); }
  };
  return (
    <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900/50 p-3 grid grid-cols-1 sm:grid-cols-2 gap-2" data-testid="mod-ms-add-form">
      <input className={inputCls} placeholder="Company name *" value={f.name} onChange={set('name')} data-testid="mod-ms-add-name" />
      <input className={inputCls} placeholder="Email for fault alerts *" value={f.email} onChange={set('email')} data-testid="mod-ms-add-email" />
      <input className={inputCls} placeholder="Contact name" value={f.contact_name} onChange={set('contact_name')} data-testid="mod-ms-add-contact" />
      <input className={inputCls} placeholder="Phone" value={f.phone} onChange={set('phone')} data-testid="mod-ms-add-phone" />
      <div className="sm:col-span-2 flex justify-end gap-2">
        <button onClick={onCancel} className="px-3 py-2 text-xs font-bold rounded-lg border border-zinc-300 dark:border-zinc-700 text-zinc-700 dark:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-800" data-testid="mod-ms-add-cancel">Cancel</button>
        <button onClick={save} disabled={busy || !f.name || !f.email} className="px-3 py-2 text-xs font-extrabold rounded-lg bg-cyan-600 hover:bg-cyan-700 text-white disabled:opacity-40" data-testid="mod-ms-add-save">
          {busy ? 'Saving…' : 'Add supplier'}
        </button>
      </div>
    </div>
  );
}

function MachineRow({ m, checked, onToggle, siteDefault }) {
  return (
    <label className={`flex flex-wrap sm:flex-nowrap items-center gap-x-3 gap-y-1 px-3 py-2.5 rounded-lg border cursor-pointer transition-colors ${checked ? 'border-cyan-500 bg-cyan-50 dark:bg-cyan-500/10' : 'border-zinc-200 dark:border-zinc-800 hover:bg-zinc-50 dark:hover:bg-zinc-900'}`} data-testid={`mod-ms-row-${m.id}`}>
      <input type="checkbox" checked={checked} onChange={onToggle} className="accent-cyan-600 w-4 h-4" data-testid={`mod-ms-check-${m.id}`} />
      <div className="flex-1 min-w-0">
        <div className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 truncate">{m.name}</div>
        <div className="text-[11px] text-zinc-500 truncate">{m.serial_number || 'No serial'}{m.location ? ` · ${m.location}` : ''}</div>
      </div>
      <div className="w-full sm:w-auto pl-7 sm:pl-0 sm:text-right sm:shrink-0 sm:max-w-[45%] flex sm:block items-center gap-2">
        <div className="text-xs font-semibold text-zinc-800 dark:text-zinc-200 truncate" data-testid={`mod-ms-supplier-${m.id}`}>{m.follows_default && !siteDefault ? PULSE : (m.supplier || PULSE)}</div>
        <span className={`inline-block mt-0.5 px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${m.follows_default ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300' : 'bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300'}`} data-testid={`mod-ms-mode-${m.id}`}>
          {m.follows_default ? 'Site default' : 'Changed by site'}
        </span>
      </div>
    </label>
  );
}

function TargetSelect({ value, onChange, def, opts }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} className={`${inputCls} flex-1 min-w-[200px] w-auto`} data-testid="mod-ms-target-select">
      <option value="">Reassign selected to…</option>
      <option value="site_default">Use site default ({def?.name || PULSE})</option>
      {def && <option value="pulse">{PULSE} — in-house</option>}
      {(opts.providers || []).length > 0 && (
        <optgroup label="Service providers">
          {opts.providers.map((p) => <option key={p.id} value={`provider:${p.id}`}>{p.name}</option>)}
        </optgroup>
      )}
      {(opts.third_party || []).length > 0 && (
        <optgroup label="Your third-party suppliers">
          {opts.third_party.map((s) => <option key={s.id} value={`supplier:${s.id}`}>{s.name}</option>)}
        </optgroup>
      )}
    </select>
  );
}

export default function MODMachineSuppliersPanel() {
  const { API } = useAuth();
  const [data, setData] = useState(null);
  const [sel, setSel] = useState(new Set());
  const [target, setTarget] = useState('');
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const { data: d } = await axios.get(`${API}/mod/site/machine-suppliers`, { headers: auth() });
      setData(d);
    } catch (e) { notifyApiError(notify, e, 'Failed to load machines'); }
  }, [API]);
  useEffect(() => { load(); }, [load]);

  const machines = useMemo(() => data?.machines || [], [data]);
  const allOn = machines.length > 0 && sel.size === machines.length;
  const toggle = (id) => { const n = new Set(sel); n.has(id) ? n.delete(id) : n.add(id); setSel(n); };

  const apply = async () => {
    setBusy(true);
    try {
      const { data: r } = await axios.post(`${API}/mod/site/machine-suppliers/bulk-reassign`,
        { equipment_ids: [...sel], target }, { headers: auth() });
      notify.success(`${r.updated} machine${r.updated > 1 ? 's' : ''} → ${r.supplier}${r.emailed ? ` · emailed ${r.emailed}` : ''}`);
      setSel(new Set()); setTarget(''); load();
    } catch (e) { notifyApiError(notify, e, 'Reassign failed'); } finally { setBusy(false); }
  };

  const def = data?.site_default;

  return (
    <section className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 mb-6" data-testid="mod-machine-suppliers-panel">
      <div className="px-5 py-4 border-b border-zinc-200 dark:border-zinc-800">
        <h3 className="text-base font-bold text-zinc-900 dark:text-zinc-100">Machine service suppliers</h3>
        <p className="text-xs text-zinc-500 mt-0.5" data-testid="mod-ms-site-default">
          New and unchanged machines follow the site default: <span className="font-semibold text-zinc-800 dark:text-zinc-200">{def?.name || PULSE}</span>
        </p>
      </div>
      <div className="px-5 py-3 border-b border-zinc-200 dark:border-zinc-800 space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <button onClick={() => setSel(allOn ? new Set() : new Set(machines.map((m) => m.id)))} className="px-3 py-2 text-xs font-bold rounded-lg border border-zinc-300 dark:border-zinc-700 text-zinc-700 dark:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-800" data-testid="mod-ms-select-all">
            {allOn ? 'Clear selection' : 'Select all'}
          </button>
          <span className="text-xs text-zinc-500" data-testid="mod-ms-selected-count">{sel.size} selected</span>
          <TargetSelect value={target} onChange={setTarget} def={def} opts={data?.options || {}} />
          <button onClick={apply} disabled={busy || !sel.size || !target} className="flex items-center gap-1.5 px-3 py-2 text-xs font-extrabold rounded-lg bg-cyan-600 hover:bg-cyan-700 text-white disabled:opacity-40" data-testid="mod-ms-apply">
            {target === 'site_default' ? <RotateCcw size={13} /> : <Check size={13} />} {busy ? 'Applying…' : 'Apply'}
          </button>
        </div>
        {adding ? (
          <AddSupplierForm onCancel={() => setAdding(false)} onAdded={(s) => { setAdding(false); load(); setTarget(`supplier:${s.id}`); }} />
        ) : (
          <button onClick={() => setAdding(true)} className="flex items-center gap-1.5 text-xs font-bold text-cyan-700 dark:text-cyan-400 hover:underline" data-testid="mod-ms-add-toggle">
            <Plus size={13} /> Add another third-party supplier
          </button>
        )}
      </div>
      <div className="p-4 space-y-1.5 max-h-[60vh] overflow-y-auto" data-testid="mod-ms-list">
        {!data ? <div className="text-sm text-zinc-500 p-6 text-center">Loading…</div>
          : machines.length === 0 ? (
            <div className="text-sm text-zinc-500 p-6 text-center"><Wrench size={18} className="mx-auto mb-2" />No machines on this site yet.</div>
          ) : machines.map((m) => <MachineRow key={m.id} m={m} siteDefault={def} checked={sel.has(m.id)} onToggle={() => toggle(m.id)} />)}
      </div>
    </section>
  );
}
