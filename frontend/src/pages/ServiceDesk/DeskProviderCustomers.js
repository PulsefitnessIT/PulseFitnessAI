/**
 * Provider-native desk Customers — Iter 256.
 *
 * For self-serve service providers, the desk "Customers" tab manages their
 * FIELD-SERVICE customer book (svc_engineer_customers — same data the
 * Engineer App and import wizard use), not platform organisations.
 * List/search → detail with recent cases → add/edit/delete.
 * Backed by /api/service-desk/provider-customers.
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import {
  Users, Search, Plus, Loader2, ArrowLeft, Pencil, Trash2, ClipboardList,
  PhoneCall, HardHat,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { authConfig } from './authConfig';

const FORM_FIELDS = [
  ['name', 'Customer name *'], ['email', 'Email'], ['phone', 'Phone'],
  ['site_name', 'Site name'], ['address_line1', 'Address line 1'],
  ['city', 'City / town'], ['postcode', 'Postcode'], ['notes', 'Notes'],
];
const EMPTY_FORM = Object.fromEntries(FORM_FIELDS.map(([k]) => [k, '']));

function CustomerForm({ initial, busy, onSave, onCancel, testid }) {
  const [form, setForm] = useState({ ...EMPTY_FORM, ...initial });
  return (
    <div className="space-y-3" data-testid={testid}>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {FORM_FIELDS.map(([k, label]) => (
          <div key={k} className={k === 'notes' ? 'sm:col-span-2' : ''}>
            <label className="block text-xs font-medium text-zinc-600 mb-1">{label}</label>
            <input value={form[k] || ''} onChange={(e) => setForm({ ...form, [k]: e.target.value })}
              className="w-full px-3 py-2 rounded-lg border border-zinc-200 text-sm outline-none focus:ring-2 focus:ring-orange-500"
              data-testid={`pc-form-${k}`} />
          </div>
        ))}
      </div>
      <div className="flex gap-2">
        <button onClick={onCancel} className="px-4 py-2 text-sm text-zinc-600 hover:text-zinc-900">Cancel</button>
        <button onClick={() => onSave(form)} disabled={busy || !form.name?.trim()}
          className="inline-flex items-center gap-2 bg-orange-500 hover:bg-orange-600 disabled:opacity-60 text-white text-sm font-semibold px-4 py-2 rounded-lg"
          data-testid="pc-form-save">
          {busy ? <Loader2 size={14} className="animate-spin" /> : 'Save'}
        </button>
      </div>
    </div>
  );
}

const STATUS_TONES = {
  closed: 'bg-zinc-100 text-zinc-600', invoiced: 'bg-emerald-50 text-emerald-700',
};

const PRIORITIES = [
  ['p1', 'P1 — Critical'], ['p2', 'P2 — High'], ['p3', 'P3 — Medium'], ['p4', 'P4 — Low'],
];

/** Iter 256b — "phone rings" flow: raise a case straight from the customer
 *  detail page with customer/site pre-filled (POST /svc/intake/phone).
 *  Iter 256d — after raising, offer one-click engineer dispatch
 *  (POST /svc/scheduler/assign) so call → case → engineer takes seconds. */
