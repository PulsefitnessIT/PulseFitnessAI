/**
 * CRMTerritoryOffices.js
 *
 * Sidebar panel to manage physical office / depot locations that get
 * pinned on the coverage map. Kept in its own file to keep the map
 * component's JSX tree shallow. Owns no data — the parent map holds
 * `offices` state and reloads via `onChange` after each mutation.
 */
import { useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Building2, Plus, Trash2, X, MapPin, Search } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('crm_token') || localStorage.getItem('token') || ''}` } });

const BLANK = { name: '', postcode: '', address: '', lat: '', lng: '', colour_hex: '#0F172A' };

export default function OfficesPanel({ offices, onChange, focusOffice }) {
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState(BLANK);
  const [saving, setSaving] = useState(false);
  const [locating, setLocating] = useState(false);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const lookupPostcode = async () => {
    if (!form.postcode.trim()) { toast.error('Enter a postcode first'); return; }
    setLocating(true);
    try {
      const r = await axios.get(`${API}/crm/territories/geocode?postcode=${encodeURIComponent(form.postcode.trim())}`, auth());
      setForm((f) => ({ ...f, lat: String(r.data.lat), lng: String(r.data.lng) }));
      toast.success('Location found from postcode');
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Could not resolve that postcode');
    } finally { setLocating(false); }
  };

  const create = async () => {
    if (!form.name.trim()) { toast.error('Office name required'); return; }
    if ((form.lat === '' || form.lng === '') && !form.postcode.trim()) {
      toast.error('Enter a postcode or latitude/longitude'); return;
    }
    setSaving(true);
    try {
      await axios.post(`${API}/crm/territories/offices`, {
        name: form.name, postcode: form.postcode, address: form.address,
        lat: form.lat, lng: form.lng, colour_hex: form.colour_hex,
      }, auth());
      toast.success('Office added');
      setForm(BLANK);
      setAdding(false);
      onChange();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Could not add office');
    } finally { setSaving(false); }
  };

  const remove = async (o) => {
    if (!window.confirm(`Remove office "${o.name}"?`)) return;
    try {
      await axios.delete(`${API}/crm/territories/offices/${o.id}`, auth());
      toast.success('Office removed');
      onChange();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Could not remove office');
    }
  };

  return (
    <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-3" data-testid="offices-panel">
      <div className="flex items-center justify-between mb-2">
        <p className="text-[10px] uppercase tracking-wider text-zinc-500 font-bold inline-flex items-center gap-1.5">
          <Building2 size={12} /> Offices · {offices.length}
        </p>
        <button
          onClick={() => { setAdding((v) => !v); setForm(BLANK); }}
          className="text-[10px] font-bold text-blue-600 hover:underline inline-flex items-center gap-1"
          data-testid="office-add-toggle"
        >
          {adding ? <><X size={11} /> Cancel</> : <><Plus size={11} /> Add</>}
        </button>
      </div>

      {adding && (
        <div className="space-y-2 mb-3 p-2 rounded-lg border border-zinc-200 dark:border-zinc-800 bg-zinc-50/60 dark:bg-zinc-800/40" data-testid="office-add-form">
          <input value={form.name} onChange={(e) => set('name', e.target.value)} placeholder="Office name" className="w-full px-2 py-1.5 text-sm border border-zinc-200 dark:border-zinc-700 rounded bg-white dark:bg-zinc-900" data-testid="office-name" />
          <input value={form.address} onChange={(e) => set('address', e.target.value)} placeholder="Address (optional)" className="w-full px-2 py-1.5 text-sm border border-zinc-200 dark:border-zinc-700 rounded bg-white dark:bg-zinc-900" data-testid="office-address" />
          <div className="flex gap-2">
            <input value={form.postcode} onChange={(e) => set('postcode', e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); lookupPostcode(); } }} placeholder="Postcode (auto-locates)" className="flex-1 px-2 py-1.5 text-sm border border-zinc-200 dark:border-zinc-700 rounded bg-white dark:bg-zinc-900" data-testid="office-postcode" />
            <button onClick={lookupPostcode} disabled={locating} className="px-2.5 py-1.5 text-xs font-bold border border-zinc-200 dark:border-zinc-700 rounded inline-flex items-center gap-1 hover:bg-zinc-100 dark:hover:bg-zinc-800 disabled:opacity-50" title="Find latitude/longitude from postcode" data-testid="office-geocode">
              <Search size={12} /> {locating ? '…' : 'Find'}
            </button>
          </div>
          <div className="flex gap-2">
            <input value={form.lat} onChange={(e) => set('lat', e.target.value)} placeholder="Latitude" inputMode="decimal" className="w-1/2 px-2 py-1.5 text-sm border border-zinc-200 dark:border-zinc-700 rounded bg-white dark:bg-zinc-900" data-testid="office-lat" />
            <input value={form.lng} onChange={(e) => set('lng', e.target.value)} placeholder="Longitude" inputMode="decimal" className="w-1/2 px-2 py-1.5 text-sm border border-zinc-200 dark:border-zinc-700 rounded bg-white dark:bg-zinc-900" data-testid="office-lng" />
          </div>
          <div className="flex items-center gap-2">
            <input type="color" value={form.colour_hex} onChange={(e) => set('colour_hex', e.target.value)} className="w-7 h-7 rounded border border-zinc-200 dark:border-zinc-700 bg-transparent cursor-pointer" title="Pin colour" data-testid="office-colour" />
            <span className="text-[10px] text-zinc-500 flex-1">Type a postcode &amp; hit Find — or enter coords manually.</span>
            <button onClick={create} disabled={saving} className="px-3 py-1.5 text-xs font-bold text-white rounded disabled:opacity-50" style={{ background: 'var(--color-brand-blue, #2563EB)' }} data-testid="office-save">
              {saving ? 'Saving…' : 'Save'}
            </button>
          </div>
        </div>
      )}

      <div className="space-y-1 max-h-[220px] overflow-y-auto" data-testid="offices-list">
        {offices.length === 0 && <p className="text-xs text-zinc-400 italic py-1">No offices pinned yet.</p>}
        {offices.map((o) => (
          <div key={o.id} className="flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-zinc-50 dark:hover:bg-zinc-800/60" data-testid={`office-row-${o.id}`}>
            <span className="w-3 h-3 rounded-full border border-zinc-300 shrink-0" style={{ backgroundColor: o.colour_hex }} />
            <button onClick={() => focusOffice && focusOffice(o)} className="flex-1 min-w-0 text-left" data-testid={`office-focus-${o.id}`}>
              <span className="block text-sm font-semibold text-zinc-900 dark:text-zinc-100 truncate">{o.name}</span>
              <span className="block text-[10px] text-zinc-500 truncate inline-flex items-center gap-1"><MapPin size={9} /> {o.postcode || `${o.lat}, ${o.lng}`}</span>
            </button>
            <button onClick={() => remove(o)} className="p-1 text-zinc-400 hover:text-rose-600" title="Remove" data-testid={`office-remove-${o.id}`}>
              <Trash2 size={13} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
