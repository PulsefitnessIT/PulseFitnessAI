/**
 * MOD Machine Suppliers — see who services each machine and bulk-reassign
 * selected machines to Pulse in-house, an estate provider, a site-added
 * third-party supplier, or back to the site default.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { X, Wrench, Plus, Check, RotateCcw } from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import { useAuth } from '@/App';

const inputCls = 'w-full px-3 py-2 rounded-lg bg-black/30 border border-white/10 text-sm text-white placeholder:text-white/30 focus:outline-none focus:border-[var(--color-brand-cyan)]';

function AddSupplierForm({ onAdded, onCancel }) {
  const { API } = useAuth();
  const [f, setF] = useState({ name: '', email: '', contact_name: '', phone: '' });
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const save = async () => {
    setBusy(true);
    try {
      const { data } = await axios.post(`${API}/mod/site/machine-suppliers/third-party`, f,
        { headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } });
      notify.success(`${data.supplier.name} added`);
      onAdded(data.supplier);
    } catch (e) { notifyApiError(notify, e, 'Could not add supplier'); } finally { setBusy(false); }
  };
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3 grid grid-cols-1 sm:grid-cols-2 gap-2" data-testid="mod-ms-add-form">
      <input className={inputCls} placeholder="Company name *" value={f.name} onChange={set('name')} data-testid="mod-ms-add-name" />
      <input className={inputCls} placeholder="Email for fault alerts *" value={f.email} onChange={set('email')} data-testid="mod-ms-add-email" />
      <input className={inputCls} placeholder="Contact name" value={f.contact_name} onChange={set('contact_name')} data-testid="mod-ms-add-contact" />
      <input className={inputCls} placeholder="Phone" value={f.phone} onChange={set('phone')} data-testid="mod-ms-add-phone" />
      <div className="sm:col-span-2 flex justify-end gap-2">
        <button onClick={onCancel} className="px-3 py-2 text-xs font-bold rounded-lg border border-white/10 hover:bg-white/5" data-testid="mod-ms-add-cancel">Cancel</button>
        <button onClick={save} disabled={busy || !f.name || !f.email} className="px-3 py-2 text-xs font-extrabold rounded-lg bg-[var(--color-brand-cyan)] text-black disabled:opacity-40" data-testid="mod-ms-add-save">
          {busy ? 'Saving…' : 'Add supplier'}
        </button>
      </div>
    </div>
  );
}

function MachineRow({ m, checked, onToggle }) {
  return (
    <label className={`flex items-center gap-3 px-3 py-2.5 rounded-lg border cursor-pointer transition-colors ${checked ? 'border-[var(--color-brand-cyan)]/60 bg-[var(--color-brand-cyan)]/5' : 'border-white/5 hover:bg-white/[0.03]'}`} data-testid={`mod-ms-row-${m.id}`}>
      <input type="checkbox" checked={checked} onChange={onToggle} className="accent-cyan-400 w-4 h-4" data-testid={`mod-ms-check-${m.id}`} />
      <div className="flex-1 min-w-0">
        <div className="text-sm font-bold truncate">{m.name}</div>
        <div className="text-[11px] text-white/50 truncate">{m.serial_number || 'No serial'}{m.location ? ` · ${m.location}` : ''}</div>
      </div>
      <div className="text-right shrink-0 max-w-[45%]">
        <div className="text-xs font-semibold truncate" data-testid={`mod-ms-supplier-${m.id}`}>{m.supplier || 'Pulse Fitness (MOD Service)'}</div>
        <span className={`text-[10px] font-bold uppercase tracking-wider ${m.follows_default ? 'text-emerald-300' : 'text-amber-300'}`} data-testid={`mod-ms-mode-${m.id}`}>
          {m.follows_default ? 'Site default' : 'Changed by site'}
        </span>
      </div>
    </label>
  );
}

export default function MODMachineSuppliersModal({ onClose }) {
  const { API } = useAuth();
  const [data, setData] = useState(null);
  const [sel, setSel] = useState(new Set());
  const [target, setTarget] = useState('');
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);
  const headers = { Authorization: `Bearer ${localStorage.getItem('token')}` };

  const load = useCallback(async () => {
    try {
      const { data: d } = await axios.get(`${API}/mod/site/machine-suppliers`, { headers });
      setData(d);
    } catch (e) { notifyApiError(notify, e, 'Failed to load machines'); }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- headers is rebuilt each render from localStorage
  }, [API]);
  useEffect(() => { load(); }, [load]);

  const machines = useMemo(() => data?.machines || [], [data]);
  const allOn = machines.length > 0 && sel.size === machines.length;
  const toggle = (id) => { const n = new Set(sel); n.has(id) ? n.delete(id) : n.add(id); setSel(n); };

  const apply = async () => {
    setBusy(true);
    try {
      const { data: r } = await axios.post(`${API}/mod/site/machine-suppliers/bulk-reassign`,
        { equipment_ids: [...sel], target }, { headers });
      notify.success(`${r.updated} machine${r.updated > 1 ? 's' : ''} → ${r.supplier}${r.emailed ? ` · emailed ${r.emailed}` : ''}`);
      setSel(new Set()); setTarget(''); load();
    } catch (e) { notifyApiError(notify, e, 'Reassign failed'); } finally { setBusy(false); }
  };

  const opts = data?.options || {};
  const def = data?.site_default;

  return (
    <div className="fixed inset-0 z-[80] bg-black/80 backdrop-blur-sm grid place-items-center p-4" data-testid="mod-machine-suppliers-modal" onClick={onClose}>
      <div className="w-full max-w-3xl bg-[var(--color-ink-deep)] border border-white/10 rounded-2xl overflow-hidden max-h-[90vh] flex flex-col text-white" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-4 border-b border-white/10 bg-[var(--color-surface-darker)]">
          <div>
            <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--color-brand-cyan)]">MOD Portal</div>
            <h2 className="text-lg font-extrabold tracking-tight">Machine service suppliers</h2>
            <div className="text-xs text-white/50" data-testid="mod-ms-site-default">
              Site default: <span className="text-white/80 font-semibold">{def?.name || 'Pulse Fitness (MOD Service)'}</span>
            </div>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-white/5 text-white/60" data-testid="mod-ms-close"><X size={18} /></button>
        </div>

        <div className="px-5 py-3 border-b border-white/10 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <button onClick={() => setSel(allOn ? new Set() : new Set(machines.map((m) => m.id)))} className="px-3 py-2 text-xs font-bold rounded-lg border border-white/10 hover:bg-white/5" data-testid="mod-ms-select-all">
              {allOn ? 'Clear selection' : 'Select all'}
            </button>
            <span className="text-xs text-white/50" data-testid="mod-ms-selected-count">{sel.size} selected</span>
            <select value={target} onChange={(e) => setTarget(e.target.value)} className={`${inputCls} flex-1 min-w-[200px] w-auto`} data-testid="mod-ms-target-select">
              <option value="">Reassign selected to…</option>
              <option value="site_default">Use site default ({def?.name || 'Pulse Fitness'})</option>
              <option value="pulse">{opts.pulse?.name || 'Pulse Fitness (MOD Service)'} — in-house</option>
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
            <button onClick={apply} disabled={busy || !sel.size || !target} className="flex items-center gap-1.5 px-3 py-2 text-xs font-extrabold rounded-lg bg-[var(--color-brand-cyan)] text-black disabled:opacity-40" data-testid="mod-ms-apply">
              {target === 'site_default' ? <RotateCcw size={13} /> : <Check size={13} />} {busy ? 'Applying…' : 'Apply'}
            </button>
          </div>
          {adding ? (
            <AddSupplierForm onCancel={() => setAdding(false)} onAdded={(s) => { setAdding(false); load(); setTarget(`supplier:${s.id}`); }} />
          ) : (
            <button onClick={() => setAdding(true)} className="flex items-center gap-1.5 text-xs font-bold text-[var(--color-brand-cyan)] hover:underline" data-testid="mod-ms-add-toggle">
              <Plus size={13} /> Add another third-party supplier
            </button>
          )}
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-1.5" data-testid="mod-ms-list">
          {!data ? <div className="text-sm text-white/50 p-6 text-center">Loading…</div>
            : machines.length === 0 ? (
              <div className="text-sm text-white/50 p-6 text-center"><Wrench size={18} className="mx-auto mb-2" />No machines on this site yet.</div>
            ) : machines.map((m) => <MachineRow key={m.id} m={m} checked={sel.has(m.id)} onToggle={() => toggle(m.id)} />)}
        </div>
      </div>
    </div>
  );
}