function NewCaseForm({ API, customer, onCreated, onCancel }) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState('p3');
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState(null);     // the raised case
  const [engineers, setEngineers] = useState([]);
  const [engineerId, setEngineerId] = useState('');

  const submit = async () => {
    setBusy(true);
    try {
      const r = await axios.post(`${API}/svc/intake/phone`, {
        title,
        description,
        priority,
        customer_name: customer.name || '',
        customer_email: customer.email || '',
        customer_phone: customer.phone || '',
        site_name: customer.site_name || '',
        site_postcode: customer.postcode || '',
      }, authConfig());
      notify.success('Case raised', r.data.reference || '');
      setCreated(r.data);
      try {
        const e = await axios.get(`${API}/svc/engineers`, authConfig());
        const active = (e.data.engineers || []).filter((x) => x.active !== false);
        setEngineers(active);
        if (active.length === 1) setEngineerId(active[0].id);
      } catch { setEngineers([]); }
    } catch (e) {
      notify.error('Could not raise case', e.response?.data?.detail || '');
    } finally { setBusy(false); }
  };

  const dispatch = async () => {
    setBusy(true);
    try {
      await axios.post(`${API}/svc/scheduler/assign`,
        { case_id: created.id, engineer_id: engineerId }, authConfig());
      const eng = engineers.find((e) => e.id === engineerId);
      notify.success('Engineer dispatched', `${created.reference} → ${eng?.full_name || 'engineer'}`);
      onCreated();
    } catch (e) {
      notify.error('Could not assign engineer', e.response?.data?.detail || '');
    } finally { setBusy(false); }
  };

  // ── Stage 2: dispatch ─────────────────────────────────────────
  if (created) {
    return (
      <Card className="p-6 space-y-3 border-emerald-200 bg-emerald-50/30" data-testid="pc-dispatch-form">
        <div className="text-sm font-semibold text-zinc-900">
          <span className="font-mono text-emerald-700">{created.reference}</span> raised — dispatch an engineer?
        </div>
        {engineers.length === 0 ? (
          <div className="text-xs text-zinc-500" data-testid="pc-dispatch-empty">
            No active engineers yet — assign later from the Cases board.
          </div>
        ) : (
          <select value={engineerId} onChange={(e) => setEngineerId(e.target.value)}
            className="w-full sm:w-72 px-3 py-2 rounded-lg border border-zinc-200 text-sm bg-white"
            data-testid="pc-dispatch-engineer">
            <option value="">Choose an engineer…</option>
            {engineers.map((e) => (
              <option key={e.id} value={e.id}>{e.full_name}</option>
            ))}
          </select>
        )}
        <div className="flex gap-2 justify-end">
          <button onClick={onCreated} className="px-4 py-2 text-sm text-zinc-600 hover:text-zinc-900"
            data-testid="pc-dispatch-later">
            Assign later
          </button>
          {engineers.length > 0 && (
            <button onClick={dispatch} disabled={busy || !engineerId}
              className="inline-flex items-center gap-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white text-sm font-semibold px-4 py-2 rounded-lg"
              data-testid="pc-dispatch-assign">
              {busy ? <Loader2 size={14} className="animate-spin" /> : <HardHat size={14} />} Dispatch
            </button>
          )}
        </div>
      </Card>
    );
  }

  // ── Stage 1: raise ────────────────────────────────────────────
  return (
    <Card className="p-6 space-y-3 border-orange-200 bg-orange-50/30" data-testid="pc-new-case-form">
      <div className="text-sm font-semibold text-zinc-900">
        New case for {customer.name}
        <span className="ml-2 text-xs font-normal text-zinc-500">
          {[customer.site_name, customer.postcode].filter(Boolean).join(' · ') || 'no site on record'}
        </span>
      </div>
      <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="What's the fault? *"
        className="w-full px-3 py-2 rounded-lg border border-zinc-200 text-sm outline-none focus:ring-2 focus:ring-orange-500 bg-white"
        data-testid="pc-case-title" />
      <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3}
        placeholder="Details (what the caller said, machine, symptoms…)"
        className="w-full px-3 py-2 rounded-lg border border-zinc-200 text-sm outline-none focus:ring-2 focus:ring-orange-500 bg-white"
        data-testid="pc-case-description" />
      <div className="flex items-center gap-3 flex-wrap">
        <select value={priority} onChange={(e) => setPriority(e.target.value)}
          className="px-3 py-2 rounded-lg border border-zinc-200 text-sm bg-white"
          data-testid="pc-case-priority">
          {PRIORITIES.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
        </select>
        <div className="flex gap-2 ml-auto">
          <button onClick={onCancel} className="px-4 py-2 text-sm text-zinc-600 hover:text-zinc-900">Cancel</button>
          <button onClick={submit} disabled={busy || !title.trim()}
            className="inline-flex items-center gap-2 bg-orange-500 hover:bg-orange-600 disabled:opacity-60 text-white text-sm font-semibold px-4 py-2 rounded-lg"
            data-testid="pc-case-submit">
            {busy ? <Loader2 size={14} className="animate-spin" /> : <PhoneCall size={14} />} Raise case
          </button>
        </div>
      </div>
    </Card>
  );
}

