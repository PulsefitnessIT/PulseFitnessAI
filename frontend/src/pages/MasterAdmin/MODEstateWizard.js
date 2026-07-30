/**
 * Master Admin — MOD Estate Setup wizard.
 *
 * Model (founder decision): Army / RAF / Navy are three INDEPENDENT service
 * HQs sharing one estate id (so we report on the MOD as a whole). Sites are
 * global (country + region); overseas sites get one external service supplier
 * from an estate-level registry — Pulse Fitness is always notified of faults.
 *
 * Orchestrates (does not replace) the existing CSV bulk importer.
 */
import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import {
  ShieldCheck, Building2, Truck, MapPin, Plus, CheckCircle2, Loader2,
  Copy, Globe2, Flag, Wrench, RefreshCw, KeyRound,
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL + '/api';
const ESTATE_ID = 'uk-mod';

const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } });
const errMsg = (e, f) => {
  const d = e?.response?.data?.detail;
  return typeof d === 'string' ? d : f;
};
const inputCls =
  'mt-1 w-full px-3 py-2 text-sm rounded-lg border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-cyan-500/30 focus:border-cyan-400';

const Field = ({ label, required, children }) => (
  <label className="block">
    <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
      {label}{required && <span className="text-red-500"> *</span>}
    </span>
    {children}
  </label>
);

const SERVICE_META = {
  army: { label: 'British Army', color: 'text-emerald-700 bg-emerald-50 border-emerald-200' },
  raf: { label: 'Royal Air Force', color: 'text-sky-700 bg-sky-50 border-sky-200' },
  navy: { label: 'Royal Navy', color: 'text-indigo-700 bg-indigo-50 border-indigo-200' },
};

const Kpi = ({ icon: Icon, label, value, accent = 'text-cyan-600' }) => (
  <div className="rounded-xl border border-slate-200 p-4 bg-white">
    <div className="flex items-center gap-2 text-slate-400 text-[11px] font-semibold uppercase tracking-wide">
      <Icon size={13} className={accent} /> {label}
    </div>
    <div className="mt-1 text-2xl font-extrabold text-slate-900">{value}</div>
  </div>
);

