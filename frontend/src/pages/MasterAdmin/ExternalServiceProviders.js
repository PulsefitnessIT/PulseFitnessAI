/**
 * Master Admin — External Service Providers (unified)
 *
 * One place to onboard every external company that services MOD / overseas
 * sites: the company itself plus its field engineers, each a real /bfpo
 * portal login. Engineers flagged MOD/BFPO get a territory + site allocation;
 * all get an invite link or a temporary password. Replaces the separate
 * Dealer/Engineer, BFPO-Engineers and Service-Providers flows.
 */
import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import {
  Truck, Mail, Phone, User, MapPin, Building2, Loader2, Search, ShieldCheck,
  Pencil, X, Plus, Trash2, CheckCircle2, Copy, Link2, KeyRound, Wrench, ArrowLeft,
} from 'lucide-react';
import { toast } from 'sonner';

const API = process.env.REACT_APP_BACKEND_URL + '/api';
const headers = () => ({ Authorization: `Bearer ${localStorage.getItem('token')}` });

const emptyEngineer = () => ({
  full_name: '', email: '', phone: '', mod_bfpo: 'inherit',
  territory_ids: [], site_ids: [], password_mode: 'invite', temp_password: '',
});

const inputCls = 'w-full px-3 py-2 text-sm rounded-lg border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-cyan-500/30 focus:border-cyan-400';
const labelCls = 'text-[11px] font-semibold uppercase tracking-wide text-slate-500';

