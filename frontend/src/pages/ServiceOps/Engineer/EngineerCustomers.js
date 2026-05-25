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
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import {
  ArrowLeft, Users, Plus, Search, Loader2, Mail, Phone, MapPin,
  Trash2, Edit3, Save, X, Wrench, FileText, CalendarClock,
  Receipt,
} from 'lucide-react';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const auth = () => ({
  headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
});

const EMPTY_FORM = {
  name: '', email: '', phone: '', site_name: '', site_address: '',
  notes: '', equipment_list: '',
};

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
        className="w-full mt-1 text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white text-slate-900 placeholder-slate-400 focus:border-blue-400 focus:outline-none"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        data-testid={testid}
      />
    ) : (
      <input
        type={type}
        className="w-full mt-1 text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white text-slate-900 placeholder-slate-400 focus:border-blue-400 focus:outline-none"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        data-testid={testid}
      />
    )}
  </label>
);

export default function EngineerCustomers() {
  const navigate = useNavigate();
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

  const openNew = () => {
    setForm(EMPTY_FORM);
    setEditId(null);
    setShowForm(true);
  };

  const openEdit = (row) => {
    setForm({
      name: row.name || '',
      email: row.email || '',
      phone: row.phone || '',
      site_name: row.site_name || '',
      site_address: row.site_address || '',
      notes: row.notes || '',
      equipment_list: (row.equipment_list || []).join('\n'),
    });
    setEditId(row.id);
    setShowForm(true);
  };

  const close = () => {
    setShowForm(false);
    setForm(EMPTY_FORM);
    setEditId(null);
  };

  const save = async () => {
    if (!form.name.trim()) {
      notify.error('Customer name is required');
      return;
    }
    setSaving(true);
    try {
      const payload = {
        name: form.name.trim(),
        email: form.email.trim() || null,
        phone: form.phone.trim() || null,
        site_name: form.site_name.trim() || null,
        site_address: form.site_address.trim() || null,
        notes: form.notes.trim() || null,
        equipment_list: form.equipment_list
          .split('\n').map((s) => s.trim()).filter(Boolean),
      };
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

  const handleToggleRow = async (row) => {
    if (activeId === row.id) {
      setActiveId(null);
      setActiveDetail(null);
      return;
    }
    setActiveId(row.id);
    setActiveDetail(null);
    setActiveDetailLoading(true);
    try {
      const r = await axios.get(`${API}/svc/engineer/customers/${row.id}`, auth());
      setActiveDetail(r.data);
    } catch (err) {
      notify.error('Failed to load customer history', err?.response?.data?.detail || err?.message);
    } finally {
      setActiveDetailLoading(false);
    }
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
            className="inline-flex items-center gap-1 px-3 py-2 rounded-lg bg-gradient-to-br from-[#1d4ed8] to-[#6366f1] text-white text-xs font-bold shadow"
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
              className="w-full bg-white border border-slate-200 focus:border-blue-400 rounded-lg pl-9 pr-3 py-2 text-sm focus:outline-none"
              data-testid="customers-search"
            />
          </div>
        </div>
      </header>

      <main className="max-w-3xl mx-auto p-4 space-y-3">
        {loading ? (
          <div className="flex items-center justify-center py-10">
            <Loader2 className="animate-spin text-blue-500" />
          </div>
        ) : rows.length === 0 ? (
          <div className="bg-white rounded-2xl border border-slate-200 p-8 text-center" data-testid="customers-empty">
            <Users size={28} className="mx-auto text-slate-300 mb-3" />
            <p className="font-bold text-slate-900">No customers yet</p>
            <p className="text-sm text-slate-500 mt-1">
              Add your first customer so you can auto-fill quotes & invoices.
            </p>
            <button
              type="button"
              onClick={openNew}
              className="mt-4 inline-flex items-center gap-1 px-4 py-2 rounded-lg bg-gradient-to-br from-[#1d4ed8] to-[#6366f1] text-white text-sm font-bold"
              data-testid="customers-empty-cta"
            >
              <Plus size={14} /> Add customer
            </button>
          </div>
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
                                    <span className="tabular-nums font-semibold">£{Number(qq.total || 0).toFixed(2)}</span>
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
                                    <span className="tabular-nums font-semibold">£{Number(inv.total || 0).toFixed(2)}</span>
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
                      </div>
                    ) : null}
                    <div className="flex flex-wrap gap-2 pt-2 border-t border-slate-100">
                      <button
                        type="button"
                        onClick={() => handleUseInQuote(row)}
                        className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-gradient-to-br from-[#1d4ed8] to-[#6366f1] text-white text-xs font-bold"
                        data-testid={`customer-use-quote-${row.id}`}
                      >
                        <FileText size={12} /> Use in quote
                      </button>
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
            <div className="p-4 space-y-3">
              <Field label="Name *" value={form.name}
                     onChange={(v) => setForm({ ...form, name: v })}
                     placeholder="Acme Gyms Ltd"
                     testid="customer-form-name" />
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <Field label="Email" type="email" value={form.email}
                       onChange={(v) => setForm({ ...form, email: v })}
                       placeholder="manager@acme.co.uk"
                       testid="customer-form-email" />
                <Field label="Phone" value={form.phone}
                       onChange={(v) => setForm({ ...form, phone: v })}
                       placeholder="+44 …"
                       testid="customer-form-phone" />
              </div>
              <Field label="Site name" value={form.site_name}
                     onChange={(v) => setForm({ ...form, site_name: v })}
                     placeholder="Acme Gym · Leeds"
                     testid="customer-form-site-name" />
              <Field label="Site address" multiline value={form.site_address}
                     onChange={(v) => setForm({ ...form, site_address: v })}
                     placeholder="12 Industrial Way, Leeds LS10 1AB"
                     testid="customer-form-site-address" />
              <Field label="Equipment list (one per line)" multiline value={form.equipment_list}
                     onChange={(v) => setForm({ ...form, equipment_list: v })}
                     placeholder="Life Fitness 95Ti #1234&#10;Concept2 RowErg"
                     testid="customer-form-equipment" />
              <Field label="Notes" multiline value={form.notes}
                     onChange={(v) => setForm({ ...form, notes: v })}
                     placeholder="Access via side gate. Manager: Sarah."
                     testid="customer-form-notes" />
            </div>
            <footer className="px-4 py-3 border-t border-slate-200 flex justify-end gap-2 sticky bottom-0 bg-white">
              <button
                type="button"
                onClick={close}
                className="px-4 py-2 rounded-lg border border-slate-300 text-sm font-bold"
                data-testid="customer-form-cancel"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={save}
                disabled={saving}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gradient-to-br from-[#1d4ed8] to-[#6366f1] text-white text-sm font-bold disabled:opacity-50"
                data-testid="customer-form-save"
              >
                {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
                {editId ? 'Update' : 'Save'}
              </button>
            </footer>
          </div>
        </div>
      ) : null}
    </div>
  );
}
