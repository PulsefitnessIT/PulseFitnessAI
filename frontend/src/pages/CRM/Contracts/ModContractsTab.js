import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Plus, Trash2, Pencil, Shield, X } from 'lucide-react';

const BASIS_LABEL = { annual: 'per year', per_visit: 'per visit', quoted: 'quoted amount' };
const STATUS = ['draft', 'active', 'expired', 'cancelled'];
const emptyForm = { company_id: '', reference: '', title: 'MOD PTE Service Contract', authority: '', start_date: '', end_date: '', status: 'draft', notes: '', lines: [] };

// MOD aftersales contracts — per-site locations × service type (A / B / C / repairs / refurbishment).
export default function ModContractsTab({ API, headers, c, isDark }) {
  const [rows, setRows] = useState([]);
  const [catalog, setCatalog] = useState([]);
  const [companies, setCompanies] = useState([]);
  const [form, setForm] = useState(null);
  const [editId, setEditId] = useState(null);
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    const [r, cat] = await Promise.all([
      axios.get(`${API}/crm/v2/mod-contracts`, { headers: headers() }),
      axios.get(`${API}/crm/v2/mod-contracts/catalog`, { headers: headers() }),
    ]);
    setRows(r.data.contracts || []); setCatalog(cat.data.service_types || []);
  }, [API, headers]);
  useEffect(() => { load().catch(() => setErr('Could not load MOD contracts')); }, [load]);

  const openForm = async (row) => {
    setErr('');
    if (!companies.length) {
      const r = await axios.get(`${API}/crm/v2/companies?type=mod_site&limit=500`, { headers: headers() });
      setCompanies(r.data.companies || r.data.items || []);
    }
    setEditId(row?.id || null);
    setForm(row ? { ...emptyForm, ...row } : { ...emptyForm });
  };

  const remove = async (id) => {
    if (!window.confirm('Delete this MOD contract?')) return;
    await axios.delete(`${API}/crm/v2/mod-contracts/${id}`, { headers: headers() });
    load();
  };

  const card = { background: isDark ? 'var(--color-surface-dark-1)' : '#fff', border: `1px solid ${c.border}` };
  const label = (k) => catalog.find((x) => x.key === k)?.label || k;

  return (
    <div className="space-y-3" data-testid="mod-contracts-tab">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs" style={{ color: c.textDim }}>Ministry of Defence PTE service contracts — set the service type and price for each location on a site.</p>
        <button onClick={() => openForm(null)} className="px-3 py-1.5 text-xs font-semibold rounded-md bg-[var(--color-info-ios)] text-white" data-testid="mod-contract-new">
          <Plus size={12} className="inline -mt-0.5" /> New MOD contract
        </button>
      </div>
      {err && <p className="text-xs text-red-600" data-testid="mod-contract-error">{err}</p>}
      {!rows.length && <div className="rounded-lg p-6 text-center text-sm" style={{ ...card, color: c.textDim }} data-testid="mod-contracts-empty">No MOD contracts yet.</div>}
      {rows.map((r) => (
        <div key={r.id} className="rounded-lg p-3" style={card} data-testid={`mod-contract-${r.id}`}>
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="text-sm font-semibold" style={{ color: c.text }}><Shield size={13} className="inline -mt-0.5 mr-1 text-emerald-600" />{r.company_name} {r.reference && <span className="font-mono text-xs" style={{ color: c.textDim }}>· {r.reference}</span>}</p>
              <p className="text-[11px]" style={{ color: c.textDim }}>{r.title} · {r.start_date || '—'} → {r.end_date || '—'} · <span className="capitalize">{r.status}</span></p>
            </div>
            <div className="flex items-center gap-1 shrink-0">
              <span className="text-xs font-bold mr-2" style={{ color: c.text }}>£{Number(r.annual_value || 0).toLocaleString('en-GB')}/yr</span>
              <button onClick={() => openForm(r)} className="p-1.5 rounded hover:opacity-70" aria-label="Edit" data-testid={`mod-contract-edit-${r.id}`}><Pencil size={13} /></button>
              <button onClick={() => remove(r.id)} className="p-1.5 rounded hover:opacity-70 text-red-600" aria-label="Delete" data-testid={`mod-contract-delete-${r.id}`}><Trash2 size={13} /></button>
            </div>
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {(r.lines || []).map((ln) => (
              <span key={ln.id} className="text-[10px] px-2 py-0.5 rounded-full" style={{ background: isDark ? 'var(--color-surface-dark-3)' : 'var(--color-neutral-100)', color: c.textMuted }}>
                {ln.location_name}: {label(ln.service_type).split(' — ')[0]} · £{Number(ln.price).toLocaleString('en-GB')} {BASIS_LABEL[ln.price_basis]}
              </span>
            ))}
          </div>
        </div>
      ))}
      {form && <ModContractForm {...{ API, headers, c, isDark, catalog, companies, form, setForm, editId }} onClose={() => setForm(null)} onSaved={() => { setForm(null); load(); }} />}
    </div>
  );
}