const MODEstateWizard = () => {
  const [overview, setOverview] = useState(null);
  const [suppliers, setSuppliers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [ensuring, setEnsuring] = useState(false);

  const load = useCallback(async () => {
    try {
      const [ov, sup] = await Promise.all([
        axios.get(`${API}/master-admin/mod-estate/overview?estate_id=${ESTATE_ID}`, auth()),
        axios.get(`${API}/master-admin/mod-estate/suppliers?estate_id=${ESTATE_ID}`, auth()),
      ]);
      setOverview(ov.data);
      setSuppliers(sup.data.suppliers || []);
    } catch (e) {
      toast.error(errMsg(e, 'Could not load MOD estate'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const ensureHqs = async () => {
    setEnsuring(true);
    try {
      const { data } = await axios.post(`${API}/master-admin/mod-estate/hqs`,
        { estate_id: ESTATE_ID }, auth());
      const created = data.hqs.filter((h) => h.created).length;
      toast.success(created ? `${created} service HQ(s) created` : 'All service HQs already set up');
      await load();
    } catch (e) {
      toast.error(errMsg(e, 'Could not set up HQs'));
    } finally {
      setEnsuring(false);
    }
  };

  if (loading) {
    return <div className="flex items-center gap-2 text-slate-500 text-sm p-6"><Loader2 size={16} className="animate-spin" /> Loading MOD estate…</div>;
  }

  const t = overview?.totals || {};
  const hqsReady = overview?.hqs_ready;

  return (
    <div className="max-w-4xl space-y-6" data-testid="mod-estate-wizard">
      {/* Whole-of-MOD reporting */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2 text-slate-800">
            <ShieldCheck size={16} className="text-cyan-500" />
            <h3 className="text-sm font-bold">MOD estate — whole-of-MOD view</h3>
          </div>
          <button onClick={load} className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-800" data-testid="mod-estate-refresh">
            <RefreshCw size={12} /> Refresh
          </button>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
          <Kpi icon={MapPin} label="Total sites" value={t.sites ?? 0} />
          <Kpi icon={Flag} label="UK sites" value={t.uk_sites ?? 0} accent="text-emerald-600" />
          <Kpi icon={Globe2} label="Overseas" value={t.overseas_sites ?? 0} accent="text-indigo-600" />
          <Kpi icon={Truck} label="Suppliers" value={t.suppliers ?? 0} accent="text-amber-600" />
          <Kpi icon={Wrench} label="Open faults" value={t.open_faults ?? 0} accent="text-rose-600" />
        </div>
        {overview?.per_service && (
          <div className="mt-3 grid grid-cols-1 sm:grid-cols-3 gap-3">
            {overview.per_service.map((s) => (
              <div key={s.force} className={`rounded-lg border p-3 ${SERVICE_META[s.force]?.color || 'border-slate-200'}`} data-testid={`mod-estate-service-${s.force}`}>
                <div className="text-xs font-bold">{s.label}</div>
                <div className="text-[12px] mt-0.5 opacity-80">{s.total} site(s) · {s.uk} UK · {s.overseas} overseas</div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Step 1 — Sections / HQs */}
      <section className="rounded-xl border border-slate-200 p-4">
        <div className="flex items-center gap-2 text-slate-800 mb-2">
          <Building2 size={16} className="text-cyan-500" />
          <h3 className="text-sm font-bold">1 · Service Head Offices</h3>
        </div>
        <p className="text-[12px] text-slate-500 mb-3">
          Army, RAF and Navy are set up as three independent Head Offices sharing one MOD estate for reporting.
        </p>
        {hqsReady ? (
          <div className="flex flex-wrap gap-2" data-testid="mod-estate-hqs-ready">
            {overview.hqs.map((h) => (
              <span key={h.force} className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
                <CheckCircle2 size={13} /> {SERVICE_META[h.force]?.label || h.force} HQ
              </span>
            ))}
          </div>
        ) : (
          <button onClick={ensureHqs} disabled={ensuring} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-cyan-500 text-white text-sm font-bold hover:bg-cyan-600 disabled:opacity-60" data-testid="mod-estate-ensure-hqs">
            {ensuring ? <Loader2 size={15} className="animate-spin" /> : <Plus size={15} />}
            Set up the three service Head Offices
          </button>
        )}
      </section>

      {/* Step 2 — Suppliers */}
      <SupplierRegistry suppliers={suppliers} onAdded={load} />

      {/* Step 3 — Add site */}
      <AddSite hqsReady={hqsReady} suppliers={suppliers} onCreated={load} />
    </div>
  );
};

/* ── Supplier registry ─────────────────────────────────────────────── */
const SupplierRegistry = ({ suppliers, onAdded }) => {
  const blank = { name: '', contact_name: '', email: '', phone: '', countries: '', regions: '' };
  const [form, setForm] = useState(blank);
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async () => {
    if (!form.name.trim()) return toast.error('Supplier name is required');
    setBusy(true);
    try {
      await axios.post(`${API}/master-admin/mod-estate/suppliers`, {
        estate_id: ESTATE_ID,
        name: form.name, contact_name: form.contact_name, email: form.email, phone: form.phone,
        countries: form.countries.split(',').map((s) => s.trim()).filter(Boolean),
        regions: form.regions.split(',').map((s) => s.trim()).filter(Boolean),
      }, auth());
      toast.success(`Added supplier "${form.name}"`);
      setForm(blank);
      onAdded();
    } catch (e) {
      toast.error(errMsg(e, 'Could not add supplier'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="rounded-xl border border-slate-200 p-4 space-y-3" data-testid="mod-estate-suppliers">
      <div className="flex items-center gap-2 text-slate-800">
        <Truck size={16} className="text-cyan-500" />
        <h3 className="text-sm font-bold">2 · External service suppliers <span className="text-slate-400 font-normal">(overseas)</span></h3>
      </div>
      <p className="text-[12px] text-slate-500">
        Register the companies that service overseas bases. UK bases are serviced by Pulse Fitness — no supplier needed.
      </p>
      {suppliers.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {suppliers.map((s) => (
            <span key={s.id} className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full bg-slate-50 text-slate-700 border border-slate-200" data-testid={`mod-estate-supplier-${s.id}`}>
              <Truck size={12} className="text-amber-600" /> {s.name}
              {s.countries?.length ? <span className="text-slate-400">· {s.countries.join(', ')}</span> : null}
            </span>
          ))}
        </div>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Field label="Supplier name" required><input className={inputCls} value={form.name} onChange={(e) => set('name', e.target.value)} data-testid="mod-supplier-name" /></Field>
        <Field label="Contact name"><input className={inputCls} value={form.contact_name} onChange={(e) => set('contact_name', e.target.value)} /></Field>
        <Field label="Email"><input className={inputCls} value={form.email} onChange={(e) => set('email', e.target.value)} data-testid="mod-supplier-email" /></Field>
        <Field label="Phone"><input className={inputCls} value={form.phone} onChange={(e) => set('phone', e.target.value)} /></Field>
        <Field label="Countries served (comma-separated)"><input className={inputCls} value={form.countries} onChange={(e) => set('countries', e.target.value)} placeholder="Cyprus, Germany" /></Field>
        <Field label="Regions (comma-separated)"><input className={inputCls} value={form.regions} onChange={(e) => set('regions', e.target.value)} placeholder="Akrotiri" /></Field>
      </div>
      <button onClick={submit} disabled={busy} className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-cyan-200 text-cyan-700 text-sm font-semibold hover:bg-cyan-50 disabled:opacity-60" data-testid="mod-supplier-add">
        {busy ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />} Add supplier
      </button>
    </section>
  );
};

/* ── Add site ──────────────────────────────────────────────────────── */
const AddSite = ({ hqsReady, suppliers, onCreated }) => {
  const blank = {
    force: 'army', site_name: '', site_code: '', country: 'United Kingdom', region: '',
    address_line1: '', city: '', county: '', postcode: '',
    site_manager_name: '', site_manager_email: '', phone: '', service_supplier_id: '',
  };
  const [form, setForm] = useState(blank);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const overseas = form.country.trim().toLowerCase() !== 'united kingdom';

  const submit = async () => {
    if (!form.site_name.trim()) return toast.error('Site name is required');
    if (overseas && !form.service_supplier_id) return toast.error('Pick an external service supplier for this overseas site');
    setBusy(true);
    try {
      const { data } = await axios.post(`${API}/master-admin/mod-estate/sites`, {
        estate_id: ESTATE_ID, ...form,
        service_supplier_id: overseas ? form.service_supplier_id : '',
      }, auth());
      setResult(data);
      toast.success(`Site "${data.site.name}" created`);
      setForm(blank);
      onCreated();
    } catch (e) {
      toast.error(errMsg(e, 'Could not create site'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="rounded-xl border border-slate-200 p-4 space-y-3" data-testid="mod-estate-add-site">
      <div className="flex items-center gap-2 text-slate-800">
        <MapPin size={16} className="text-cyan-500" />
        <h3 className="text-sm font-bold">3 · Add a site</h3>
      </div>
      {!hqsReady && <p className="text-[12px] text-amber-600">Set up the service Head Offices first (step 1).</p>}

      {result && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm" data-testid="mod-estate-site-result">
          <div className="flex items-center gap-2 text-emerald-700 font-semibold">
            <CheckCircle2 size={15} /> {result.site.name} · {SERVICE_META[result.site.force]?.label} · {result.site.is_overseas ? `Overseas (${result.site.service_supplier})` : 'UK · Pulse-serviced'}
          </div>
          {result.login?.mode === 'password' ? (
            <div className="mt-2 flex flex-wrap items-center gap-2 text-[12px] text-slate-700">
              <KeyRound size={13} className="text-amber-600" />
              <span className="font-semibold text-slate-600">Shared login</span>
              <span>Username <code className="font-mono bg-white border border-slate-200 rounded px-1.5 py-0.5">{result.login.username}</code></span>
              <span>Password <code className="font-mono bg-white border border-slate-200 rounded px-1.5 py-0.5">{result.login.temporary_password}</code></span>
              <button onClick={() => { navigator.clipboard?.writeText(result.login.temporary_password); toast.success('Password copied'); }} className="p-1 rounded hover:bg-white"><Copy size={12} /></button>
              <span className="text-[11px] text-slate-500 basis-full">Restricted — for all site staff. Cannot see Reports/figures or Staffing.</span>
            </div>
          ) : (
            <div className="mt-2 text-[12px] text-slate-700 break-all">Shared login invite: {result.login?.invite_url}</div>
          )}
          {result.owner_login && (
            <div className="mt-2 pt-2 border-t border-emerald-200 flex flex-wrap items-center gap-2 text-[12px] text-slate-700" data-testid="mod-estate-owner-login">
              <KeyRound size={13} className="text-emerald-600" />
              <span className="font-semibold text-slate-600">Owner login</span>
              {result.owner_login.mode === 'password' ? (
                <>
                  <span>Email <code className="font-mono bg-white border border-slate-200 rounded px-1.5 py-0.5">{result.owner_login.email}</code></span>
                  <span>Password <code className="font-mono bg-white border border-slate-200 rounded px-1.5 py-0.5">{result.owner_login.temporary_password}</code></span>
                  <button onClick={() => { navigator.clipboard?.writeText(result.owner_login.temporary_password); toast.success('Owner password copied'); }} className="p-1 rounded hover:bg-white"><Copy size={12} /></button>
                </>
              ) : (
                <span className="break-all">Invite sent to {result.owner_login.email}: {result.owner_login.invite_url}</span>
              )}
              <span className="text-[11px] text-slate-500 basis-full">Individual, full-visibility owner. Ownership can be handed over later from the site's Staffing → Staff tab.</span>
            </div>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Field label="Service" required>
          <select className={inputCls} value={form.force} onChange={(e) => set('force', e.target.value)} data-testid="mod-site-force">
            <option value="army">British Army</option>
            <option value="raf">Royal Air Force</option>
            <option value="navy">Royal Navy</option>
          </select>
        </Field>
        <Field label="Site name" required><input className={inputCls} value={form.site_name} onChange={(e) => set('site_name', e.target.value)} data-testid="mod-site-name" /></Field>
        <Field label="Site code"><input className={inputCls} value={form.site_code} onChange={(e) => set('site_code', e.target.value)} placeholder="auto from name" data-testid="mod-site-code" /></Field>
        <Field label="Country" required><input className={inputCls} value={form.country} onChange={(e) => set('country', e.target.value)} data-testid="mod-site-country" /></Field>
        <Field label="Region"><input className={inputCls} value={form.region} onChange={(e) => set('region', e.target.value)} data-testid="mod-site-region" /></Field>
        <Field label="Address line 1"><input className={inputCls} value={form.address_line1} onChange={(e) => set('address_line1', e.target.value)} /></Field>
        <Field label="City"><input className={inputCls} value={form.city} onChange={(e) => set('city', e.target.value)} /></Field>
        <Field label="Postcode"><input className={inputCls} value={form.postcode} onChange={(e) => set('postcode', e.target.value)} /></Field>
        <Field label="Site manager name"><input className={inputCls} value={form.site_manager_name} onChange={(e) => set('site_manager_name', e.target.value)} /></Field>
        <Field label="Site manager email"><input className={inputCls} value={form.site_manager_email} onChange={(e) => set('site_manager_email', e.target.value)} /></Field>
      </div>

      {overseas && (
        <div className="rounded-lg border border-indigo-200 bg-indigo-50/50 p-3" data-testid="mod-site-overseas-block">
          <div className="flex items-center gap-1.5 text-indigo-700 text-xs font-semibold mb-1.5">
            <Globe2 size={13} /> Overseas site — assign an external service supplier (Pulse Fitness is still notified of all faults)
          </div>
          <select className={inputCls} value={form.service_supplier_id} onChange={(e) => set('service_supplier_id', e.target.value)} data-testid="mod-site-supplier">
            <option value="">Select a service supplier…</option>
            {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}{s.countries?.length ? ` (${s.countries.join(', ')})` : ''}</option>)}
          </select>
          {suppliers.length === 0 && <p className="text-[11px] text-amber-600 mt-1">Add a supplier in step 2 first.</p>}
        </div>
      )}

      <button onClick={submit} disabled={busy || !hqsReady} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-cyan-500 text-white text-sm font-bold hover:bg-cyan-600 disabled:opacity-60" data-testid="mod-site-submit">
        {busy ? <Loader2 size={15} className="animate-spin" /> : <Plus size={15} />} Create site
      </button>
      <p className="text-[11px] text-slate-400">Provisioning many sites at once? Use the <strong>MOD Sites (CSV bulk)</strong> tab.</p>
    </section>
  );
};

export default MODEstateWizard;
