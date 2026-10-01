/**
 * EngineerExpenses — Iter 278
 *
 * Mobile-first expenses for field engineers: scan a receipt (AI OCR),
 * add a manual expense, or log a mileage claim — each can link to a
 * job / customer / site / vehicle. Drafts can be saved or submitted for
 * approval. Solo (independent) engineers auto-approve their own claims.
 *
 * Backend: /api/expenses/* (config, ocr, CRUD, submit, dashboard).
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import {
  ArrowLeft, Camera, Plus, Car, Loader2, Receipt,
  AlertTriangle, Wallet, Send, Save, ScanLine, Trash2, Pencil,
} from 'lucide-react';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = (extra = {}) => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}`, ...extra } });

const CCY = { GBP: '£', USD: '$', EUR: '€', CAD: 'C$', AUD: 'A$' };
const sym = (c) => CCY[c] || (c ? `${c} ` : '£');
const fmtDate = (iso) => {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }); }
  catch { return String(iso).slice(0, 10); }
};
const todayISO = () => new Date().toISOString().slice(0, 10);

const STATUS_STYLE = {
  draft: 'bg-slate-100 text-slate-600',
  submitted: 'bg-amber-100 text-amber-700',
  needs_details: 'bg-orange-100 text-orange-700',
  approved: 'bg-emerald-100 text-emerald-700',
  rejected: 'bg-red-100 text-red-700',
  exported: 'bg-cyan-100 text-cyan-700',
  reimbursed: 'bg-emerald-600 text-white',
  cancelled: 'bg-slate-200 text-slate-400 line-through',
};
const StatusPill = ({ status }) => (
  <span className={`text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full ${STATUS_STYLE[status] || 'bg-slate-100 text-slate-600'}`}>
    {String(status || '').replace('_', ' ')}
  </span>
);

// Authed receipt thumbnail — fetched as a blob (Bearer/cookie) then shown
// as an object URL. Handles PDFs (no preview) gracefully.
function ReceiptThumb({ expenseId, index = 0, className = '' }) {
  const [url, setUrl] = useState(null);
  const [err, setErr] = useState(false);
  useEffect(() => {
    let revoke;
    let alive = true;
    (async () => {
      try {
        const res = await axios.get(`${API}/expenses/${expenseId}/receipt?i=${index}`, { ...auth(), responseType: 'blob' });
        if (!alive) return;
        if ((res.data.type || '').startsWith('image/')) {
          const u = URL.createObjectURL(res.data); revoke = u; setUrl(u);
        } else { setErr(true); }
      } catch { if (alive) setErr(true); }
    })();
    return () => { alive = false; if (revoke) URL.revokeObjectURL(revoke); };
  }, [expenseId, index]);
  if (err) return (
    <div className={`flex items-center justify-center bg-slate-100 text-slate-400 ${className}`} data-testid={`exp-receipt-thumb-${expenseId}`}><Receipt size={18} /></div>
  );
  if (!url) return <div className={`bg-slate-100 animate-pulse ${className}`} />;
  return <img src={url} alt="Receipt" className={`object-cover ${className}`} data-testid={`exp-receipt-thumb-${expenseId}`} />;
}

const Field = ({ label, children }) => (
  <label className="block">
    <span className="text-[11px] font-bold uppercase tracking-wide text-slate-500">{label}</span>
    <div className="mt-1">{children}</div>
  </label>
);
const inputCls = 'w-full text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white text-slate-900 placeholder-slate-400 focus:border-orange-400 focus:outline-none';

const EMPTY = {
  expense_type: 'manual', category_id: '', category_name: '', merchant: '',
  transaction_date: todayISO(), gross_amount: '', tax_amount: '', tax_rate: '',
  payment_method: '', description: '', business_purpose: '', job_id: '',
  job_reference: '', customer_id: '', customer_name: '', site_id: '', site_name: '',
  vehicle_id: '', billable_to_customer: false, receipt_paths: [], country_code: '',
  currency: '', ocr_confidence: null,
  mileage: { start_location: '', end_location: '', return_journey: false, distance: '', unit: 'mi', vehicle_type: 'personal_car', rate: 0, calculated_amount: 0, business_reason: '' },
};

export default function EngineerExpenses() {
  const navigate = useNavigate();
  const fileRef = useRef(null);
  const [cfg, setCfg] = useState(null);
  const [stats, setStats] = useState(null);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [view, setView] = useState('list'); // list | form
  const [form, setForm] = useState(EMPTY);
  const [editId, setEditId] = useState(null);
  const [reviewNote, setReviewNote] = useState('');
  const [saving, setSaving] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [warnings, setWarnings] = useState([]);

  const ccy = cfg?.currency || 'GBP';
  const rule = (cfg?.country_rules || []).find((r) => r.country_code === (form.country_code || cfg?.default_country_code)) || (cfg?.country_rules || [])[0] || {};

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [c, d, l] = await Promise.all([
        axios.get(`${API}/expenses/config`, auth()),
        axios.get(`${API}/expenses/dashboard`, auth()),
        axios.get(`${API}/expenses?status=${filter === 'all' ? 'all' : filter}`, auth()),
      ]);
      setCfg(c.data); setStats(d.data?.me || {}); setRows(l.data?.expenses || []);
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Failed to load expenses');
    } finally { setLoading(false); }
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  const openNew = (type) => {
    setWarnings([]); setEditId(null); setReviewNote('');
    setForm({ ...EMPTY, expense_type: type, transaction_date: todayISO(),
      country_code: cfg?.default_country_code || '', currency: cfg?.currency || '',
      mileage: { ...EMPTY.mileage, unit: rule.mileage_unit || 'mi' } });
    setView('form');
    if (type === 'receipt') setTimeout(() => fileRef.current?.click(), 100);
  };

  const openEdit = (e) => {
    setWarnings([]); setEditId(e.id); setReviewNote(e.status === 'needs_details' ? (e.review_note || '') : '');
    setForm({
      ...EMPTY, ...e,
      gross_amount: e.gross_amount != null ? String(e.gross_amount) : '',
      tax_amount: e.tax_amount != null ? String(e.tax_amount) : '',
      tax_rate: e.tax_rate != null ? String(e.tax_rate) : '',
      mileage: e.mileage
        ? { ...EMPTY.mileage, ...e.mileage, distance: e.mileage.distance != null ? String(e.mileage.distance) : '' }
        : { ...EMPTY.mileage, unit: rule.mileage_unit || 'mi' },
    });
    setView('form');
  };

  const onScan = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    setScanning(true); setWarnings([]);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const { data } = await axios.post(`${API}/expenses/ocr`, fd, auth({ 'Content-Type': 'multipart/form-data' }));
      const ex = data.extracted || {};
      setForm((f) => ({
        ...f, expense_type: 'receipt',
        receipt_paths: data.receipt_path ? [data.receipt_path] : [],
        merchant: ex.merchant_name || f.merchant,
        transaction_date: ex.date || f.transaction_date,
        gross_amount: ex.total_amount ? String(ex.total_amount) : f.gross_amount,
        tax_amount: ex.tax_amount ? String(ex.tax_amount) : f.tax_amount,
        tax_rate: ex.tax_rate ? String(ex.tax_rate) : f.tax_rate,
        payment_method: ex.payment_method || f.payment_method,
        ocr_confidence: ex.confidence ?? null,
        category_name: ex.category_suggestion || f.category_name,
      }));
      setWarnings(data.warnings || []);
      if (!(data.warnings || []).length) notify.success('Receipt scanned');
    } catch (err) {
      notify.error(err?.response?.data?.detail || 'Scan failed — enter details manually');
    } finally { setScanning(false); }
  };

  // Mileage live calc
  const recalcMileage = (m) => {
    const r = (rule.mileage_rates || []).find((x) => x.type === m.vehicle_type);
    const rate = r ? r.rate : 0;
    const dist = parseFloat(m.distance) || 0;
    const amt = +(dist * rate * (m.return_journey ? 2 : 1)).toFixed(2);
    return { ...m, rate, calculated_amount: amt };
  };
  const setMileage = (patch) => setForm((f) => ({ ...f, mileage: recalcMileage({ ...f.mileage, ...patch }) }));

  const pickCategory = (id) => {
    const cat = (cfg?.categories || []).find((c) => c.id === id);
    setForm((f) => ({ ...f, category_id: id, category_name: cat?.name || '', billable_to_customer: cat?.billable_to_customer ?? f.billable_to_customer }));
  };
  const pickJob = (id) => {
    const j = (cfg?.recent_jobs || []).find((x) => x.id === id);
    setForm((f) => ({ ...f, job_id: id, job_reference: j?.reference || '', customer_name: j?.customer_name || f.customer_name, site_name: j?.site_name || f.site_name }));
  };

  const save = async (submit) => {
    if (form.expense_type !== 'mileage' && !(parseFloat(form.gross_amount) > 0)) {
      notify.error('Enter an amount'); return;
    }
    if (form.expense_type === 'mileage' && !(parseFloat(form.mileage.distance) > 0)) {
      notify.error('Enter a distance'); return;
    }
    setSaving(true);
    try {
      const payload = {
        ...form, submit,
        gross_amount: parseFloat(form.gross_amount) || 0,
        tax_amount: parseFloat(form.tax_amount) || 0,
        tax_rate: parseFloat(form.tax_rate) || 0,
        mileage: form.expense_type === 'mileage'
          ? { ...form.mileage, distance: parseFloat(form.mileage.distance) || 0 }
          : null,
      };
      if (editId) {
        await axios.put(`${API}/expenses/${editId}`, payload, auth());
        notify.success(submit ? 'Expense resubmitted' : 'Changes saved');
      } else {
        await axios.post(`${API}/expenses`, payload, auth());
        notify.success(submit ? (cfg?.approval_mode === 'off' ? 'Expense saved & approved' : 'Expense submitted') : 'Draft saved');
      }
      setView('list'); setEditId(null); await load();
    } catch (err) {
      notify.error(err?.response?.data?.detail || 'Could not save');
    } finally { setSaving(false); }
  };

  const submitExisting = async (id) => {
    try { await axios.post(`${API}/expenses/${id}/submit`, {}, auth()); notify.success('Submitted'); load(); }
    catch (e) { notify.error(e?.response?.data?.detail || 'Submit failed'); }
  };
  const cancelExisting = async (id) => {
    if (!window.confirm('Cancel this expense?')) return;
    try { await axios.post(`${API}/expenses/${id}/cancel`, {}, auth()); notify.success('Cancelled'); load(); }
    catch (e) { notify.error(e?.response?.data?.detail || 'Cancel failed'); }
  };

  const FILTERS = [
    { id: 'all', label: 'All' },
    { id: 'draft', label: 'Drafts' },
    { id: 'submitted', label: 'Submitted' },
    { id: 'approved', label: 'Approved' },
    { id: 'reimbursed', label: 'Paid' },
  ];

  // ── Entry form view ──────────────────────────────────────────────
  if (view === 'form') {
    const isMileage = form.expense_type === 'mileage';
    return (
      <div className="min-h-screen bg-slate-50 pb-10" data-testid="engineer-expenses-form">
        <header className="sticky top-0 z-10 bg-white border-b border-slate-200 px-4 py-3 flex items-center gap-3">
          <button onClick={() => { setView('list'); setEditId(null); }} className="text-slate-500" data-testid="exp-form-back" aria-label="Back"><ArrowLeft size={20} /></button>
          <h1 className="text-base font-bold text-slate-900">
            {editId ? 'Edit expense' : isMileage ? 'Mileage claim' : form.expense_type === 'receipt' ? 'Receipt expense' : 'New expense'}
          </h1>
        </header>

        <input ref={fileRef} type="file" accept="image/*,application/pdf" capture="environment" className="hidden" onChange={onScan} data-testid="exp-file-input" />

        <div className="p-4 space-y-4 max-w-xl mx-auto">
          {reviewNote && (
            <div className="rounded-lg bg-orange-50 border border-orange-200 p-3" data-testid="exp-review-banner">
              <p className="text-[11px] font-bold uppercase tracking-wide text-orange-600">Finance needs more detail</p>
              <p className="text-sm text-orange-800 mt-0.5">“{reviewNote}”</p>
            </div>
          )}
          {/* type switch */}
          <div className="flex gap-2 text-xs">
            {['manual', 'receipt', 'mileage'].map((t) => (
              <button key={t} onClick={() => setForm((f) => ({ ...f, expense_type: t }))}
                className={`flex-1 py-2 rounded-lg font-semibold capitalize ${form.expense_type === t ? 'bg-orange-500 text-white' : 'bg-white border border-slate-200 text-slate-600'}`}
                data-testid={`exp-type-${t}`}>{t}</button>
            ))}
          </div>

          {form.expense_type === 'receipt' && (
            <button onClick={() => fileRef.current?.click()} disabled={scanning}
              className="w-full flex items-center justify-center gap-2 py-3 rounded-lg border-2 border-dashed border-orange-300 bg-orange-50 text-orange-700 font-semibold text-sm"
              data-testid="exp-rescan">
              {scanning ? <Loader2 size={18} className="animate-spin" /> : <ScanLine size={18} />}
              {form.receipt_paths.length ? 'Re-scan receipt' : 'Scan / upload receipt'}
            </button>
          )}

          {editId && (form.receipt_paths || []).length > 0 && (
            <ReceiptThumb expenseId={editId} className="w-full max-h-56 rounded-lg border border-slate-200" />
          )}

          {warnings.length > 0 && (
            <div className="rounded-lg bg-amber-50 border border-amber-200 p-3 space-y-1" data-testid="exp-warnings">
              {warnings.map((w, i) => (
                <p key={i} className="text-xs text-amber-800 flex gap-1.5"><AlertTriangle size={13} className="mt-0.5 shrink-0" />{w}</p>
              ))}
            </div>
          )}

          {isMileage ? (
            <div className="space-y-3">
              <Field label="From"><input className={inputCls} value={form.mileage.start_location} onChange={(e) => setMileage({ start_location: e.target.value })} placeholder="Home / depot" data-testid="exp-mileage-from" /></Field>
              <Field label="To"><input className={inputCls} value={form.mileage.end_location} onChange={(e) => setMileage({ end_location: e.target.value })} placeholder="Customer site" data-testid="exp-mileage-to" /></Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label={`Distance (${form.mileage.unit})`}><input type="number" className={inputCls} value={form.mileage.distance} onChange={(e) => setMileage({ distance: e.target.value })} data-testid="exp-mileage-distance" /></Field>
                <Field label="Vehicle">
                  <select className={inputCls} value={form.mileage.vehicle_type} onChange={(e) => setMileage({ vehicle_type: e.target.value })} data-testid="exp-mileage-vehicle">
                    {(rule.mileage_rates || []).map((m) => <option key={m.type} value={m.type}>{m.label}</option>)}
                  </select>
                </Field>
              </div>
              <label className="flex items-center gap-2 text-sm text-slate-700">
                <input type="checkbox" checked={form.mileage.return_journey} onChange={(e) => setMileage({ return_journey: e.target.checked })} data-testid="exp-mileage-return" />
                Return journey (double the distance)
              </label>
              <div className="rounded-lg bg-emerald-50 border border-emerald-200 p-3 flex items-center justify-between" data-testid="exp-mileage-amount">
                <span className="text-xs text-emerald-700 font-semibold">Claim @ {form.mileage.rate}/{form.mileage.unit}</span>
                <span className="text-xl font-bold text-emerald-800">{sym(ccy)}{(form.mileage.calculated_amount || 0).toFixed(2)}</span>
              </div>
              <Field label="Reason"><input className={inputCls} value={form.mileage.business_reason} onChange={(e) => setMileage({ business_reason: e.target.value })} placeholder="Why this trip?" data-testid="exp-mileage-reason" /></Field>
            </div>
          ) : (
            <div className="space-y-3">
              <Field label="Category">
                <select className={inputCls} value={form.category_id} onChange={(e) => pickCategory(e.target.value)} data-testid="exp-category">
                  <option value="">Select…</option>
                  {(cfg?.categories || []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </Field>
              <Field label="Merchant"><input className={inputCls} value={form.merchant} onChange={(e) => setForm((f) => ({ ...f, merchant: e.target.value }))} placeholder="Where did you spend?" data-testid="exp-merchant" /></Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Date"><input type="date" className={inputCls} value={form.transaction_date} onChange={(e) => setForm((f) => ({ ...f, transaction_date: e.target.value }))} data-testid="exp-date" /></Field>
                <Field label={`Amount (${sym(ccy)})`}><input type="number" className={inputCls} value={form.gross_amount} onChange={(e) => setForm((f) => ({ ...f, gross_amount: e.target.value }))} data-testid="exp-amount" /></Field>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Field label={`${rule.tax_label || 'Tax'} amount`}><input type="number" className={inputCls} value={form.tax_amount} onChange={(e) => setForm((f) => ({ ...f, tax_amount: e.target.value }))} data-testid="exp-tax" /></Field>
                <Field label="Payment"><input className={inputCls} value={form.payment_method} onChange={(e) => setForm((f) => ({ ...f, payment_method: e.target.value }))} placeholder="Card / cash" data-testid="exp-payment" /></Field>
              </div>
            </div>
          )}

          {/* shared: job link + description */}
          <Field label="Link to job (optional)">
            <select className={inputCls} value={form.job_id} onChange={(e) => pickJob(e.target.value)} data-testid="exp-job">
              <option value="">No job</option>
              {(cfg?.recent_jobs || []).map((j) => <option key={j.id} value={j.id}>{j.reference} — {j.title || j.customer_name || 'Job'}</option>)}
            </select>
          </Field>
          <Field label="Notes"><textarea rows={2} className={inputCls} value={form.description} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} placeholder="Anything finance should know" data-testid="exp-notes" /></Field>
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input type="checkbox" checked={form.billable_to_customer} onChange={(e) => setForm((f) => ({ ...f, billable_to_customer: e.target.checked }))} data-testid="exp-billable" />
            Billable to customer
          </label>

          <div className="flex gap-2 pt-2">
            {editId && form.status === 'submitted' ? (
              <button onClick={() => save(false)} disabled={saving}
                className="flex-1 flex items-center justify-center gap-2 py-3 rounded-lg bg-orange-500 text-white font-semibold text-sm" data-testid="exp-save-changes">
                {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />} Save changes
              </button>
            ) : (
              <>
                <button onClick={() => save(false)} disabled={saving}
                  className="flex-1 flex items-center justify-center gap-2 py-3 rounded-lg border border-slate-300 text-slate-700 font-semibold text-sm" data-testid="exp-save-draft">
                  {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />} Save draft
                </button>
                <button onClick={() => save(true)} disabled={saving}
                  className="flex-1 flex items-center justify-center gap-2 py-3 rounded-lg bg-orange-500 text-white font-semibold text-sm" data-testid="exp-submit">
                  {saving ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
                  {cfg?.approval_mode === 'off' ? 'Save & approve' : 'Submit'}
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    );
  }

  // ── List view ────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-slate-50 pb-10" data-testid="engineer-expenses">
      <header className="sticky top-0 z-10 bg-white border-b border-slate-200 px-4 py-3 flex items-center gap-3">
        <button onClick={() => navigate('/svc/engineer')} className="text-slate-500" data-testid="exp-back" aria-label="Back"><ArrowLeft size={20} /></button>
        <Wallet size={20} className="text-orange-500" />
        <h1 className="text-base font-bold text-slate-900">Expenses</h1>
      </header>

      {/* stat strip */}
      <div className="px-4 pt-4 grid grid-cols-3 gap-2">
        <div className="bg-white rounded-xl p-3 border border-slate-100" data-testid="exp-stat-month">
          <p className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold">This month</p>
          <p className="text-lg font-bold text-slate-900">{sym(ccy)}{(stats?.month_total || 0).toFixed(0)}</p>
        </div>
        <div className="bg-white rounded-xl p-3 border border-slate-100" data-testid="exp-stat-pending">
          <p className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold">Awaiting</p>
          <p className="text-lg font-bold text-amber-600">{(stats?.submitted || 0) + (stats?.needs_details || 0)}</p>
        </div>
        <div className="bg-white rounded-xl p-3 border border-slate-100" data-testid="exp-stat-mileage">
          <p className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold">Mileage</p>
          <p className="text-lg font-bold text-slate-900">{sym(ccy)}{(stats?.mileage_total || 0).toFixed(0)}</p>
        </div>
      </div>

      {/* actions */}
      <div className="px-4 pt-4 grid grid-cols-3 gap-2">
        <button onClick={() => openNew('receipt')} className="flex flex-col items-center gap-1 py-3 rounded-xl bg-orange-500 text-white font-semibold text-xs" data-testid="exp-action-scan"><Camera size={20} /> Scan receipt</button>
        <button onClick={() => openNew('manual')} className="flex flex-col items-center gap-1 py-3 rounded-xl bg-white border border-slate-200 text-slate-700 font-semibold text-xs" data-testid="exp-action-manual"><Plus size={20} /> Manual</button>
        <button onClick={() => openNew('mileage')} className="flex flex-col items-center gap-1 py-3 rounded-xl bg-white border border-slate-200 text-slate-700 font-semibold text-xs" data-testid="exp-action-mileage"><Car size={20} /> Mileage</button>
      </div>

      {/* filters */}
      <div className="px-4 pt-4 flex gap-2 overflow-x-auto">
        {FILTERS.map((f) => (
          <button key={f.id} onClick={() => setFilter(f.id)}
            className={`shrink-0 text-xs font-semibold px-3 py-1.5 rounded-full ${filter === f.id ? 'bg-slate-900 text-white' : 'bg-white border border-slate-200 text-slate-600'}`}
            data-testid={`exp-filter-${f.id}`}>{f.label}</button>
        ))}
      </div>

      {/* list */}
      <div className="px-4 pt-3 space-y-2">
        {loading ? (
          <div className="flex justify-center py-16 text-slate-400"><Loader2 className="animate-spin" /></div>
        ) : rows.length === 0 ? (
          <div className="text-center py-16 text-slate-400" data-testid="exp-empty">
            <Receipt size={40} className="mx-auto mb-2 opacity-40" />
            <p className="text-sm">No expenses yet. Scan a receipt to get started.</p>
          </div>
        ) : rows.map((e) => {
          const editable = e.status === 'draft' || e.status === 'needs_details';
          const canEdit = editable || e.status === 'submitted';
          const hasReceipt = (e.receipt_paths || []).length > 0;
          return (
          <div key={e.id} className="bg-white rounded-xl border border-slate-100 p-3" data-testid={`exp-row-${e.id}`}>
            <button onClick={() => canEdit ? openEdit(e) : null} className={`w-full text-left flex items-center gap-3 ${canEdit ? '' : 'cursor-default'}`} data-testid={`exp-open-${e.id}`}>
              {hasReceipt ? (
                <ReceiptThumb expenseId={e.id} className="w-11 h-11 rounded-lg shrink-0" />
              ) : (
                <div className="w-11 h-11 rounded-lg bg-slate-50 flex items-center justify-center shrink-0 text-slate-300">
                  {e.expense_type === 'mileage' ? <Car size={18} /> : <Receipt size={18} />}
                </div>
              )}
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-bold text-slate-900 truncate">{e.merchant || e.category_name || (e.expense_type === 'mileage' ? 'Mileage' : 'Expense')}</span>
                </div>
                <p className="text-[11px] text-slate-400">{e.reference} · {fmtDate(e.transaction_date)}{e.job_reference ? ` · ${e.job_reference}` : ''}</p>
              </div>
              <div className="text-right shrink-0">
                <p className="text-sm font-bold text-slate-900">{sym(e.currency || ccy)}{(e.gross_amount || 0).toFixed(2)}</p>
                <StatusPill status={e.status} />
              </div>
            </button>
            {canEdit && (
              <div className="flex gap-2 mt-2 pt-2 border-t border-slate-50">
                <button onClick={() => openEdit(e)} className="flex-1 text-xs font-semibold text-slate-600 py-1 flex items-center justify-center gap-1" data-testid={`exp-edit-${e.id}`}><Pencil size={12} /> Edit</button>
                {editable && <button onClick={() => submitExisting(e.id)} className="flex-1 text-xs font-semibold text-orange-600 py-1 flex items-center justify-center gap-1" data-testid={`exp-submit-${e.id}`}><Send size={12} /> {e.status === 'needs_details' ? 'Resubmit' : 'Submit'}</button>}
                {editable && <button onClick={() => cancelExisting(e.id)} className="flex-1 text-xs font-semibold text-slate-400 py-1 flex items-center justify-center gap-1" data-testid={`exp-cancel-${e.id}`}><Trash2 size={12} /> Cancel</button>}
              </div>
            )}
            {e.review_note && (e.status === 'needs_details' || e.status === 'rejected') && (
              <p className="text-[11px] text-orange-600 mt-1.5 italic">“{e.review_note}”</p>
            )}
          </div>
          );
        })}
      </div>
    </div>
  );
}
