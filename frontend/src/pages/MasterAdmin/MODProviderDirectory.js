/**
 * Master Admin — MOD Overseas Service Provider Directory
 *
 * Every registered overseas service provider with contact details and the MOD
 * sites it covers. Providers here can be assigned to sites from the MOD
 * Equipment & Readiness site cards; both Pulse Fitness and the provider are
 * emailed when a job is logged.
 */
import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import {
  Truck, Mail, Phone, User, MapPin, Building2, Loader2, Search,
  AlertCircle, Pencil, CheckCircle2, X, Plus,
} from 'lucide-react';
import { toast } from 'sonner';

const API = process.env.REACT_APP_BACKEND_URL + '/api';
const headers = () => ({ Authorization: `Bearer ${localStorage.getItem('token')}` });

const MODProviderDirectory = () => {
  const [providers, setProviders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState('');
  const [editing, setEditing] = useState(null); // provider being edited / created
  const [form, setForm] = useState({ name: '', email: '', phone: '', contact_name: '', notes: '' });
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/master-admin/mod-estate/provider-directory`, { headers: headers() });
      setProviders(data?.providers || []);
    } catch {
      setProviders([]);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const openEdit = (p) => {
    setEditing(p || { id: null });
    setForm({
      name: p?.name || '', email: p?.email || '', phone: p?.phone || '',
      contact_name: p?.contact_name || '', notes: p?.notes || '',
    });
  };

  const save = async () => {
    if (!form.name.trim()) { toast.error('Provider name is required'); return; }
    setBusy(true);
    try {
      if (editing?.id) {
        await axios.patch(`${API}/master-admin/mod-estate/suppliers/${editing.id}`, {
          name: form.name.trim(), email: form.email.trim(), phone: form.phone.trim(),
          contact_name: form.contact_name.trim(), notes: form.notes.trim(),
        }, { headers: headers() });
        toast.success('Provider updated');
      } else {
        await axios.post(`${API}/master-admin/mod-estate/suppliers`, {
          name: form.name.trim(), email: form.email.trim(), phone: form.phone.trim(),
          contact_name: form.contact_name.trim(), notes: form.notes.trim(),
        }, { headers: headers() });
        toast.success('Provider added to the registry');
      }
      setEditing(null);
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Could not save provider');
    } finally { setBusy(false); }
  };

  const filtered = providers.filter((p) => {
    if (!q.trim()) return true;
    const hay = `${p.name} ${p.email} ${p.contact_name} ${(p.sites || []).map((s) => s.name).join(' ')}`.toLowerCase();
    return hay.includes(q.trim().toLowerCase());
  });

  return (
    <div className="space-y-4" data-testid="mod-provider-directory">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Truck size={18} className="text-cyan-600" />
          <h2 className="text-lg font-extrabold text-zinc-900">Overseas Service Providers</h2>
          <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-zinc-100 text-zinc-600" data-testid="provider-count">{providers.length}</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-400" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search providers or sites…"
              className="pl-8 pr-3 py-2 text-sm rounded-lg border border-zinc-300 focus:border-cyan-400 focus:outline-none w-64"
              data-testid="provider-search" />
          </div>
          <button onClick={() => openEdit(null)} data-testid="provider-add-btn"
            className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-bold rounded-lg bg-cyan-600 text-white hover:bg-cyan-700 transition-colors">
            <Plus size={15} /> Add provider
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-zinc-500 text-sm py-12 justify-center"><Loader2 size={16} className="animate-spin" /> Loading providers…</div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16 text-zinc-500" data-testid="provider-empty">
          <Truck size={30} className="mx-auto mb-3 text-zinc-300" />
          <p className="text-sm font-semibold">No providers yet</p>
          <p className="text-xs mt-1">Add an overseas provider, then assign it to sites from MOD Equipment &amp; Readiness.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {filtered.map((p) => (
            <div key={p.id} className="rounded-xl border border-zinc-200 bg-white p-4" data-testid={`provider-card-${p.id}`}>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="font-bold text-zinc-900 truncate">{p.name}</h3>
                    {!p.allocated && (
                      <span className="inline-flex items-center gap-1 text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200" title="No email — this provider will NOT receive job alerts">
                        <AlertCircle size={10} /> No email
                      </span>
                    )}
                  </div>
                  <div className="mt-1.5 space-y-1 text-sm text-zinc-600">
                    {p.contact_name && <div className="flex items-center gap-1.5"><User size={13} className="text-zinc-400" /> {p.contact_name}</div>}
                    {p.email ? <a href={`mailto:${p.email}`} className="flex items-center gap-1.5 text-cyan-700 hover:underline"><Mail size={13} className="text-zinc-400" /> {p.email}</a>
                      : <div className="flex items-center gap-1.5 text-zinc-400"><Mail size={13} /> No email on file</div>}
                    {p.phone && <a href={`tel:${p.phone}`} className="flex items-center gap-1.5 text-zinc-600 hover:underline"><Phone size={13} className="text-zinc-400" /> {p.phone}</a>}
                    {(p.countries?.length > 0 || p.regions?.length > 0) && (
                      <div className="flex items-center gap-1.5 text-zinc-500"><MapPin size={13} className="text-zinc-400" /> {[...(p.countries || []), ...(p.regions || [])].join(', ')}</div>
                    )}
                  </div>
                </div>
                <button onClick={() => openEdit(p)} data-testid={`provider-edit-${p.id}`}
                  className="shrink-0 inline-flex items-center gap-1 text-xs font-semibold text-zinc-500 hover:text-zinc-900 px-2 py-1 rounded-md border border-zinc-200 hover:border-zinc-300">
                  <Pencil size={12} /> Edit
                </button>
              </div>

              <div className="mt-3 pt-3 border-t border-zinc-100">
                <div className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wide text-zinc-400 mb-1.5">
                  <Building2 size={12} /> Covers {p.site_count} site{p.site_count === 1 ? '' : 's'}
                </div>
                {p.sites.length === 0 ? (
                  <p className="text-xs text-zinc-400">Not assigned to any site yet.</p>
                ) : (
                  <div className="flex flex-wrap gap-1.5" data-testid={`provider-sites-${p.id}`}>
                    {p.sites.map((s) => (
                      <span key={s.id} className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-800 border border-emerald-100">
                        {s.name}
                        {s.force && <span className="text-emerald-500/70 uppercase text-[9px]">{s.force}</span>}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {editing && (
        <div className="fixed inset-0 z-[130] flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.7)' }} data-testid="provider-edit-modal" onClick={() => !busy && setEditing(null)}>
          <div className="bg-white rounded-2xl w-full max-w-md p-5 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Truck size={18} className="text-cyan-600" />
                <h3 className="text-base font-extrabold text-zinc-900">{editing.id ? 'Edit provider' : 'Add provider'}</h3>
              </div>
              <button onClick={() => setEditing(null)} disabled={busy} className="text-zinc-400 hover:text-zinc-700"><X size={18} /></button>
            </div>
            <div className="space-y-2">
              <input value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} placeholder="Provider name *"
                className="w-full px-3 py-2 text-sm rounded-md border border-zinc-300 focus:border-cyan-400 focus:outline-none" data-testid="provider-form-name" autoFocus />
              <input value={form.email} onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))} placeholder="Email (receives job alerts)"
                className="w-full px-3 py-2 text-sm rounded-md border border-zinc-300 focus:border-cyan-400 focus:outline-none" data-testid="provider-form-email" />
              <div className="flex gap-2">
                <input value={form.contact_name} onChange={(e) => setForm((f) => ({ ...f, contact_name: e.target.value }))} placeholder="Contact name"
                  className="w-1/2 px-3 py-2 text-sm rounded-md border border-zinc-300 focus:border-cyan-400 focus:outline-none" data-testid="provider-form-contact" />
                <input value={form.phone} onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))} placeholder="Phone"
                  className="w-1/2 px-3 py-2 text-sm rounded-md border border-zinc-300 focus:border-cyan-400 focus:outline-none" data-testid="provider-form-phone" />
              </div>
              <textarea value={form.notes} onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))} placeholder="Notes (optional)" rows={2}
                className="w-full px-3 py-2 text-sm rounded-md border border-zinc-300 focus:border-cyan-400 focus:outline-none resize-none" data-testid="provider-form-notes" />
            </div>
            <div className="flex justify-end gap-2 mt-4">
              <button onClick={() => setEditing(null)} disabled={busy} className="px-3 py-1.5 text-xs font-semibold text-zinc-600">Cancel</button>
              <button onClick={save} disabled={busy} data-testid="provider-form-save"
                className="px-3 py-1.5 text-xs font-bold rounded-md bg-cyan-600 text-white disabled:opacity-40 inline-flex items-center gap-1.5">
                {busy ? <Loader2 size={13} className="animate-spin" /> : <CheckCircle2 size={13} />} Save
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default MODProviderDirectory;