function ModContractForm({ API, headers, c, isDark, catalog, companies, form, setForm, editId, onClose, onSaved }) {
  const [locations, setLocations] = useState([]);
  const [linked, setLinked] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  useEffect(() => {
    if (!form.company_id) { setLocations([]); return; }
    axios.get(`${API}/crm/v2/mod-contracts/locations?company_id=${form.company_id}`, { headers: headers() })
      .then((r) => { setLocations(r.data.locations || []); setLinked(r.data.linked); }).catch(() => setLocations([]));
  }, [form.company_id, API, headers]);

  const set = (k, v) => setForm({ ...form, [k]: v });
  const setLine = (i, patch) => set('lines', form.lines.map((l, k) => (k === i ? { ...l, ...patch } : l)));
  const addLine = () => set('lines', [...form.lines, { location_id: '', service_type: 'A', price: '' }]);
  const save = async () => {
    setErr(''); setBusy(true);
    try {
      const body = { ...form, lines: form.lines.map((l) => ({ ...l, price: Number(l.price || 0) })) };
      if (editId) await axios.put(`${API}/crm/v2/mod-contracts/${editId}`, body, { headers: headers() });
      else await axios.post(`${API}/crm/v2/mod-contracts`, body, { headers: headers() });
      onSaved();
    } catch (e) { setErr(e?.response?.data?.detail || 'Could not save the contract'); }
    setBusy(false);
  };
  const input = { background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text };
  const fld = 'w-full mt-1 px-2.5 py-1.5 text-sm rounded-md';
  const lbl = 'text-[10px] uppercase tracking-wider font-medium';

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div className="w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-xl p-5" style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff' }} onClick={(e) => e.stopPropagation()} data-testid="mod-contract-form">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold" style={{ color: c.text }}>{editId ? 'Edit MOD contract' : 'New MOD contract'}</h2>
          <button onClick={onClose} aria-label="Close"><X size={16} /></button>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <label className="col-span-2"><span className={lbl} style={{ color: c.textDim }}>MOD site *</span>
            <select value={form.company_id} disabled={!!editId} onChange={(e) => set('company_id', e.target.value)} className={fld} style={input} data-testid="mod-contract-company">
              <option value="">— Select a MOD site —</option>
              {companies.map((co) => <option key={co.id} value={co.id}>{co.name}</option>)}
            </select>
          </label>
          <label><span className={lbl} style={{ color: c.textDim }}>Contract reference</span><input value={form.reference} onChange={(e) => set('reference', e.target.value)} className={fld} style={input} data-testid="mod-contract-reference" /></label>
          <label><span className={lbl} style={{ color: c.textDim }}>MoD contracting authority</span><input value={form.authority} onChange={(e) => set('authority', e.target.value)} className={fld} style={input} data-testid="mod-contract-authority" /></label>
          <label><span className={lbl} style={{ color: c.textDim }}>Start date</span><input type="date" value={form.start_date} onChange={(e) => set('start_date', e.target.value)} className={fld} style={input} data-testid="mod-contract-start" /></label>
          <label><span className={lbl} style={{ color: c.textDim }}>End date</span><input type="date" value={form.end_date} onChange={(e) => set('end_date', e.target.value)} className={fld} style={input} data-testid="mod-contract-end" /></label>
          <label><span className={lbl} style={{ color: c.textDim }}>Status</span>
            <select value={form.status} onChange={(e) => set('status', e.target.value)} className={fld} style={input} data-testid="mod-contract-status">
              {STATUS.map((st) => <option key={st} value={st}>{st[0].toUpperCase() + st.slice(1)}</option>)}
            </select>
          </label>
        </div>

        <div className="mt-4">
          <div className="flex items-center justify-between">
            <p className={lbl} style={{ color: c.textDim }}>Services by location</p>
            <button onClick={addLine} disabled={!form.company_id} className="text-xs font-semibold disabled:opacity-40" style={{ color: 'var(--color-info-ios)' }} data-testid="mod-contract-add-line"><Plus size={12} className="inline -mt-0.5" /> Add service</button>
          </div>
          {form.company_id && !linked && <p className="text-[11px] mt-1 text-amber-600">This site isn't linked to a MOD portal account yet — services can only cover the whole site.</p>}
          {form.company_id && linked && !locations.length && <p className="text-[11px] mt-1" style={{ color: c.textDim }}>No locations set up yet — add them under the site's Equipment register, or cover the whole site.</p>}
          {form.lines.map((ln, i) => {
            const st = catalog.find((x) => x.key === ln.service_type);
            return (
              <div key={ln.id || i} className="mt-2 p-2.5 rounded-lg" style={{ border: `1px solid ${c.border}` }} data-testid={`mod-contract-line-${i}`}>
                <div className="grid grid-cols-12 gap-2 items-end">
                  <label className="col-span-4"><span className={lbl} style={{ color: c.textDim }}>Location</span>
                    <select value={ln.location_id} onChange={(e) => setLine(i, { location_id: e.target.value })} className={fld} style={input} data-testid={`mod-contract-line-location-${i}`}>
                      <option value="">Whole site</option>
                      {locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
                    </select>
                  </label>
                  <label className="col-span-4"><span className={lbl} style={{ color: c.textDim }}>Service type</span>
                    <select value={ln.service_type} onChange={(e) => setLine(i, { service_type: e.target.value })} className={fld} style={input} data-testid={`mod-contract-line-type-${i}`}>
                      {catalog.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
                    </select>
                  </label>
                  <label className="col-span-3"><span className={lbl} style={{ color: c.textDim }}>£ {BASIS_LABEL[st?.price_basis] || ''}</span>
                    <input type="number" min="0" step="0.01" value={ln.price} onChange={(e) => setLine(i, { price: e.target.value })} className={fld} style={input} data-testid={`mod-contract-line-price-${i}`} />
                  </label>
                  <button onClick={() => set('lines', form.lines.filter((_, k) => k !== i))} className="col-span-1 pb-2 text-red-600" aria-label="Remove service" data-testid={`mod-contract-line-remove-${i}`}><Trash2 size={14} /></button>
                </div>
                {ln.service_type === 'C' && (
                  <label className="mt-1.5 flex items-center gap-1.5 text-xs" style={{ color: c.textMuted }}>
                    <input type="checkbox" checked={!!ln.quarterly_inspections} onChange={(e) => setLine(i, { quarterly_inspections: e.target.checked })} /> Include quarterly inspections
                  </label>
                )}
                {st && <p className="mt-1.5 text-[10px]" style={{ color: c.textDim }}>Includes: {st.includes.join(', ')} · Excludes: {st.excludes.join(', ')}</p>}
              </div>
            );
          })}
        </div>
        <label className="block mt-3"><span className={lbl} style={{ color: c.textDim }}>Notes</span><textarea value={form.notes} onChange={(e) => set('notes', e.target.value)} rows={2} className={fld} style={input} /></label>
        {err && <p className="mt-2 text-xs text-red-600" data-testid="mod-contract-form-error">{typeof err === 'string' ? err : 'Could not save'}</p>}
        <div className="mt-4 flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 text-sm" style={{ color: c.textMuted }}>Cancel</button>
          <button onClick={save} disabled={busy || !form.company_id} className="px-4 py-2 text-sm font-semibold rounded-md bg-[var(--color-info-ios)] text-white disabled:opacity-50" data-testid="mod-contract-save">{busy ? 'Saving…' : 'Save contract'}</button>
        </div>
      </div>
    </div>
  );
}