const ExternalServiceProviders = () => {
  const [providers, setProviders] = useState([]);
  const [territories, setTerritories] = useState([]);
  const [sites, setSites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState('');
  const [view, setView] = useState('list'); // 'list' | 'form'
  const [editing, setEditing] = useState(null); // provider being edited (null = new)
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  const [company, setCompany] = useState({ name: '', contact_name: '', email: '', phone: '', country: '', notes: '', mod_bfpo_default: 'yes' });
  const [engineers, setEngineers] = useState([]);
  const [existingEngs, setExistingEngs] = useState([]);
  const [rowBusy, setRowBusy] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [p, t, s] = await Promise.all([
        axios.get(`${API}/master-admin/mod-estate/external-providers`, { headers: headers() }),
        axios.get(`${API}/master-admin/mod-estate/bfpo-territories`, { headers: headers() }),
        axios.get(`${API}/master-admin/mod-estate/bfpo-sites`, { headers: headers() }),
      ]);
      setProviders(p.data?.providers || []);
      setTerritories(t.data?.territories || []);
      setSites(s.data?.sites || []);
    } catch {
      setProviders([]);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const openNew = () => {
    setEditing(null); setResult(null);
    setCompany({ name: '', contact_name: '', email: '', phone: '', country: '', notes: '', mod_bfpo_default: 'yes' });
    setEngineers([emptyEngineer()]);
    setExistingEngs([]);
    setView('form');
  };
  const openEdit = (p) => {
    setEditing(p); setResult(null);
    setCompany({
      name: p.name || '', contact_name: p.contact_name || '', email: p.email || '',
      phone: p.phone || '', country: (p.countries || [])[0] || '', notes: p.notes || '',
      mod_bfpo_default: p.is_mod_bfpo ? 'yes' : 'yes',
    });
    setEngineers([]); // only ADD new engineers while editing
    setExistingEngs((p.engineers || []).map((e) => ({
      id: e.id, full_name: e.full_name || '', email: e.email || '', phone: e.phone || '',
      mod_bfpo: e.is_mod_bfpo ? 'yes' : 'no',
      territory_ids: e.territory_ids || [], site_ids: e.site_ids || [],
      login_status: e.login_status,
    })));
    setView('form');
  };
  const backToList = () => { setView('list'); setResult(null); load(); };

  const setEng = (i, k, v) => setEngineers((arr) => arr.map((e, idx) => (idx === i ? { ...e, [k]: v } : e)));
  const addEng = () => setEngineers((arr) => [...arr, emptyEngineer()]);
  const removeEng = (i) => setEngineers((arr) => arr.filter((_, idx) => idx !== i));

  const setExist = (i, k, v) => setExistingEngs((arr) => arr.map((e, idx) => (idx === i ? { ...e, [k]: v } : e)));
  const saveExisting = async (i) => {
    const e = existingEngs[i];
    if (!e.full_name.trim()) return toast.error('Full name is required');
    setRowBusy(e.id);
    try {
      await axios.patch(`${API}/master-admin/mod-estate/external-providers/${editing.id}/engineers/${e.id}`, {
        full_name: e.full_name, phone: e.phone, mod_bfpo: e.mod_bfpo,
        territory_ids: e.territory_ids, site_ids: e.site_ids,
      }, { headers: headers() });
      toast.success(`${e.full_name} updated`);
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Could not update engineer');
    } finally { setRowBusy(null); }
  };
  const removeExisting = async (i) => {
    const e = existingEngs[i];
    if (!window.confirm(`Remove ${e.full_name}? This deletes their MOD portal login.`)) return;
    setRowBusy(e.id);
    try {
      await axios.delete(`${API}/master-admin/mod-estate/external-providers/${editing.id}/engineers/${e.id}`, { headers: headers() });
      toast.success(`${e.full_name} removed`);
      setExistingEngs((arr) => arr.filter((_, idx) => idx !== i));
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Could not remove engineer');
    } finally { setRowBusy(null); }
  };

  const renderTerrSites = (eng, onField, idPrefix) => {
    const selTerr = (eng.territory_ids || [])[0] || '';
    const terrSites = sites.filter((s) => s.territory_id === selTerr);
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 rounded-lg bg-cyan-50/40 border border-cyan-100 p-3">
        <label className="block"><span className={labelCls}>Territory</span>
          <select className={`mt-1 ${inputCls}`} value={selTerr} onChange={(ev) => { onField('territory_ids', ev.target.value ? [ev.target.value] : []); onField('site_ids', []); }} data-testid={`${idPrefix}-territory`}>
            <option value="">Select territory…</option>
            {territories.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
        </label>
        <div className="block">
          <span className={labelCls}>Sites {selTerr && `(${terrSites.length})`}</span>
          <div className="mt-1 max-h-32 overflow-auto rounded-lg border border-slate-200 bg-white p-2 space-y-1" data-testid={`${idPrefix}-sites`}>
            {!selTerr && <p className="text-[11px] text-slate-400">Pick a territory first.</p>}
            {selTerr && terrSites.length === 0 && <p className="text-[11px] text-slate-400">No sites in this territory.</p>}
            {terrSites.map((s) => {
              const on = (eng.site_ids || []).includes(s.id);
              return (
                <label key={s.id} className="flex items-center gap-2 text-[13px] text-slate-700 cursor-pointer">
                  <input type="checkbox" checked={on} className="accent-cyan-500"
                    onChange={(ev) => onField('site_ids', ev.target.checked ? [...(eng.site_ids || []), s.id] : (eng.site_ids || []).filter((x) => x !== s.id))}
                    data-testid={`${idPrefix}-site-${s.id}`} />
                  {s.name}
                </label>
              );
            })}
          </div>
        </div>
      </div>
    );
  };

  const copy = (txt) => { navigator.clipboard?.writeText(txt); toast.success('Copied'); };

  const submit = async () => {
    if (!company.name.trim()) return toast.error('Provider company name is required');
    for (const [i, e] of engineers.entries()) {
      if (!e.full_name.trim() || !e.email.trim()) return toast.error(`Engineer ${i + 1}: name and email are required`);
    }
    setBusy(true);
    try {
      const payload = { ...company, engineers };
      let data;
      if (editing?.id) {
        ({ data } = await axios.patch(`${API}/master-admin/mod-estate/external-providers/${editing.id}`, payload, { headers: headers() }));
        toast.success('Provider updated');
      } else {
        ({ data } = await axios.post(`${API}/master-admin/mod-estate/external-providers`, payload, { headers: headers() }));
        toast.success(`Provider "${company.name}" onboarded`);
      }
      if ((data.engineers || []).length > 0) setResult(data);
      else backToList();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Could not save provider');
    } finally { setBusy(false); }
  };

  const filtered = providers.filter((p) => {
    if (!q.trim()) return true;
    const hay = `${p.name} ${p.email} ${p.contact_name} ${(p.engineers || []).map((e) => e.full_name + e.email).join(' ')} ${(p.sites || []).map((s) => s.name).join(' ')}`.toLowerCase();
    return hay.includes(q.trim().toLowerCase());
  });

  /* ── Success screen ─────────────────────────────────────────────── */
  if (view === 'form' && result) {
    const Cred = ({ acc }) => (
      <div className="rounded-lg border border-slate-200 p-3 bg-slate-50" data-testid={`esp-result-${acc.email}`}>
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0">
            <div className="text-sm font-semibold text-slate-800 truncate">{acc.full_name}
              {acc.is_mod_bfpo && <span className="ml-2 text-[10px] font-bold uppercase px-1.5 py-0.5 rounded-full bg-cyan-100 text-cyan-700">MOD/BFPO</span>}
            </div>
            <div className="text-[12px] text-slate-500 truncate">{acc.email}</div>
          </div>
          <span className={`text-[10px] font-bold uppercase px-2 py-1 rounded-full flex items-center gap-1 ${acc.mode === 'invite' ? 'bg-cyan-100 text-cyan-700' : 'bg-amber-100 text-amber-700'}`}>
            {acc.mode === 'invite' ? <Link2 size={11} /> : <KeyRound size={11} />}
            {acc.mode === 'invite' ? 'Invite link' : 'Temp password'}
          </span>
        </div>
        {acc.mode === 'invite' ? (
          <div className="mt-2 flex items-center gap-2">
            <input readOnly value={acc.invite_url} className="flex-1 text-[11px] font-mono px-2 py-1.5 rounded border border-slate-200 bg-white truncate" data-testid={`esp-invite-${acc.email}`} />
            <button onClick={() => copy(acc.invite_url)} className="p-1.5 rounded border border-slate-200 hover:bg-white"><Copy size={13} /></button>
          </div>
        ) : (
          <div className="mt-2 flex items-center gap-2">
            <code className="flex-1 text-[12px] font-mono px-2 py-1.5 rounded border border-slate-200 bg-white" data-testid={`esp-password-${acc.email}`}>{acc.temp_password}</code>
            <button onClick={() => copy(acc.temp_password)} className="p-1.5 rounded border border-slate-200 hover:bg-white"><Copy size={13} /></button>
          </div>
        )}
      </div>
    );
    return (
      <div className="max-w-2xl space-y-4" data-testid="esp-result-screen">
        <div className="flex items-center gap-2 text-emerald-600">
          <CheckCircle2 size={20} />
          <h3 className="text-base font-bold text-slate-900">Engineer logins created</h3>
        </div>
        <p className="text-sm text-slate-600">Share the credentials below. MOD/BFPO engineers can sign in to the MOD portal straight away.</p>
        <div className="space-y-2">{(result.engineers || []).map((e) => <Cred key={e.id} acc={e} />)}</div>
        <button onClick={backToList} className="mt-2 px-4 py-2 rounded-lg bg-cyan-500 text-white text-sm font-semibold hover:bg-cyan-600" data-testid="esp-back-to-list">
          Back to providers
        </button>
      </div>
    );
  }

  /* ── Add / Edit form ────────────────────────────────────────────── */
  if (view === 'form') {
    return (
      <div className="max-w-3xl space-y-5" data-testid="esp-form">
        <button onClick={() => setView('list')} className="inline-flex items-center gap-1.5 text-sm font-semibold text-slate-500 hover:text-slate-900" data-testid="esp-form-back">
          <ArrowLeft size={15} /> Back to providers
        </button>

        {/* Company */}
        <section className="rounded-xl border border-slate-200 p-4 space-y-4">
          <div className="flex items-center gap-2 text-slate-800"><Building2 size={16} className="text-cyan-500" /><h3 className="text-sm font-bold">Service provider company</h3></div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className="block"><span className={labelCls}>Company name *</span><input className={`mt-1 ${inputCls}`} value={company.name} onChange={(e) => setCompany((c) => ({ ...c, name: e.target.value }))} data-testid="esp-company-name" autoFocus /></label>
            <label className="block"><span className={labelCls}>Contact name</span><input className={`mt-1 ${inputCls}`} value={company.contact_name} onChange={(e) => setCompany((c) => ({ ...c, contact_name: e.target.value }))} data-testid="esp-company-contact" /></label>
            <label className="block"><span className={labelCls}>Email (job alerts)</span><input className={`mt-1 ${inputCls}`} value={company.email} onChange={(e) => setCompany((c) => ({ ...c, email: e.target.value }))} data-testid="esp-company-email" /></label>
            <label className="block"><span className={labelCls}>Phone</span><input className={`mt-1 ${inputCls}`} value={company.phone} onChange={(e) => setCompany((c) => ({ ...c, phone: e.target.value }))} data-testid="esp-company-phone" /></label>
            <label className="block"><span className={labelCls}>Country</span><input className={`mt-1 ${inputCls}`} value={company.country} onChange={(e) => setCompany((c) => ({ ...c, country: e.target.value }))} placeholder="e.g. Kenya" data-testid="esp-company-country" /></label>
            <label className="block"><span className={labelCls}>MOD / BFPO default</span>
              <select className={`mt-1 ${inputCls}`} value={company.mod_bfpo_default} onChange={(e) => setCompany((c) => ({ ...c, mod_bfpo_default: e.target.value }))} data-testid="esp-company-mod-default">
                <option value="yes">Yes — MOD/BFPO service provider</option>
                <option value="no">No — directory only</option>
              </select>
            </label>
          </div>
          <label className="block"><span className={labelCls}>Notes</span><textarea rows={2} className={`mt-1 ${inputCls} resize-none`} value={company.notes} onChange={(e) => setCompany((c) => ({ ...c, notes: e.target.value }))} data-testid="esp-company-notes" /></label>
          {editing && <p className="text-[11px] text-slate-400">Editing <strong>{editing.name}</strong>. Existing engineers are unchanged — add new engineer logins below.</p>}
        </section>

        {/* Current engineers (edit / remove) */}
        {editing && existingEngs.length > 0 && (
          <section className="rounded-xl border border-slate-200 p-4 space-y-4" data-testid="esp-existing-engineers">
            <div className="flex items-center gap-2 text-slate-800"><Wrench size={16} className="text-cyan-500" /><h3 className="text-sm font-bold">Current engineers</h3></div>
            {existingEngs.map((e, i) => (
              <div key={e.id} className="rounded-lg border border-slate-200 p-3 space-y-3 bg-white" data-testid={`esp-existing-row-${i}`}>
                <div className="flex items-center justify-between gap-2">
                  <span className={labelCls}>{e.email}
                    <span className={`ml-2 ${e.login_status === 'active' ? 'text-emerald-600' : e.login_status === 'invite_pending' ? 'text-cyan-600' : 'text-amber-600'}`}>
                      {e.login_status === 'active' ? 'Active' : e.login_status === 'invite_pending' ? 'Invite sent' : 'Temp pw'}
                    </span>
                  </span>
                  <button onClick={() => removeExisting(i)} disabled={rowBusy === e.id} className="inline-flex items-center gap-1 text-[11px] font-semibold text-red-500 hover:text-red-700 disabled:opacity-50" data-testid={`esp-existing-remove-${i}`}>
                    <Trash2 size={13} /> Remove
                  </button>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <label className="block"><span className={labelCls}>Full name *</span><input className={`mt-1 ${inputCls}`} value={e.full_name} onChange={(ev) => setExist(i, 'full_name', ev.target.value)} data-testid={`esp-existing-name-${i}`} /></label>
                  <label className="block"><span className={labelCls}>Phone</span><input className={`mt-1 ${inputCls}`} value={e.phone} onChange={(ev) => setExist(i, 'phone', ev.target.value)} data-testid={`esp-existing-phone-${i}`} /></label>
                  <label className="block"><span className={labelCls}>MOD / BFPO</span>
                    <select className={`mt-1 ${inputCls}`} value={e.mod_bfpo} onChange={(ev) => setExist(i, 'mod_bfpo', ev.target.value)} data-testid={`esp-existing-mod-${i}`}>
                      <option value="yes">Yes — MOD/BFPO</option>
                      <option value="no">No</option>
                    </select>
                  </label>
                </div>
                {e.mod_bfpo === 'yes' && renderTerrSites(e, (k, v) => setExist(i, k, v), `esp-existing-${i}`)}
                <div className="flex justify-end">
                  <button onClick={() => saveExisting(i)} disabled={rowBusy === e.id} className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-bold rounded-lg bg-cyan-500 text-white hover:bg-cyan-600 disabled:opacity-50" data-testid={`esp-existing-save-${i}`}>
                    {rowBusy === e.id ? <Loader2 size={13} className="animate-spin" /> : <CheckCircle2 size={13} />} Save changes
                  </button>
                </div>
              </div>
            ))}
          </section>
        )}

        {/* Engineers */}
        <section className="rounded-xl border border-slate-200 p-4 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-slate-800"><Wrench size={16} className="text-cyan-500" /><h3 className="text-sm font-bold">Engineers {editing && <span className="text-slate-400 font-normal">(add new)</span>}</h3></div>
            <button onClick={addEng} className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-cyan-200 text-cyan-700 hover:bg-cyan-50" data-testid="esp-add-engineer"><Plus size={14} /> Add engineer</button>
          </div>
          {engineers.length === 0 && <p className="text-[12px] text-slate-400">No engineers added yet.</p>}
          {engineers.map((e, i) => {
            const effectiveMod = e.mod_bfpo === 'inherit' ? company.mod_bfpo_default === 'yes' : e.mod_bfpo === 'yes';
            const selTerr = (e.territory_ids || [])[0] || '';
            const terrSites = sites.filter((s) => s.territory_id === selTerr);
            return (
              <div key={i} className="rounded-lg border border-slate-200 p-3 space-y-3 bg-slate-50/50" data-testid={`esp-engineer-row-${i}`}>
                <div className="flex items-center justify-between">
                  <span className={labelCls}>Engineer {i + 1}</span>
                  <button onClick={() => removeEng(i)} className="p-1 text-slate-400 hover:text-red-500" data-testid={`esp-remove-engineer-${i}`}><Trash2 size={14} /></button>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <label className="block"><span className={labelCls}>Full name *</span><input className={`mt-1 ${inputCls}`} value={e.full_name} onChange={(ev) => setEng(i, 'full_name', ev.target.value)} data-testid={`esp-engineer-name-${i}`} /></label>
                  <label className="block"><span className={labelCls}>Email *</span><input className={`mt-1 ${inputCls}`} value={e.email} onChange={(ev) => setEng(i, 'email', ev.target.value)} data-testid={`esp-engineer-email-${i}`} /></label>
                  <label className="block"><span className={labelCls}>Phone</span><input className={`mt-1 ${inputCls}`} value={e.phone} onChange={(ev) => setEng(i, 'phone', ev.target.value)} data-testid={`esp-engineer-phone-${i}`} /></label>
                  <label className="block"><span className={labelCls}>MOD / BFPO</span>
                    <select className={`mt-1 ${inputCls}`} value={e.mod_bfpo} onChange={(ev) => setEng(i, 'mod_bfpo', ev.target.value)} data-testid={`esp-engineer-mod-${i}`}>
                      <option value="inherit">Use company default ({company.mod_bfpo_default === 'yes' ? 'MOD/BFPO' : 'Directory only'})</option>
                      <option value="yes">Yes — MOD/BFPO</option>
                      <option value="no">No</option>
                    </select>
                  </label>
                </div>
                {effectiveMod && (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 rounded-lg bg-cyan-50/40 border border-cyan-100 p-3">
                    <label className="block"><span className={labelCls}>Territory</span>
                      <select className={`mt-1 ${inputCls}`} value={selTerr} onChange={(ev) => { setEng(i, 'territory_ids', ev.target.value ? [ev.target.value] : []); setEng(i, 'site_ids', []); }} data-testid={`esp-engineer-territory-${i}`}>
                        <option value="">Select territory…</option>
                        {territories.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                      </select>
                    </label>
                    <div className="block">
                      <span className={labelCls}>Sites {selTerr && `(${terrSites.length})`}</span>
                      <div className="mt-1 max-h-32 overflow-auto rounded-lg border border-slate-200 bg-white p-2 space-y-1" data-testid={`esp-engineer-sites-${i}`}>
                        {!selTerr && <p className="text-[11px] text-slate-400">Pick a territory first.</p>}
                        {selTerr && terrSites.length === 0 && <p className="text-[11px] text-slate-400">No sites in this territory.</p>}
                        {terrSites.map((s) => {
                          const on = (e.site_ids || []).includes(s.id);
                          return (
                            <label key={s.id} className="flex items-center gap-2 text-[13px] text-slate-700 cursor-pointer">
                              <input type="checkbox" checked={on} className="accent-cyan-500"
                                onChange={(ev) => setEng(i, 'site_ids', ev.target.checked ? [...(e.site_ids || []), s.id] : (e.site_ids || []).filter((x) => x !== s.id))}
                                data-testid={`esp-engineer-site-${i}-${s.id}`} />
                              {s.name}
                            </label>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                )}
                <div className="flex flex-wrap items-center gap-4 text-sm">
                  <label className="flex items-center gap-2 cursor-pointer"><input type="radio" checked={e.password_mode === 'invite'} onChange={() => setEng(i, 'password_mode', 'invite')} data-testid={`esp-engineer-invite-${i}`} /> Invite link</label>
                  <label className="flex items-center gap-2 cursor-pointer"><input type="radio" checked={e.password_mode === 'temp'} onChange={() => setEng(i, 'password_mode', 'temp')} data-testid={`esp-engineer-temp-${i}`} /> Temp password</label>
                  {e.password_mode === 'temp' && <input className={`${inputCls} flex-1 min-w-[180px]`} placeholder="Auto-generate if blank" value={e.temp_password} onChange={(ev) => setEng(i, 'temp_password', ev.target.value)} data-testid={`esp-engineer-temp-pw-${i}`} />}
                </div>
              </div>
            );
          })}
        </section>

        <div className="flex items-center gap-3">
          <button onClick={submit} disabled={busy} className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-cyan-500 text-white text-sm font-bold hover:bg-cyan-600 disabled:opacity-60" data-testid="esp-submit">
            {busy ? <Loader2 size={15} className="animate-spin" /> : <CheckCircle2 size={15} />}
            {editing ? 'Save provider' : 'Onboard provider'}
          </button>
          <span className="text-[12px] text-slate-400">{editing ? 'Updates the company' : 'Creates the provider company'}{engineers.length ? ` + ${engineers.length} engineer login(s)` : ''}.</span>
        </div>
      </div>
    );
  }

  /* ── List ───────────────────────────────────────────────────────── */
  return (
    <div className="space-y-4" data-testid="external-service-providers">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Truck size={18} className="text-cyan-600" />
          <h2 className="text-lg font-extrabold text-zinc-900">External Service Providers</h2>
          <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-zinc-100 text-zinc-600" data-testid="esp-count">{providers.length}</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-400" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search providers, engineers or sites…" className="pl-8 pr-3 py-2 text-sm rounded-lg border border-zinc-300 focus:border-cyan-400 focus:outline-none w-72" data-testid="esp-search" />
          </div>
          <button onClick={openNew} data-testid="esp-add-btn" className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-bold rounded-lg bg-cyan-600 text-white hover:bg-cyan-700"><Plus size={15} /> Add provider</button>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-zinc-500 text-sm py-12 justify-center"><Loader2 size={16} className="animate-spin" /> Loading providers…</div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16 text-zinc-500" data-testid="esp-empty">
          <Truck size={30} className="mx-auto mb-3 text-zinc-300" />
          <p className="text-sm font-semibold">No service providers yet</p>
          <p className="text-xs mt-1">Add an external provider with its field engineers — each gets a MOD portal login.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {filtered.map((p) => (
            <div key={p.id} className="rounded-xl border border-zinc-200 bg-white p-4" data-testid={`esp-card-${p.id}`}>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="font-bold text-zinc-900 truncate">{p.name}</h3>
                    {p.is_mod_bfpo && <span className="inline-flex items-center gap-1 text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-cyan-50 text-cyan-700 border border-cyan-200"><ShieldCheck size={10} /> MOD/BFPO</span>}
                  </div>
                  <div className="mt-1.5 space-y-1 text-sm text-zinc-600">
                    {p.contact_name && <div className="flex items-center gap-1.5"><User size={13} className="text-zinc-400" /> {p.contact_name}</div>}
                    {p.email ? <a href={`mailto:${p.email}`} className="flex items-center gap-1.5 text-cyan-700 hover:underline"><Mail size={13} className="text-zinc-400" /> {p.email}</a> : <div className="flex items-center gap-1.5 text-zinc-400"><Mail size={13} /> No email on file</div>}
                    {p.phone && <a href={`tel:${p.phone}`} className="flex items-center gap-1.5 text-zinc-600 hover:underline"><Phone size={13} className="text-zinc-400" /> {p.phone}</a>}
                    {(p.countries?.length > 0) && <div className="flex items-center gap-1.5 text-zinc-500"><MapPin size={13} className="text-zinc-400" /> {p.countries.join(', ')}</div>}
                  </div>
                </div>
                <button onClick={() => openEdit(p)} data-testid={`esp-edit-${p.id}`} className="shrink-0 inline-flex items-center gap-1 text-xs font-semibold text-zinc-500 hover:text-zinc-900 px-2 py-1 rounded-md border border-zinc-200 hover:border-zinc-300"><Pencil size={12} /> Edit</button>
              </div>

              {/* Engineers */}
              <div className="mt-3 pt-3 border-t border-zinc-100">
                <div className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wide text-zinc-400 mb-1.5"><Wrench size={12} /> {p.engineer_count} engineer{p.engineer_count === 1 ? '' : 's'}</div>
                {(p.engineers || []).length === 0 ? <p className="text-xs text-zinc-400">No engineer logins yet.</p> : (
                  <div className="space-y-1.5" data-testid={`esp-card-engineers-${p.id}`}>
                    {p.engineers.map((e) => (
                      <div key={e.id} className="flex items-center justify-between gap-2 text-[13px]">
                        <div className="min-w-0 flex items-center gap-1.5">
                          <span className="font-semibold text-zinc-800 truncate">{e.full_name}</span>
                          {e.territory_names?.length > 0 && <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-100 whitespace-nowrap">{e.territory_names.join(', ')}</span>}
                        </div>
                        <span className={`text-[10px] font-bold uppercase whitespace-nowrap ${e.login_status === 'active' ? 'text-emerald-600' : e.login_status === 'invite_pending' ? 'text-cyan-600' : 'text-amber-600'}`}>
                          {e.login_status === 'active' ? 'Active' : e.login_status === 'invite_pending' ? 'Invite sent' : 'Temp pw'}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Covered sites */}
              <div className="mt-3 pt-3 border-t border-zinc-100">
                <div className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wide text-zinc-400 mb-1.5"><Building2 size={12} /> Covers {(p.sites || []).length} site{(p.sites || []).length === 1 ? '' : 's'}</div>
                {(p.sites || []).length === 0 ? <p className="text-xs text-zinc-400">No sites assigned yet.</p> : (
                  <div className="flex flex-wrap gap-1.5" data-testid={`esp-card-sites-${p.id}`}>
                    {p.sites.map((s) => <span key={s.id} className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-800 border border-emerald-100">{s.name}</span>)}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default ExternalServiceProviders;