export default function DeskProviderCustomers({ API }) {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [q, setQ] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState(false);
  const [raisingCase, setRaisingCase] = useState(false);
  const [detail, setDetail] = useState(null); // {customer, recent_cases, case_count}

  const load = useCallback(async (search = '') => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/service-desk/provider-customers`,
        { ...authConfig(), params: { q: search, limit: 100 } });
      setRows(r.data.customers);
      setTotal(r.data.total);
    } catch (e) {
      notify.error('Could not load customers', e.response?.data?.detail || '');
    } finally { setLoading(false); }
  }, [API]);

  useEffect(() => { load(); }, [load]);

  const openDetail = async (id) => {
    try {
      const r = await axios.get(`${API}/service-desk/provider-customers/${id}`, authConfig());
      setDetail(r.data);
      setEditing(false);
      setRaisingCase(false);
    } catch (e) { notify.error('Could not load customer', e.response?.data?.detail || ''); }
  };

  const create = async (form) => {
    setBusy(true);
    try {
      await axios.post(`${API}/service-desk/provider-customers`, form, authConfig());
      notify.success('Customer added', form.name);
      setAdding(false);
      load(q);
    } catch (e) { notify.error('Could not add customer', e.response?.data?.detail || ''); }
    finally { setBusy(false); }
  };

  const update = async (form) => {
    setBusy(true);
    try {
      const r = await axios.patch(
        `${API}/service-desk/provider-customers/${detail.customer.id}`, form, authConfig());
      setDetail({ ...detail, customer: r.data.customer });
      setEditing(false);
      notify.success('Customer updated', r.data.customer.name);
      load(q);
    } catch (e) { notify.error('Could not update customer', e.response?.data?.detail || ''); }
    finally { setBusy(false); }
  };

  const remove = async () => {
    if (!window.confirm(`Delete ${detail.customer.name}? Their case history stays intact.`)) return;
    setBusy(true);
    try {
      await axios.delete(`${API}/service-desk/provider-customers/${detail.customer.id}`, authConfig());
      notify.success('Customer deleted', detail.customer.name);
      setDetail(null);
      load(q);
    } catch (e) { notify.error('Could not delete customer', e.response?.data?.detail || ''); }
    finally { setBusy(false); }
  };

  // ── Detail view ─────────────────────────────────────────────────
  if (detail) {
    const c = detail.customer;
    return (
      <div className="space-y-5 max-w-3xl" data-testid="pc-detail">
        <button onClick={() => setDetail(null)}
          className="inline-flex items-center gap-1.5 text-sm text-zinc-600 hover:text-zinc-900"
          data-testid="pc-back">
          <ArrowLeft size={14} /> All customers
        </button>
        <Card className="p-6 space-y-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-xl font-semibold text-zinc-900" data-testid="pc-detail-name">{c.name}</h2>
              <div className="text-sm text-zinc-500 mt-0.5">
                {[c.email, c.phone].filter(Boolean).join(' · ') || 'No contact details'}
              </div>
            </div>
            {!editing && (
              <div className="flex gap-2">
                <button onClick={() => setRaisingCase(true)}
                  className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg bg-orange-500 hover:bg-orange-600 text-white"
                  data-testid="pc-new-case">
                  <PhoneCall size={12} /> New case
                </button>
                <button onClick={() => setEditing(true)}
                  className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg border border-zinc-200 hover:bg-zinc-50 text-zinc-700"
                  data-testid="pc-edit">
                  <Pencil size={12} /> Edit
                </button>
                <button onClick={remove} disabled={busy}
                  className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg border border-red-200 hover:bg-red-50 text-red-600"
                  data-testid="pc-delete">
                  <Trash2 size={12} /> Delete
                </button>
              </div>
            )}
          </div>
          {editing ? (
            <CustomerForm initial={c} busy={busy} onSave={update} onCancel={() => setEditing(false)} testid="pc-edit-form" />
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm">
              {[['Site', c.site_name], ['Address', [c.address_line1, c.city].filter(Boolean).join(', ')],
                ['Postcode', c.postcode], ['Source', c.source || 'manual'],
                ['Notes', c.notes]].map(([label, v]) => (
                <div key={label}>
                  <div className="text-[11px] uppercase tracking-wide text-zinc-400 font-semibold">{label}</div>
                  <div className="text-zinc-800">{v || '—'}</div>
                </div>
              ))}
            </div>
          )}
        </Card>

        {raisingCase && (
          <NewCaseForm API={API} customer={c}
            onCreated={() => openDetail(c.id)}
            onCancel={() => setRaisingCase(false)} />
        )}


        <Card className="p-6" data-testid="pc-cases">
          <div className="flex items-center gap-2 mb-3">
            <ClipboardList size={15} className="text-zinc-500" />
            <div className="text-sm font-medium text-zinc-900">
              Cases <span className="text-zinc-400">({detail.case_count})</span>
            </div>
          </div>
          {detail.recent_cases.length === 0 ? (
            <div className="text-sm text-zinc-500">No cases yet for this customer.</div>
          ) : (
            <div className="divide-y divide-zinc-50">
              {detail.recent_cases.map((cs) => (
                <div key={cs.id} className="py-2 flex items-center gap-3 text-sm" data-testid={`pc-case-${cs.reference}`}>
                  <span className="font-mono text-xs text-zinc-500 shrink-0">{cs.reference}</span>
                  <span className="flex-1 text-zinc-800 truncate">{cs.title}</span>
                  <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${STATUS_TONES[cs.status] || 'bg-sky-50 text-sky-700'}`}>
                    {cs.status}
                  </span>
                  <span className="text-xs text-zinc-400 shrink-0">{(cs.created_at || '').slice(0, 10)}</span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    );
  }

  // ── List view ───────────────────────────────────────────────────
  return (
    <div className="space-y-5" data-testid="pc-list">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-900">Customers</h1>
          <p className="text-sm text-zinc-500 mt-1">
            Your customer book — shared with the Engineer App and the import wizard.
          </p>
        </div>
        <button onClick={() => setAdding(true)}
          className="inline-flex items-center gap-2 bg-orange-500 hover:bg-orange-600 text-white text-sm font-semibold px-4 py-2 rounded-lg"
          data-testid="pc-add">
          <Plus size={15} /> Add customer
        </button>
      </div>

      {adding && (
        <Card className="p-6">
          <div className="text-sm font-semibold text-zinc-900 mb-3">New customer</div>
          <CustomerForm busy={busy} onSave={create} onCancel={() => setAdding(false)} testid="pc-add-form" />
        </Card>
      )}

      <div className="relative max-w-sm">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400" />
        <input value={q}
          onChange={(e) => { setQ(e.target.value); load(e.target.value); }}
          placeholder="Search name, email, site, postcode…"
          className="w-full pl-8 pr-3 py-2 rounded-lg border border-zinc-200 text-sm outline-none focus:ring-2 focus:ring-orange-500"
          data-testid="pc-search" />
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-16 text-zinc-500 text-sm" data-testid="pc-loading">
          <Loader2 size={16} className="mr-2 animate-spin" /> Loading customers…
        </div>
      ) : rows.length === 0 ? (
        <Card className="p-10 text-center" data-testid="pc-empty">
          <Users className="mx-auto text-zinc-300 mb-2" size={26} />
          <div className="text-sm text-zinc-600 font-medium">No customers yet</div>
          <div className="text-xs text-zinc-400 mt-1">
            Add one above, or bring your whole book over with <span className="font-semibold">Import data</span>.
          </div>
        </Card>
      ) : (
        <Card className="overflow-hidden">
          <div className="px-4 py-2 text-[11px] text-zinc-400 border-b border-zinc-100" data-testid="pc-total">
            {total.toLocaleString()} customer{total === 1 ? '' : 's'}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-zinc-50 text-zinc-500 text-xs">
                <tr>
                  {['Name', 'Contact', 'Site', 'Postcode', 'Added'].map((h) => (
                    <th key={h} className="text-left px-4 py-2 font-semibold whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-50">
                {rows.map((c) => (
                  <tr key={c.id} onClick={() => openDetail(c.id)}
                    className="hover:bg-orange-50/40 cursor-pointer transition-colors"
                    data-testid={`pc-row-${c.id}`}>
                    <td className="px-4 py-2.5 font-medium text-zinc-900 whitespace-nowrap">{c.name}</td>
                    <td className="px-4 py-2.5 text-zinc-600 whitespace-nowrap">{c.email || c.phone || '—'}</td>
                    <td className="px-4 py-2.5 text-zinc-600 whitespace-nowrap">{c.site_name || '—'}</td>
                    <td className="px-4 py-2.5 text-zinc-600 whitespace-nowrap">{c.postcode || '—'}</td>
                    <td className="px-4 py-2.5 text-zinc-400 text-xs whitespace-nowrap">{(c.created_at || '').slice(0, 10)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
