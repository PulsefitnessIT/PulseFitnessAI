/**
 * EngineerCustomers — Iter 216h259
 *
 * Lite CRM for field engineers. Shared org-wide. Saves customer
 * details so engineers can search + auto-fill quotes/invoices
 * instead of retyping. Stores name, email, phone, site name/address,
 * equipment list, notes, and last-job-date.
 *
 * Routes: GET/POST/PATCH/DELETE /api/svc/engineer/customers
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import {
  ArrowLeft, Users, Plus, Search, Loader2, Mail, Phone, MapPin,
  Trash2, Edit3, Save, X, Wrench, FileText, CalendarClock,
  ReceiptPoundSterling as Receipt, Building2, CheckCircle2, AlertTriangle,
  ChevronRight, Download, Upload,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { useLocalization, formatMoney } from '@/utils/localization';
import useEngineerOrgBrand from './hooks/useEngineerOrgBrand';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const auth = () => ({
  headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
});

const EMPTY_FORM = {
  name: '', email: '', phone: '', site_name: '',
  // Iter 220ck — structured address (better reporting).
  address_line1: '', address_line2: '', city: '', county: '',
  postcode: '', country: 'United Kingdom',
  company_number: '',
  notes: '', equipment_list: '',
};

// Iter 220ck — three-step wizard. The order matches how an engineer
// thinks: who is this gym → where do I drive → what do they own.
const WIZARD_STEPS = [
  { id: 'identity', label: 'Identity' },
  { id: 'site',     label: 'Site' },
  { id: 'equip',    label: 'Equipment' },
];

const fmtDate = (iso) => {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
  } catch {
    return iso.slice(0, 10);
  }
};

const Field = ({ label, value, onChange, type = 'text', testid, placeholder, multiline }) => (
  <label className="block">
    <span className="text-[11px] font-bold uppercase tracking-wide text-slate-500">{label}</span>
    {multiline ? (
      <textarea
        rows={3}
        className="w-full mt-1 text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white text-slate-900 placeholder-slate-400 focus:border-cyan-400 focus:outline-none"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        data-testid={testid}
      />
    ) : (
      <input
        type={type}
        className="w-full mt-1 text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white text-slate-900 placeholder-slate-400 focus:border-cyan-400 focus:outline-none"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        data-testid={testid}
      />
    )}
  </label>
);

// Iter 220ea·26 (G1) — Canonical CRM link. Shows the linked CRM company
// for a service customer (one shared spine across CRM ↔ Service Ops) and
// lets the user search + link, or unlink. Linking PATCHes `company_id`.
const CrmLinkRow = ({ customerId, crmCompany, onChanged }) => {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [busy, setBusy] = useState(false);

  const runSearch = async (val) => {
    setQ(val);
    if (!val.trim()) { setResults([]); return; }
    setSearching(true);
    try {
      const r = await axios.get(`${API}/svc/customers/crm-search`,
        { params: { q: val }, ...auth() });
      setResults(r.data?.companies || []);
    } catch { setResults([]); } finally { setSearching(false); }
  };

  const setLink = async (companyId) => {
    setBusy(true);
    try {
      await axios.patch(`${API}/svc/engineer/customers/${customerId}`,
        { company_id: companyId }, auth());
      notify.success(companyId ? 'Linked to CRM customer' : 'Unlinked from CRM');
      setOpen(false); setQ(''); setResults([]);
      onChanged?.();
    } catch (e) {
      notify.error('Could not update CRM link', e?.response?.data?.detail || e?.message);
    } finally { setBusy(false); }
  };

  const pushToCrm = async () => {
    setBusy(true);
    try {
      const r = await axios.post(`${API}/svc/customers/${customerId}/push-to-crm`, {}, auth());
      notify.success(
        r.data?.created ? 'Created in CRM' : 'Linked to CRM',
        r.data?.company_name ? `${r.data.company_name} is now in the CRM.` : undefined);
      onChanged?.();
    } catch (e) {
      notify.error('Could not push to CRM', e?.response?.data?.detail || e?.message);
    } finally { setBusy(false); }
  };

  return (
    <div className="pt-2 border-t border-slate-100" data-testid={`crm-link-${customerId}`}>
      <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500 flex items-center gap-1">
        <Building2 size={12} /> CRM customer
      </p>
      {crmCompany ? (
        <div className="mt-1 flex items-center justify-between gap-2">
          <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-full px-2 py-1"
            data-testid={`crm-link-badge-${customerId}`}>
            <CheckCircle2 size={12} /> {crmCompany.name}
            {crmCompany.sage_customer_id
              ? <span className="text-emerald-500 font-mono">· {crmCompany.sage_customer_id}</span>
              : null}
          </span>
          <button type="button" onClick={() => setLink('')} disabled={busy}
            className="text-[11px] text-slate-400 hover:text-rose-600 font-semibold disabled:opacity-50"
            data-testid={`crm-unlink-${customerId}`}>
            {busy ? <Loader2 size={12} className="animate-spin" /> : 'Unlink'}
          </button>
        </div>
      ) : !open ? (
        <div className="mt-1 flex items-center gap-3 flex-wrap">
          <button type="button" onClick={() => setOpen(true)}
            className="inline-flex items-center gap-1 text-xs font-semibold text-cyan-600 hover:text-cyan-700"
            data-testid={`crm-link-open-${customerId}`}>
            <Search size={12} /> Link to a CRM customer
          </button>
          <span className="text-slate-300">·</span>
          <button type="button" onClick={pushToCrm} disabled={busy}
            className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-600 hover:text-emerald-700 disabled:opacity-50"
            data-testid={`crm-push-${customerId}`}>
            {busy ? <Loader2 size={12} className="animate-spin" /> : <Building2 size={12} />}
            Create in CRM
          </button>
        </div>
      ) : (
        <div className="mt-1 space-y-1">
          <div className="relative">
            <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-400" />
            <input autoFocus value={q} onChange={(e) => runSearch(e.target.value)}
              placeholder="Search CRM companies…"
              className="w-full text-xs border border-slate-200 rounded-lg pl-7 pr-2 py-1.5 bg-white"
              data-testid={`crm-link-search-${customerId}`} />
          </div>
          {searching ? (
            <p className="text-[11px] text-slate-400 flex items-center gap-1">
              <Loader2 size={11} className="animate-spin" /> Searching…
            </p>
          ) : results.length > 0 ? (
            <ul className="border border-slate-100 rounded-lg divide-y divide-slate-50 max-h-40 overflow-y-auto">
              {results.map((c) => (
                <li key={c.id}>
                  <button type="button" disabled={busy} onClick={() => setLink(c.id)}
                    className="w-full text-left px-2 py-1.5 hover:bg-slate-50 text-xs flex items-center justify-between gap-2 disabled:opacity-50"
                    data-testid={`crm-link-result-${c.id}`}>
                    <span className="truncate"><b>{c.name}</b>
                      {c.postcode ? <span className="text-slate-400 ml-1">{c.postcode}</span> : null}</span>
                    {c.sage_customer_id
                      ? <span className="text-emerald-600 font-mono shrink-0">{c.sage_customer_id}</span> : null}
                  </button>
                </li>
              ))}
            </ul>
          ) : q.trim() ? (
            <p className="text-[11px] text-slate-400 italic">No CRM companies match.</p>
          ) : null}
          <button type="button" onClick={() => { setOpen(false); setQ(''); setResults([]); }}
            className="text-[11px] text-slate-400 hover:text-slate-600">Cancel</button>
        </div>
      )}
    </div>
  );
};


export default function EngineerCustomers() {
  const navigate = useNavigate();
  const loc = useLocalization();
  const orgBrand = useEngineerOrgBrand();
  const internal = orgBrand.internal;
  const [terr, setTerr] = useState({ customers: [], territories: [] });
  const [rows, setRows] = useState([]);
  const [q, setQ] = useState('');
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [editId, setEditId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [activeId, setActiveId] = useState(null);
  const [activeDetail, setActiveDetail] = useState(null); // { id, recent_quotes, recent_invoices }
  const [activeDetailLoading, setActiveDetailLoading] = useState(false);
  // Iter 220cj — Companies House lookup + per-field validation.
  const [formErrors, setFormErrors] = useState({});
  const [wizardStep, setWizardStep] = useState(0);  // 220ck — 3-step wizard
  const [chQuery, setChQuery] = useState('');
  const [chResults, setChResults] = useState([]);
  const [chLoading, setChLoading] = useState(false);
  const [chEnabled, setChEnabled] = useState(false);
  const [chPicked, setChPicked] = useState(null);
  const chDebRef = useRef(null);

  useEffect(() => {
    let cancel = false;
    (async () => {
      try {
        const r = await axios.get(`${API}/account/companies-house/status`, auth());
        if (!cancel) setChEnabled(Boolean(r.data?.enabled));
      } catch {
        if (!cancel) setChEnabled(false);
      }
    })();
    return () => { cancel = true; };
  }, []);

  const runChSearch = async (q) => {
    if (!chEnabled || !q || q.trim().length < 2) {
      setChResults([]);
      return;
    }
    setChLoading(true);
    try {
      const r = await axios.get(`${API}/account/companies-house/search`, {
        ...auth(), params: { q: q.trim(), limit: 8 },
      });
      setChResults(r.data?.items || []);
    } catch {
      setChResults([]);
    } finally {
      setChLoading(false);
    }
  };

  const onChQueryChange = (v) => {
    setChQuery(v);
    if (chDebRef.current) clearTimeout(chDebRef.current);
    chDebRef.current = setTimeout(() => runChSearch(v), 250);
  };

  const pickFromCh = async (item) => {
    try {
      const r = await axios.get(
        `${API}/account/companies-house/company/${item.company_number}`,
        auth(),
      );
      const profile = r.data || {};
      // Companies House profile returns `registered_office_address`
      // (snake-case object) when configured. Stringify lightly.
      const addr = profile.registered_office_address || profile.address || {};
      const addressStr = [
        addr.address_line_1, addr.address_line_2, addr.locality,
        addr.region, addr.postal_code,
      ].filter(Boolean).join(', ');
      setForm((f) => ({
        ...f,
        name: profile.company_name || item.company_name || f.name,
        // Iter 220ck — populate structured address from CH fields so
        // the new wizard's Site step renders pre-filled.
        address_line1: addr.address_line_1 || f.address_line1,
        address_line2: addr.address_line_2 || f.address_line2,
        city: addr.locality || f.city,
        county: addr.region || f.county,
        postcode: addr.postal_code || f.postcode,
        country: addr.country || f.country || 'United Kingdom',
        company_number: item.company_number,
      }));
      setChPicked({
        company_number: item.company_number,
        company_name: profile.company_name || item.company_name,
        status: profile.company_status || item.company_status,
        address_str: addressStr,
      });
      setFormErrors((er) => ({
        ...er, name: undefined,
        address_line1: undefined, city: undefined, postcode: undefined,
      }));
      setChResults([]);
      setChQuery('');
      notify.success(`Filled from Companies House · ${item.company_name}`);
    } catch (err) {
      notify.error('Companies House lookup failed',
                   err?.response?.data?.detail || err?.message);
    }
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/svc/engineer/customers`, {
        ...auth(),
        params: q ? { q } : {},
      });
      setRows(r.data?.customers || []);
    } catch (err) {
      notify.error('Failed to load customers', err?.response?.data?.detail || err?.message);
    } finally {
      setLoading(false);
    }
  }, [q]);

  useEffect(() => {
    const id = setTimeout(load, 200);
    return () => clearTimeout(id);
  }, [load]);

  // Iter 288b — Pulse-only: pull the engineer's customers from their assigned
  // CRM territories (read-only). No-ops (empty) for non-Pulse / unassigned.
  useEffect(() => {
    if (!internal) return;
    let cancel = false;
    (async () => {
      try {
        const r = await axios.get(`${API}/svc/engineer/customers/crm-territory`, auth());
        if (!cancel) setTerr({
          customers: r.data?.customers || [],
          territories: r.data?.territories || [],
        });
      } catch {
        if (!cancel) setTerr({ customers: [], territories: [] });
      }
    })();
    return () => { cancel = true; };
  }, [internal]);

  const terrQ = q.trim().toLowerCase();
  const terrFiltered = terrQ
    ? terr.customers.filter((c) =>
        [c.name, c.email, c.phone, c.site_address, c.territory_name]
          .some((v) => (v || '').toLowerCase().includes(terrQ)))
    : terr.customers;

  const openNew = () => {
    setForm(EMPTY_FORM);
    setEditId(null);
    setWizardStep(0);
    setShowForm(true);
  };

  const openEdit = (row) => {
    setForm({
      name: row.name || '',
      email: row.email || '',
      phone: row.phone || '',
      site_name: row.site_name || '',
      // Iter 220ck — structured address (with legacy fallback when
      // the customer was created before this iter).
      address_line1: row.address_line1 || row.site_address || '',
      address_line2: row.address_line2 || '',
      city: row.city || '',
      county: row.county || '',
      postcode: row.postcode || '',
      country: row.country || 'United Kingdom',
      company_number: row.company_number || '',
      notes: row.notes || '',
      equipment_list: (row.equipment_list || []).join('\n'),
    });
    setEditId(row.id);
    setWizardStep(0);
    setShowForm(true);
  };

  const close = () => {
    setShowForm(false);
    setForm(EMPTY_FORM);
    setEditId(null);
    setWizardStep(0);
    setFormErrors({});
    setChQuery('');
    setChResults([]);
    setChPicked(null);
  };

  const save = async () => {
    // Iter 220ck — wizard validation. Each step's required fields
    // are checked before allowing forward navigation; ``save`` runs
    // the full check one last time as a defence-in-depth.
    const errs = validateAll();
    if (Object.keys(errs).length > 0) {
      setFormErrors(errs);
      // Jump to the earliest step containing an error.
      const stepOfField = (k) => {
        if (['name', 'email', 'phone'].includes(k)) return 0;
        if (['site_name', 'address_line1', 'city', 'postcode'].includes(k)) return 1;
        return 2;
      };
      const stepIdx = Math.min(...Object.keys(errs).map(stepOfField));
      setWizardStep(stepIdx);
      notify.error('Please fix the highlighted fields');
      return;
    }
    setSaving(true);
    try {
      const payload = {
        name: form.name.trim(),
        email: form.email.trim() || null,
        phone: form.phone.trim() || null,
        site_name: form.site_name.trim() || null,
        // Iter 220ck — structured address fields (preferred for reporting).
        address_line1: form.address_line1.trim() || null,
        address_line2: form.address_line2.trim() || null,
        city: form.city.trim() || null,
        county: form.county.trim() || null,
        postcode: form.postcode.trim() || null,
        country: (form.country || 'United Kingdom').trim(),
        notes: form.notes.trim() || null,
        equipment_list: form.equipment_list
          .split('\n').map((s) => s.trim()).filter(Boolean),
      };
      if (form.company_number) payload.company_number = form.company_number;
      if (editId) {
        await axios.patch(`${API}/svc/engineer/customers/${editId}`, payload, auth());
        notify.success('Customer updated');
      } else {
        const r = await axios.post(`${API}/svc/engineer/customers`, payload, auth());
        notify.success(r.data?.merged ? 'Existing customer updated' : 'Customer saved');
      }
      close();
      await load();
    } catch (err) {
      notify.error('Save failed', err?.response?.data?.detail || err?.message);
    } finally {
      setSaving(false);
    }
  };

  // Iter 220ck — wizard step validators.
  const validateAll = () => {
    const er = {};
    if (!form.name.trim()) er.name = 'Required';
    const email = form.email.trim();
    if (!email) er.email = 'Required';
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) er.email = 'Enter a valid email';
    const phone = form.phone.trim();
    if (!phone) er.phone = 'Required';
    else if (phone.replace(/[^0-9]/g, '').length < 7) er.phone = 'Enter a valid phone';
    if (!form.site_name.trim()) er.site_name = 'Required';
    if (!form.address_line1.trim()) er.address_line1 = 'Required';
    if (!form.city.trim()) er.city = 'Required';
    if (!form.postcode.trim()) er.postcode = 'Required';
    return er;
  };

  const validateStep = (idx) => {
    const all = validateAll();
    const stepFields = {
      0: ['name', 'email', 'phone'],
      1: ['site_name', 'address_line1', 'city', 'postcode'],
      2: [],  // equipment step is optional
    }[idx] || [];
    const er = {};
    stepFields.forEach((k) => { if (all[k]) er[k] = all[k]; });
    return er;
  };

  const goNext = () => {
    const er = validateStep(wizardStep);
    if (Object.keys(er).length > 0) {
      setFormErrors((prev) => ({ ...prev, ...er }));
      notify.error('Please fix the highlighted fields');
      return;
    }
    setWizardStep((s) => Math.min(s + 1, WIZARD_STEPS.length - 1));
  };
  const goBack = () => setWizardStep((s) => Math.max(s - 1, 0));

  const removeRow = async (row) => {
    if (!window.confirm(`Delete ${row.name}? This cannot be undone.`)) return;
    try {
      await axios.delete(`${API}/svc/engineer/customers/${row.id}`, auth());
      notify.success('Customer deleted');
      await load();
    } catch (err) {
      notify.error('Delete failed', err?.response?.data?.detail || err?.message);
    }
  };

  const handleUseInQuote = (row) => {
    const params = new URLSearchParams({
      customer_id: row.id,
      name: row.name || '',
      email: row.email || '',
      phone: row.phone || '',
      site_name: row.site_name || '',
      site_address: row.site_address || '',
    });
    navigate(`/svc/engineer/quotes/new?${params.toString()}`);
  };

  const loadActiveDetail = async (id) => {
    setActiveDetail(null);
    setActiveDetailLoading(true);
    try {
      const r = await axios.get(`${API}/svc/engineer/customers/${id}`, auth());
      setActiveDetail(r.data);
    } catch (err) {
      notify.error('Failed to load customer history', err?.response?.data?.detail || err?.message);
    } finally {
      setActiveDetailLoading(false);
    }
  };

  const handleToggleRow = async (row) => {
    if (activeId === row.id) {
      setActiveId(null);
      setActiveDetail(null);
      return;
    }
    setActiveId(row.id);
    await loadActiveDetail(row.id);
  };

  return (
    <div className="min-h-screen bg-slate-50" data-testid="engineer-customers-page">
      <header className="sticky top-0 z-20 bg-white border-b border-slate-200">
        <div className="max-w-3xl mx-auto px-4 py-3 flex items-center gap-3">
          <button
            onClick={() => navigate('/svc/engineer')}
            className="inline-flex items-center gap-1 text-sm font-bold text-slate-600 hover:text-slate-900"
            data-testid="customers-back"
            aria-label="Back"
          >
            <ArrowLeft size={16} /> Back
          </button>
          <div className="flex-1 min-w-0">
            <h1 className="text-base font-bold text-slate-900 flex items-center gap-2">
              <Users size={16} /> My customers
            </h1>
            <p className="text-[11px] text-slate-500">
              Shared with your team — save once, reuse on every quote.
            </p>
          </div>
          <button
            type="button"
            onClick={openNew}
            className="inline-flex items-center gap-1 px-3 py-2 rounded-lg bg-gradient-to-br from-[#0891b2] to-[#0e7490] text-white text-xs font-bold shadow"
            data-testid="customers-new-btn"
          >
            <Plus size={14} /> New
          </button>
        </div>
        <div className="max-w-3xl mx-auto px-4 pb-3">
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search by name, email, phone or site"
              className="w-full bg-white border border-slate-200 focus:border-cyan-400 rounded-lg pl-9 pr-3 py-2 text-sm focus:outline-none"
              data-testid="customers-search"
            />
          </div>
        </div>
      </header>

      <main className="max-w-3xl mx-auto p-4 space-y-3">
        {internal && terrFiltered.length > 0 && (
          <section data-testid="customers-crm-territory" className="space-y-2">
            <div className="flex items-center gap-2 px-1">
              <MapPin size={14} className="text-cyan-700" />
              <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500">
                From your CRM territories
              </p>
              <span className="text-[10px] text-slate-400">
                {terr.territories.map((t) => t.name).join(' · ')}
              </span>
            </div>
            {terrFiltered.map((c) => (
              <div
                key={c.id}
                className="bg-white rounded-2xl border border-slate-200 px-4 py-3"
                data-testid={`crm-customer-row-${c.crm_company_id}`}
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-bold text-slate-900 truncate">{c.name}</p>
                    <p className="text-xs text-slate-500 truncate">
                      {c.site_address || c.email || c.phone || '—'}
                    </p>
                  </div>
                  <span className="flex-shrink-0 text-[10px] font-bold px-2 py-1 rounded-full bg-cyan-50 text-cyan-700">
                    {c.territory_name}
                  </span>
                </div>
                {(c.phone || c.email) && (
                  <div className="mt-2 flex flex-wrap gap-3 text-xs text-slate-600">
                    {c.phone && (
                      <a href={`tel:${c.phone}`} className="inline-flex items-center gap-1 hover:text-cyan-700">
                        <Phone size={12} /> {c.phone}
                      </a>
                    )}
                    {c.email && (
                      <a href={`mailto:${c.email}`} className="inline-flex items-center gap-1 hover:text-cyan-700">
                        <Mail size={12} /> {c.email}
                      </a>
                    )}
                  </div>
                )}
                <button
                  type="button"
                  onClick={() => {
                    try {
                      sessionStorage.setItem('svc.engineer.crmCustomerDraft', JSON.stringify({
                        name: c.name, email: c.email, phone: c.phone,
                        site_name: c.site_name, site_address: c.site_address,
                        crm_company_id: c.crm_company_id, territory_id: c.territory_id,
                      }));
                    } catch { /* ignore */ }
                    navigate('/svc/engineer/jobs/new?from=crm-customer');
                  }}
                  className="mt-3 w-full inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-gradient-to-br from-[#0891b2] to-[#0e7490] text-white text-xs font-bold shadow"
                  data-testid={`crm-customer-start-job-${c.crm_company_id}`}
                >
                  <Wrench size={13} /> Start a job
                </button>
              </div>
            ))}
            {rows.length > 0 && (
              <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500 px-1 pt-2">
                Your saved customers
              </p>
            )}
          </section>
        )}
        {loading ? (
          <div className="flex items-center justify-center py-10">
            <Loader2 className="animate-spin text-cyan-500" />
          </div>
        ) : rows.length === 0 ? (
          (internal && terrFiltered.length > 0) ? null : (
          <div className="bg-white rounded-2xl border border-slate-200 p-8 text-center" data-testid="customers-empty">
            <Users size={28} className="mx-auto text-slate-300 mb-3" />
            <p className="font-bold text-slate-900">No customers yet</p>
            <p className="text-sm text-slate-500 mt-1">
              Add your first customer so you can auto-fill quotes & invoices.
            </p>
            <button
              type="button"
              onClick={openNew}
              className="mt-4 inline-flex items-center gap-1 px-4 py-2 rounded-lg bg-gradient-to-br from-[#0891b2] to-[#0e7490] text-white text-sm font-bold"
              data-testid="customers-empty-cta"
            >
              <Plus size={14} /> Add customer
            </button>
          </div>
          )
        ) : (
          rows.map((row) => {
            const isOpen = activeId === row.id;
            return (
              <div
                key={row.id}
                className="bg-white rounded-2xl border border-slate-200 overflow-hidden"
                data-testid={`customer-row-${row.id}`}
              >
                <button
                  type="button"
                  onClick={() => handleToggleRow(row)}
                  className="w-full text-left px-4 py-3 flex items-center justify-between gap-3 hover:bg-slate-50"
                  data-testid={`customer-row-toggle-${row.id}`}
                >
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-bold text-slate-900 truncate">{row.name}</p>
                    <p className="text-xs text-slate-500 truncate">
                      {row.site_name || row.site_address || row.email || row.phone || '—'}
                    </p>
                  </div>
                  <div className="text-right flex-shrink-0">
                    <p className="text-[10px] uppercase tracking-wider font-bold text-slate-400">Last job</p>
                    <p className="text-xs font-semibold text-slate-700">{fmtDate(row.last_job_at)}</p>
                  </div>
                </button>
                {isOpen ? (
                  <div className="border-t border-slate-100 p-4 space-y-3 text-sm" data-testid={`customer-detail-${row.id}`}>
                    {row.email ? (
                      <p className="flex items-center gap-2 text-slate-700">
                        <Mail size={14} className="text-slate-400" /> {row.email}
                      </p>
                    ) : null}
                    {row.phone ? (
                      <p className="flex items-center gap-2 text-slate-700">
                        <Phone size={14} className="text-slate-400" /> {row.phone}
                      </p>
                    ) : null}
                    {(row.site_name || row.site_address) ? (
                      <p className="flex items-start gap-2 text-slate-700">
                        <MapPin size={14} className="text-slate-400 mt-0.5" />
                        <span>
                          {row.site_name ? <b className="block">{row.site_name}</b> : null}
                          {row.site_address}
                        </span>
                      </p>
                    ) : null}
                    {row.equipment_list && row.equipment_list.length > 0 ? (
                      <div>
                        <p className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-wide text-slate-500">
                          <Wrench size={12} /> Equipment
                        </p>
                        <ul className="mt-1 text-slate-700 list-disc list-inside text-xs">
                          {row.equipment_list.map((e, i) => (
                            <li key={i}>{e}</li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                    {row.notes ? (
                      <div>
                        <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500">Notes</p>
                        <p className="text-slate-700 whitespace-pre-wrap text-xs mt-1">{row.notes}</p>
                      </div>
                    ) : null}
                    {row.last_job_at ? (
                      <p className="flex items-center gap-2 text-[11px] text-slate-500">
                        <CalendarClock size={12} /> Last job {fmtDate(row.last_job_at)}
                      </p>
                    ) : null}
                    {/* Iter 216h260 — recent quotes + invoices for repeat-business view */}
                    {activeDetailLoading && activeId === row.id ? (
                      <p className="text-[11px] text-slate-400 flex items-center gap-1">
                        <Loader2 size={12} className="animate-spin" /> Loading history…
                      </p>
                    ) : activeDetail && activeDetail.id === row.id ? (
                      <div className="space-y-2 pt-2 border-t border-slate-100" data-testid={`customer-history-${row.id}`}>
                        {(activeDetail.recent_quotes || []).length > 0 ? (
                          <div>
                            <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500 flex items-center gap-1">
                              <FileText size={12} /> Recent quotes ({activeDetail.recent_quotes.length})
                            </p>
                            <ul className="mt-1 space-y-1">
                              {activeDetail.recent_quotes.map((qq) => (
                                <li key={qq.id}>
                                  <button
                                    type="button"
                                    onClick={() => navigate(`/svc/engineer/quotes/${qq.id}`)}
                                    className="w-full text-left flex items-center justify-between gap-2 px-2 py-1 rounded hover:bg-slate-50 text-xs"
                                    data-testid={`customer-quote-${qq.id}`}
                                  >
                                    <span className="truncate">
                                      <b>{qq.quote_number}</b>
                                      <span className="text-slate-500 ml-1 capitalize">· {qq.status}</span>
                                    </span>
                                    <span className="tabular-nums font-semibold">{formatMoney(qq.total || 0, loc)}</span>
                                  </button>
                                </li>
                              ))}
                            </ul>
                          </div>
                        ) : null}
                        {(activeDetail.recent_invoices || []).length > 0 ? (
                          <div>
                            <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500 flex items-center gap-1">
                              <Receipt size={12} /> Recent invoices ({activeDetail.recent_invoices.length})
                            </p>
                            <ul className="mt-1 space-y-1">
                              {activeDetail.recent_invoices.map((inv) => (
                                <li key={inv.id}>
                                  <button
                                    type="button"
                                    onClick={() => navigate(`/svc/engineer/invoices/${inv.id}`)}
                                    className="w-full text-left flex items-center justify-between gap-2 px-2 py-1 rounded hover:bg-slate-50 text-xs"
                                    data-testid={`customer-invoice-${inv.id}`}
                                  >
                                    <span className="truncate">
                                      <b>{inv.invoice_number}</b>
                                      <span className="text-slate-500 ml-1 capitalize">· {inv.status}</span>
                                    </span>
                                    <span className="tabular-nums font-semibold">{formatMoney(inv.total || 0, loc)}</span>
                                  </button>
                                </li>
                              ))}
                            </ul>
                          </div>
                        ) : null}
                        {(activeDetail.recent_quotes || []).length === 0
                         && (activeDetail.recent_invoices || []).length === 0 ? (
                          <p className="text-[11px] text-slate-400 italic">
                            No quotes or invoices on file yet.
                          </p>
                        ) : null}
                        <CrmLinkRow
                          customerId={activeDetail.id}
                          crmCompany={activeDetail.crm_company}
                          onChanged={() => loadActiveDetail(activeDetail.id)}
                        />
                      </div>
                    ) : null}
                    <div className="flex flex-wrap gap-2 pt-2 border-t border-slate-100">
                      <button
                        type="button"
                        onClick={() => handleUseInQuote(row)}
                        className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-gradient-to-br from-[#0891b2] to-[#0e7490] text-white text-xs font-bold"
                        data-testid={`customer-use-quote-${row.id}`}
                      >
                        <FileText size={12} /> Use in quote
                      </button>
                      {/* Iter 220cl — Per-customer equipment CSV import. */}
                      <CustomerEquipmentCsv customer={row} onImported={load} />
                      <button
                        type="button"
                        onClick={() => openEdit(row)}
                        className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-slate-700 text-xs font-bold"
                        data-testid={`customer-edit-${row.id}`}
                      >
                        <Edit3 size={12} /> Edit
                      </button>
                      <button
                        type="button"
                        onClick={() => removeRow(row)}
                        className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-rose-200 bg-rose-50 text-rose-700 text-xs font-bold"
                        data-testid={`customer-delete-${row.id}`}
                      >
                        <Trash2 size={12} /> Delete
                      </button>
                    </div>
                  </div>
                ) : null}
              </div>
            );
          })
        )}
      </main>

      {showForm ? (
        <div
          className="fixed inset-0 z-30 bg-black/60 flex items-end sm:items-center justify-center p-2 sm:p-4"
          data-testid="customer-form-backdrop"
        >
          <div className="bg-white w-full sm:max-w-lg rounded-t-2xl sm:rounded-2xl shadow-xl border border-slate-200 max-h-[90vh] overflow-y-auto">
            <header className="px-4 py-3 border-b border-slate-200 flex items-center justify-between sticky top-0 bg-white">
              <h2 className="font-bold text-slate-900 text-sm">
                {editId ? 'Edit customer' : 'New customer'}
              </h2>
              <button
                type="button"
                onClick={close}
                className="p-1 rounded-lg hover:bg-slate-100"
                data-testid="customer-form-close"
                aria-label="Close"
              >
                <X size={18} />
              </button>
            </header>
            <div className="p-4">
              {/* Iter 220ck — Stepper */}
              <div className="mb-4 flex items-center gap-2" data-testid="customer-wizard-stepper">
                {WIZARD_STEPS.map((s, idx) => (
                  <div key={s.id} className="flex-1 flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => idx < wizardStep && setWizardStep(idx)}
                      disabled={idx > wizardStep}
                      className={`flex items-center gap-1.5 ${idx <= wizardStep ? 'cursor-pointer' : 'cursor-default opacity-60'}`}
                      data-testid={`customer-wizard-step-${idx}`}
                    >
                      <span className={`w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-extrabold ${
                        idx === wizardStep
                          ? 'bg-cyan-600 text-white'
                          : idx < wizardStep
                            ? 'bg-emerald-100 text-emerald-700 border-2 border-emerald-300'
                            : 'bg-slate-100 text-slate-400'
                      }`}>
                        {idx < wizardStep ? <CheckCircle2 size={14} /> : idx + 1}
                      </span>
                      <span className={`text-[11px] font-bold uppercase tracking-wider ${
                        idx === wizardStep ? 'text-slate-900' : 'text-slate-500'
                      }`}>{s.label}</span>
                    </button>
                    {idx < WIZARD_STEPS.length - 1 && (
                      <div className={`flex-1 h-0.5 ${idx < wizardStep ? 'bg-emerald-300' : 'bg-slate-200'}`} />
                    )}
                  </div>
                ))}
              </div>

              {/* Step 1 — Identity */}
              {wizardStep === 0 && (
                <div className="space-y-3" data-testid="customer-wizard-pane-identity">
                  {chEnabled && !editId ? (
                    <div className="bg-emerald-50/60 border border-emerald-200 rounded-xl p-3" data-testid="customer-form-ch-block">
                      <div className="flex items-center gap-2 mb-2">
                        <Building2 size={14} className="text-emerald-700" />
                        <p className="text-[11px] font-bold uppercase tracking-wide text-emerald-700">
                          Companies House lookup
                        </p>
                      </div>
                      <div className="relative">
                        <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-emerald-700/60 pointer-events-none" />
                        <input
                          type="text"
                          value={chQuery}
                          onChange={(e) => onChQueryChange(e.target.value)}
                          placeholder="Search company name or number…"
                          className="w-full pl-9 pr-3 py-2 text-sm rounded-lg border border-emerald-300 bg-white focus:outline-none focus:ring-2 focus:ring-emerald-400"
                          data-testid="customer-form-ch-search"
                        />
                      </div>
                      {chLoading ? (
                        <p className="mt-2 text-[11px] text-emerald-700 flex items-center gap-1">
                          <Loader2 size={11} className="animate-spin" /> Searching…
                        </p>
                      ) : null}
                      {chResults.length > 0 ? (
                        <div className="mt-2 max-h-44 overflow-y-auto bg-white border border-emerald-200 rounded-lg divide-y divide-emerald-100" data-testid="customer-form-ch-results">
                          {chResults.map((item) => (
                            <button
                              type="button"
                              key={item.company_number}
                              onClick={() => pickFromCh(item)}
                              className="w-full text-left px-3 py-2 hover:bg-emerald-50 text-sm"
                              data-testid={`customer-form-ch-pick-${item.company_number}`}
                            >
                              <div className="font-bold text-slate-900 truncate">{item.company_name}</div>
                              <div className="text-[11px] text-slate-500 flex items-center gap-2 mt-0.5">
                                <span className="font-mono">Co. {item.company_number}</span>
                                {item.address_snippet ? <span className="truncate">· {item.address_snippet}</span> : null}
                              </div>
                            </button>
                          ))}
                        </div>
                      ) : null}
                      {chPicked ? (
                        <div className="mt-2 text-[11px] text-emerald-800 flex items-center gap-1" data-testid="customer-form-ch-picked">
                          <CheckCircle2 size={11} /> Verified: {chPicked.company_name} (Co. {chPicked.company_number})
                        </div>
                      ) : null}
                    </div>
                  ) : null}

                  <div>
                    <Field label="Customer name *" value={form.name}
                           onChange={(v) => { setForm({ ...form, name: v }); if (formErrors.name) setFormErrors({ ...formErrors, name: undefined }); }}
                           placeholder="Acme Gyms Ltd"
                           testid="customer-form-name" />
                    {formErrors.name && (
                      <p className="mt-1 text-[11px] font-semibold text-rose-600" data-testid="customer-form-name-error">
                        <AlertTriangle size={10} className="inline mr-0.5" /> {formErrors.name}
                      </p>
                    )}
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <Field label="Email *" type="email" value={form.email}
                             onChange={(v) => { setForm({ ...form, email: v }); if (formErrors.email) setFormErrors({ ...formErrors, email: undefined }); }}
                             placeholder="manager@acme.co.uk"
                             testid="customer-form-email" />
                      {formErrors.email && (
                        <p className="mt-1 text-[11px] font-semibold text-rose-600" data-testid="customer-form-email-error">
                          <AlertTriangle size={10} className="inline mr-0.5" /> {formErrors.email}
                        </p>
                      )}
                    </div>
                    <div>
                      <Field label="Phone *" value={form.phone}
                             onChange={(v) => { setForm({ ...form, phone: v }); if (formErrors.phone) setFormErrors({ ...formErrors, phone: undefined }); }}
                             placeholder="+44 …"
                             testid="customer-form-phone" />
                      {formErrors.phone && (
                        <p className="mt-1 text-[11px] font-semibold text-rose-600" data-testid="customer-form-phone-error">
                          <AlertTriangle size={10} className="inline mr-0.5" /> {formErrors.phone}
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* Step 2 — Site */}
              {wizardStep === 1 && (
                <div className="space-y-3" data-testid="customer-wizard-pane-site">
                  <div>
                    <Field label="Site name *" value={form.site_name}
                           onChange={(v) => { setForm({ ...form, site_name: v }); if (formErrors.site_name) setFormErrors({ ...formErrors, site_name: undefined }); }}
                           placeholder="Acme Gym · Leeds"
                           testid="customer-form-site-name" />
                    {formErrors.site_name && (
                      <p className="mt-1 text-[11px] font-semibold text-rose-600" data-testid="customer-form-site-name-error">
                        <AlertTriangle size={10} className="inline mr-0.5" /> {formErrors.site_name}
                      </p>
                    )}
                  </div>
                  <div>
                    <Field label="Address line 1 *" value={form.address_line1}
                           onChange={(v) => { setForm({ ...form, address_line1: v }); if (formErrors.address_line1) setFormErrors({ ...formErrors, address_line1: undefined }); }}
                           placeholder="12 Industrial Way"
                           testid="customer-form-address-line1" />
                    {formErrors.address_line1 && (
                      <p className="mt-1 text-[11px] font-semibold text-rose-600" data-testid="customer-form-address-line1-error">
                        <AlertTriangle size={10} className="inline mr-0.5" /> {formErrors.address_line1}
                      </p>
                    )}
                  </div>
                  <Field label="Address line 2" value={form.address_line2}
                         onChange={(v) => setForm({ ...form, address_line2: v })}
                         placeholder="Unit 4 (optional)"
                         testid="customer-form-address-line2" />
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <Field label="Town / City *" value={form.city}
                             onChange={(v) => { setForm({ ...form, city: v }); if (formErrors.city) setFormErrors({ ...formErrors, city: undefined }); }}
                             placeholder="Leeds"
                             testid="customer-form-city" />
                      {formErrors.city && (
                        <p className="mt-1 text-[11px] font-semibold text-rose-600" data-testid="customer-form-city-error">
                          <AlertTriangle size={10} className="inline mr-0.5" /> {formErrors.city}
                        </p>
                      )}
                    </div>
                    <Field label="County / Region" value={form.county}
                           onChange={(v) => setForm({ ...form, county: v })}
                           placeholder="West Yorkshire"
                           testid="customer-form-county" />
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <Field label="Postcode *" value={form.postcode}
                             onChange={(v) => { setForm({ ...form, postcode: v.toUpperCase() }); if (formErrors.postcode) setFormErrors({ ...formErrors, postcode: undefined }); }}
                             placeholder="LS10 1AB"
                             testid="customer-form-postcode" />
                      {formErrors.postcode && (
                        <p className="mt-1 text-[11px] font-semibold text-rose-600" data-testid="customer-form-postcode-error">
                          <AlertTriangle size={10} className="inline mr-0.5" /> {formErrors.postcode}
                        </p>
                      )}
                    </div>
                    <Field label="Country" value={form.country}
                           onChange={(v) => setForm({ ...form, country: v })}
                           placeholder="United Kingdom"
                           testid="customer-form-country" />
                  </div>
                  <Field label="Access notes" multiline value={form.notes}
                         onChange={(v) => setForm({ ...form, notes: v })}
                         placeholder="Access via side gate. Manager: Sarah."
                         testid="customer-form-notes" />
                </div>
              )}

              {/* Step 3 — Equipment */}
              {wizardStep === 2 && (
                <div className="space-y-3" data-testid="customer-wizard-pane-equipment">
                  <div className="bg-cyan-50/60 border border-cyan-200 rounded-xl p-3">
                    <p className="text-[11px] font-bold uppercase tracking-wide text-cyan-700 mb-1">
                      Equipment
                    </p>
                    <p className="text-[11px] text-cyan-900/80">
                      Optional — paste a list now, or skip and add later from the customer's record.
                    </p>
                  </div>
                  <Field label="Equipment list (one per line)" multiline value={form.equipment_list}
                         onChange={(v) => setForm({ ...form, equipment_list: v })}
                         placeholder="Life Fitness 95Ti #1234&#10;Concept2 RowErg&#10;Wattbike Atom"
                         testid="customer-form-equipment" />
                  <div className="text-[11px] text-slate-500 flex items-start gap-2 leading-snug">
                    <Wrench size={12} className="mt-0.5 flex-shrink-0 text-slate-400" />
                    <span>
                      Need to import dozens of machines? Save this customer, then open the
                      customer's drawer and use <strong>Template</strong> + <strong>Import
                      equipment</strong> to upload them in bulk against this customer.
                    </span>
                  </div>
                </div>
              )}
            </div>
            <footer className="px-4 py-3 border-t border-slate-200 flex items-center justify-between gap-2 sticky bottom-0 bg-white">
              <button
                type="button"
                onClick={wizardStep === 0 ? close : goBack}
                className="px-4 py-2 rounded-lg border border-slate-300 text-sm font-bold"
                data-testid="customer-wizard-back"
              >
                {wizardStep === 0 ? 'Cancel' : 'Back'}
              </button>
              {wizardStep < WIZARD_STEPS.length - 1 ? (
                <button
                  type="button"
                  onClick={goNext}
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-cyan-600 text-white text-sm font-bold hover:bg-cyan-700"
                  data-testid="customer-wizard-next"
                >
                  Next <ChevronRight size={14} />
                </button>
              ) : (
                <button
                  type="button"
                  onClick={save}
                  disabled={saving}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gradient-to-br from-[#0891b2] to-[#0e7490] text-white text-sm font-bold disabled:opacity-50"
                  data-testid="customer-form-save"
                >
                  {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
                  {editId ? 'Update customer' : 'Save customer'}
                </button>
              )}
            </footer>
          </div>
        </div>
      ) : null}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────
// Iter 220cl — Per-customer equipment CSV (slim template, no Pulse-
// only columns). Lives on the customer-detail drawer so every
// imported row is auto-tagged with this customer's id by the
// backend, which is what makes ``/svc/engineer/equipment`` only
// surface customer-owned rows.
// ─────────────────────────────────────────────────────────────────────

function CustomerEquipmentCsv({ customer, onImported }) {
  const inputRef = useRef(null);
  const [busy, setBusy] = useState(false);

  const onDownload = async () => {
    try {
      const r = await axios.get(`${API}/svc/engineer/equipment/template-csv`, {
        ...auth(), responseType: 'blob',
      });
      const blob = new Blob([r.data], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `equipment-import-${customer.id}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      notify.success('Template downloaded');
    } catch (err) {
      notify.error('Could not download template',
                   err?.response?.data?.detail || err?.message);
    }
  };

  const onFileChosen = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) {
      notify.error('CSV too large (max 2 MB)');
      return;
    }
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const r = await axios.post(
        `${API}/svc/engineer/customers/${customer.id}/equipment/import-csv`,
        fd,
        {
          ...auth(),
          headers: { ...auth().headers, 'Content-Type': 'multipart/form-data' },
        },
      );
      const ins = r.data?.inserted || 0;
      const skip = r.data?.skipped || 0;
      notify.success(
        `Imported ${ins} machine${ins === 1 ? '' : 's'}` +
        (skip > 0 ? ` · ${skip} blank row${skip === 1 ? '' : 's'} skipped` : ''),
      );
      onImported?.();
    } catch (err) {
      const detail = err?.response?.data?.detail;
      notify.error('Import failed', Array.isArray(detail)
        ? detail.map((d) => d.msg || d.loc?.join('.')).join(', ')
        : (detail || err?.message));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={onDownload}
        className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-slate-700 text-xs font-bold"
        data-testid={`customer-csv-template-${customer.id}`}
      >
        <Download size={12} /> Template
      </button>
      <input
        ref={inputRef}
        type="file"
        accept=".csv,text/csv"
        className="hidden"
        onChange={onFileChosen}
        data-testid={`customer-csv-file-${customer.id}`}
      />
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={busy}
        className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-emerald-600 text-white text-xs font-bold disabled:opacity-50"
        data-testid={`customer-csv-import-${customer.id}`}
      >
        {busy
          ? <><Loader2 size={12} className="animate-spin" /> Importing…</>
          : <><Upload size={12} /> Import equipment</>}
      </button>
    </>
  );
}
