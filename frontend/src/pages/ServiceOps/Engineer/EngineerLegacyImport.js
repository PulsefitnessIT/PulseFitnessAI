/**
 * EngineerLegacyImport — Iter 220ea·33.
 *
 * A wizard that lets field engineers bring their history onto GymAxis:
 * pick / create a customer → bulk-upload historic PDF / CSV / XLSX service
 * reports → Gemini extracts the machines + per-machine custom fields → the
 * engineer reviews & edits everything inline → generate a beautiful branded
 * PDF saved against the customer.
 *
 * Backend: routes/svc/legacy_reports.py (prefix /api/svc/legacy).
 * Works for org engineers AND orgless partner engineers (scope handled
 * server-side). Mobile-first, GymAxis light theme.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft, ArrowRight, Upload, FileText, FileSpreadsheet, Loader2, X,
  Check, Plus, Trash2, Building2, Search, Wand2, Download, Eye,
  CheckCircle2, AlertTriangle, Cog, ChevronDown, ChevronUp, History,
  Camera, PenLine, RotateCcw, MessageSquare,
} from 'lucide-react';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });

const uid = () => `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
const ACCEPT = '.pdf,.csv,.xlsx,.xls';
const MAX_PHOTOS = 3;
const todayISO = () => new Date().toISOString().slice(0, 10);

// Compress an image client-side: resize to a max long-edge and re-encode as
// JPEG — small files that still look great in the branded PDF.
async function compressImage(file, maxEdge = 1600, quality = 0.82) {
  const dataUrl = await new Promise((res, rej) => {
    const fr = new FileReader();
    fr.onload = () => res(fr.result);
    fr.onerror = rej;
    fr.readAsDataURL(file);
  });
  const img = await new Promise((res, rej) => {
    const im = new window.Image();
    im.onload = () => res(im);
    im.onerror = rej;
    im.src = dataUrl;
  });
  let { width, height } = img;
  const longest = Math.max(width, height);
  if (longest > maxEdge) {
    const r = maxEdge / longest;
    width = Math.round(width * r);
    height = Math.round(height * r);
  }
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#ffffff'; // flatten transparency for JPEG
  ctx.fillRect(0, 0, width, height);
  ctx.drawImage(img, 0, 0, width, height);
  return new Promise((res) => canvas.toBlob((b) => res(b), 'image/jpeg', quality));
}

async function uploadPhoto(blob) {
  const fd = new FormData();
  fd.append('file', blob, `photo-${Date.now()}.jpg`);
  const r = await axios.post(`${API}/files/upload?category=service-photos`, fd, {
    headers: { ...auth().headers, 'Content-Type': 'multipart/form-data' },
  });
  return { file_id: r.data?.id, storage_path: r.data?.storage_path, url: r.data?.download_url };
}

const fileIcon = (name) => {
  const ext = (name || '').toLowerCase().split('.').pop();
  if (ext === 'pdf') return FileText;
  return FileSpreadsheet;
};

// ─── Step indicator ───────────────────────────────────────────────
const STEPS = ['Customer', 'Upload', 'Review', 'Done'];
function Stepper({ step }) {
  return (
    <div className="flex items-center gap-1.5" data-testid="legacy-stepper">
      {STEPS.map((label, i) => {
        const n = i + 1;
        const active = n === step;
        const done = n < step;
        return (
          <div key={label} className="flex items-center gap-1.5">
            <div
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold transition-colors ${
                active ? 'bg-blue-600 text-white'
                  : done ? 'bg-emerald-100 text-emerald-700'
                    : 'bg-slate-100 text-slate-400'
              }`}
            >
              <span className="w-4 h-4 rounded-full bg-white/25 flex items-center justify-center text-[9px]">
                {done ? <Check size={10} /> : n}
              </span>
              <span className="hidden sm:inline">{label}</span>
            </div>
            {i < STEPS.length - 1 && <div className="w-3 h-px bg-slate-200" />}
          </div>
        );
      })}
    </div>
  );
}

// ─── Field input helper ───────────────────────────────────────────
function Field({ label, value, onChange, placeholder, testid, type = 'text' }) {
  return (
    <label className="block">
      <span className="text-[10px] font-bold uppercase tracking-wide text-slate-500">{label}</span>
      <input
        type={type}
        value={value || ''}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="mt-1 w-full text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white focus:border-blue-400 focus:outline-none"
        data-testid={testid}
      />
    </label>
  );
}

export default function EngineerLegacyImport() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);

  // Customer
  const [custMode, setCustMode] = useState('search'); // 'search' | 'new'
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [selected, setSelected] = useState(null);
  const [newCust, setNewCust] = useState({
    name: '', site_name: '', address: '', contact_name: '', email: '', phone: '',
  });

  // Visits (one per uploaded file)
  const [visits, setVisits] = useState([]);
  const fileRef = useRef(null);

  // Save
  const [saving, setSaving] = useState(false);
  const [savedReport, setSavedReport] = useState(null);

  // Report-level comments + sign-off (engineer + customer)
  const [comments, setComments] = useState('');
  const [signatures, setSignatures] = useState({
    engineer: { name: '', data_url: '', signed_date: todayISO() },
    customer: { name: '', data_url: '', signed_date: todayISO() },
  });
  const updateSig = (who, patch) =>
    setSignatures((s) => ({ ...s, [who]: { ...s[who], ...patch } }));

  // Pre-fill the engineer's signature name from their profile.
  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/auth/me`, auth());
        const nm = r.data?.full_name || r.data?.name || '';
        if (nm) setSignatures((s) => ({ ...s, engineer: { ...s.engineer, name: s.engineer.name || nm } }));
      } catch { /* non-fatal */ }
    })();
  }, []);

  // Saved-reports panel
  const [savedList, setSavedList] = useState([]);
  const [showSaved, setShowSaved] = useState(false);

  const loadSaved = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/svc/legacy/reports`, auth());
      setSavedList(r.data?.reports || []);
    } catch { /* ignore */ }
  }, []);
  useEffect(() => { loadSaved(); }, [loadSaved]);

  // ── Customer search ──
  useEffect(() => {
    if (custMode !== 'search') return undefined;
    const t = setTimeout(async () => {
      setSearching(true);
      try {
        const r = await axios.get(`${API}/svc/legacy/customers/search`, { ...auth(), params: { q: query } });
        setResults(r.data?.customers || []);
      } catch { setResults([]); } finally { setSearching(false); }
    }, 300);
    return () => clearTimeout(t);
  }, [query, custMode]);

  const customerLabel = selected?.name
    || (custMode === 'new' ? (newCust.name || 'New customer') : null);

  const canLeaveCustomer = !!selected || (custMode === 'new' && newCust.name.trim());

  // ── File upload + extraction ──
  const handleFiles = async (e) => {
    const files = Array.from(e.target.files || []);
    if (fileRef.current) fileRef.current.value = '';
    for (const f of files) {
      const ext = (f.name || '').toLowerCase().split('.').pop();
      if (!['pdf', 'csv', 'xlsx', 'xls'].includes(ext)) {
        notify.error('Unsupported file', `${f.name} — upload PDF, CSV or XLSX.`);
        continue;
      }
      const vId = uid();
      setVisits((prev) => [...prev, {
        id: vId, filename: f.name, status: 'extracting',
        service_date: '', job_number: '', summary: '', machines: [], error: '',
      }]);
      try {
        const fd = new FormData();
        fd.append('file', f);
        const r = await axios.post(`${API}/svc/legacy/extract`, fd, {
          ...auth(),
          headers: { ...auth().headers, 'Content-Type': 'multipart/form-data' },
        });
        const d = r.data || {};
        // Prefill the new-customer form from the first detected customer.
        if (custMode === 'new' && !newCust.name && d.customer?.name) {
          setNewCust((c) => ({
            ...c,
            name: d.customer.name || '',
            site_name: d.customer.site_name || '',
            address: d.customer.address || '',
            contact_name: d.customer.contact_name || '',
            email: d.customer.email || '',
            phone: d.customer.phone || '',
          }));
        }
        setVisits((prev) => prev.map((v) => v.id === vId ? {
          ...v, status: 'done',
          service_date: (d.service_date || '').slice(0, 10),
          summary: d.summary || '',
          machines: (d.machines || []).map((m) => ({ ...m, _id: uid(), _open: false })),
        } : v));
      } catch (err) {
        const msg = err?.response?.data?.detail || err?.message || 'Extraction failed';
        setVisits((prev) => prev.map((v) => v.id === vId ? { ...v, status: 'error', error: msg } : v));
        notify.error('Could not read file', msg);
      }
    }
  };

  const removeVisit = (id) => setVisits((prev) => prev.filter((v) => v.id !== id));
  const updateVisit = (id, patch) => setVisits((prev) => prev.map((v) => v.id === id ? { ...v, ...patch } : v));

  const doneVisits = visits.filter((v) => v.status === 'done');
  const extracting = visits.some((v) => v.status === 'extracting');
  const totalMachines = doneVisits.reduce((n, v) => n + (v.machines?.length || 0), 0);

  // ── Save ──
  const save = async () => {
    setSaving(true);
    try {
      const payload = {
        visits: doneVisits.map((v) => ({
          service_date: v.service_date || null,
          job_number: v.job_number || null,
          summary: v.summary || null,
          filename: v.filename || null,
          machines: (v.machines || []).map((m) => ({
            name: m.name || 'Machine',
            model: m.model || null,
            serial: m.serial || null,
            location: m.location || null,
            status: m.status || null,
            work_done: m.work_done || null,
            custom_fields: (m.custom_fields || [])
              .filter((cf) => (cf.label || '').trim())
              .map((cf) => ({ label: cf.label, value: cf.value || '' })),
            photos: (m.photos || [])
              .filter((p) => p.storage_path)
              .slice(0, MAX_PHOTOS)
              .map((p) => ({ file_id: p.file_id || null, storage_path: p.storage_path, url: p.url || null })),
          })),
        })),
      };
      if (selected) payload.customer_id = selected.id;
      else payload.customer = newCust;

      // Report-level comments + sign-off
      payload.comments = comments.trim() || null;
      const sigContent = (p) => !!((p.name || '').trim() || p.data_url);
      payload.signatures = {
        engineer: sigContent(signatures.engineer) ? signatures.engineer : null,
        customer: sigContent(signatures.customer) ? signatures.customer : null,
      };

      const r = await axios.post(`${API}/svc/legacy/reports`, payload, auth());
      setSavedReport(r.data?.report || null);
      setStep(4);
      loadSaved();
      notify.success('Report saved', 'Your branded PDF is ready.');
    } catch (err) {
      notify.error('Could not save', err?.response?.data?.detail || err?.message);
    } finally {
      setSaving(false);
    }
  };

  // ── PDF download (auth blob) ──
  const downloadPdf = async (reportId) => {
    // Open the tab synchronously inside the click gesture so popup
    // blockers don't swallow it, then point it at the blob once fetched.
    const win = window.open('', '_blank');
    try {
      const r = await axios.get(`${API}/svc/legacy/reports/${reportId}/pdf`, { ...auth(), responseType: 'blob' });
      const url = URL.createObjectURL(new Blob([r.data], { type: 'application/pdf' }));
      if (win) win.location = url;
      else window.open(url, '_blank');
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (err) {
      if (win) win.close();
      notify.error('Could not open PDF', err?.response?.data?.detail || err?.message);
    }
  };

  const deleteSaved = async (id) => {
    try {
      await axios.delete(`${API}/svc/legacy/reports/${id}`, auth());
      loadSaved();
      notify.success('Report deleted');
    } catch (err) {
      notify.error('Delete failed', err?.response?.data?.detail || err?.message);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50" data-testid="engineer-legacy-import">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-10">
        <div className="max-w-3xl mx-auto px-4 py-3 flex items-center gap-3">
          <button
            type="button"
            onClick={() => navigate('/svc/engineer')}
            className="p-2 rounded-full border border-slate-200 hover:bg-slate-50"
            data-testid="legacy-back-home"
            aria-label="Back to home"
          >
            <ArrowLeft size={16} />
          </button>
          <div className="flex-1 min-w-0">
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-blue-700">GymAxis · Import</p>
            <h1 className="text-lg font-extrabold text-slate-900 truncate">Legacy report import</h1>
          </div>
          <Stepper step={step} />
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-5 pb-32 space-y-5">
        {/* Intro / saved reports toggle (step 1 only) */}
        {step === 1 && (
          <div className="rounded-2xl bg-gradient-to-br from-blue-50 via-white to-indigo-50/50 border border-blue-200 p-4">
            <div className="flex items-start gap-3">
              <div className="w-9 h-9 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center flex-shrink-0">
                <Wand2 size={16} />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-bold text-slate-900">Turn old reports into branded PDFs</p>
                <p className="text-xs text-slate-600 mt-0.5 leading-snug">
                  Upload your historic spreadsheets or PDFs and our AI rebuilds them into clean,
                  on-brand service reports saved against the customer.
                </p>
              </div>
            </div>
            {savedList.length > 0 && (
              <button
                type="button"
                onClick={() => setShowSaved((s) => !s)}
                className="mt-3 inline-flex items-center gap-1.5 text-xs font-bold text-blue-700 hover:text-blue-800"
                data-testid="legacy-toggle-saved"
              >
                <History size={13} /> {savedList.length} saved report{savedList.length === 1 ? '' : 's'}
                {showSaved ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
              </button>
            )}
            {showSaved && (
              <div className="mt-3 space-y-2" data-testid="legacy-saved-list">
                {savedList.map((rep) => (
                  <div key={rep.id} className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2">
                    <FileText size={15} className="text-blue-600 flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-bold text-slate-900 truncate">{rep.title || rep.customer?.name}</p>
                      <p className="text-[10px] text-slate-500">
                        {rep.visit_count} visit{rep.visit_count === 1 ? '' : 's'} · {rep.machine_count} machine{rep.machine_count === 1 ? '' : 's'}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => downloadPdf(rep.id)}
                      className="p-1.5 rounded-lg border border-slate-200 hover:bg-slate-50"
                      data-testid={`legacy-saved-pdf-${rep.id}`}
                      title="Open PDF"
                    >
                      <Eye size={14} className="text-slate-600" />
                    </button>
                    <button
                      type="button"
                      onClick={() => deleteSaved(rep.id)}
                      className="p-1.5 rounded-lg border border-rose-200 hover:bg-rose-50"
                      data-testid={`legacy-saved-delete-${rep.id}`}
                      title="Delete"
                    >
                      <Trash2 size={14} className="text-rose-500" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* STEP 1 — Customer */}
        {step === 1 && (
          <section className="bg-white rounded-2xl border border-slate-200 p-5 space-y-4" data-testid="legacy-step-customer">
            <h2 className="text-sm font-bold text-slate-900">Who is this report for?</h2>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => { setCustMode('search'); setSelected(null); }}
                className={`flex-1 px-3 py-2 rounded-lg text-xs font-bold border transition-colors ${
                  custMode === 'search' ? 'bg-blue-600 text-white border-transparent' : 'bg-white text-slate-700 border-slate-200'
                }`}
                data-testid="legacy-cust-mode-search"
              >
                <Search size={13} className="inline mr-1" /> Existing customer
              </button>
              <button
                type="button"
                onClick={() => { setCustMode('new'); setSelected(null); }}
                className={`flex-1 px-3 py-2 rounded-lg text-xs font-bold border transition-colors ${
                  custMode === 'new' ? 'bg-blue-600 text-white border-transparent' : 'bg-white text-slate-700 border-slate-200'
                }`}
                data-testid="legacy-cust-mode-new"
              >
                <Plus size={13} className="inline mr-1" /> New customer
              </button>
            </div>

            {custMode === 'search' ? (
              <div className="space-y-2">
                <div className="relative">
                  <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                  <input
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Search your customers…"
                    className="w-full text-sm border border-slate-200 rounded-lg pl-9 pr-3 py-2 focus:border-blue-400 focus:outline-none"
                    data-testid="legacy-cust-search-input"
                  />
                </div>
                {searching && <p className="text-xs text-slate-400 flex items-center gap-1"><Loader2 size={12} className="animate-spin" /> Searching…</p>}
                <div className="space-y-1.5 max-h-64 overflow-y-auto">
                  {results.map((c) => (
                    <button
                      key={c.id}
                      type="button"
                      onClick={() => setSelected(c)}
                      className={`w-full text-left flex items-center gap-2 px-3 py-2 rounded-lg border transition-colors ${
                        selected?.id === c.id ? 'border-blue-400 bg-blue-50' : 'border-slate-200 hover:bg-slate-50'
                      }`}
                      data-testid={`legacy-cust-result-${c.id}`}
                    >
                      <Building2 size={15} className="text-slate-400 flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-semibold text-slate-900 truncate">{c.name}</p>
                        {(c.site_name || c.address) && (
                          <p className="text-[11px] text-slate-500 truncate">{c.site_name || c.address}</p>
                        )}
                      </div>
                      {selected?.id === c.id && <CheckCircle2 size={16} className="text-blue-600" />}
                    </button>
                  ))}
                  {!searching && results.length === 0 && (
                    <p className="text-xs text-slate-400 py-3 text-center">
                      No matches. {query ? 'Try a different name or' : 'Start typing, or'} add a new customer.
                    </p>
                  )}
                </div>
              </div>
            ) : (
              <div className="grid sm:grid-cols-2 gap-3">
                <div className="sm:col-span-2">
                  <Field label="Customer name *" value={newCust.name} onChange={(v) => setNewCust({ ...newCust, name: v })} placeholder="e.g. Riverside Leisure Centre" testid="legacy-newcust-name" />
                </div>
                <Field label="Site name" value={newCust.site_name} onChange={(v) => setNewCust({ ...newCust, site_name: v })} testid="legacy-newcust-site" />
                <Field label="Address" value={newCust.address} onChange={(v) => setNewCust({ ...newCust, address: v })} testid="legacy-newcust-address" />
                <Field label="Contact name" value={newCust.contact_name} onChange={(v) => setNewCust({ ...newCust, contact_name: v })} testid="legacy-newcust-contact" />
                <Field label="Email" value={newCust.email} onChange={(v) => setNewCust({ ...newCust, email: v })} testid="legacy-newcust-email" />
                <Field label="Phone" value={newCust.phone} onChange={(v) => setNewCust({ ...newCust, phone: v })} testid="legacy-newcust-phone" />
              </div>
            )}
          </section>
        )}

        {/* STEP 2 — Upload */}
        {step === 2 && (
          <section className="bg-white rounded-2xl border border-slate-200 p-5 space-y-4" data-testid="legacy-step-upload">
            <div>
              <h2 className="text-sm font-bold text-slate-900">Upload historic reports</h2>
              <p className="text-xs text-slate-500 mt-0.5">
                For <span className="font-semibold text-slate-700">{customerLabel}</span> · PDF, CSV or XLSX. Each file is one visit.
              </p>
            </div>

            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              className="w-full rounded-xl border-2 border-dashed border-blue-200 bg-blue-50/50 hover:bg-blue-50 px-4 py-6 flex flex-col items-center gap-2 transition-colors"
              data-testid="legacy-upload-btn"
            >
              <Upload size={22} className="text-blue-600" />
              <span className="text-sm font-bold text-blue-700">Choose files</span>
              <span className="text-[11px] text-slate-500">PDF · CSV · XLSX — up to 15 MB each</span>
            </button>
            <input
              ref={fileRef}
              type="file"
              accept={ACCEPT}
              multiple
              onChange={handleFiles}
              className="hidden"
              data-testid="legacy-upload-input"
            />

            {visits.length > 0 && (
              <div className="space-y-2" data-testid="legacy-upload-list">
                {visits.map((v) => {
                  const Icon = fileIcon(v.filename);
                  return (
                    <div key={v.id} className="flex items-center gap-3 rounded-xl border border-slate-200 px-3 py-2.5">
                      <Icon size={18} className="text-slate-400 flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-semibold text-slate-900 truncate">{v.filename}</p>
                        {v.status === 'extracting' && (
                          <p className="text-[11px] text-blue-600 flex items-center gap-1"><Loader2 size={11} className="animate-spin" /> Reading with AI…</p>
                        )}
                        {v.status === 'done' && (
                          <p className="text-[11px] text-emerald-600 flex items-center gap-1"><Check size={11} /> {v.machines.length} machine{v.machines.length === 1 ? '' : 's'} found</p>
                        )}
                        {v.status === 'error' && (
                          <p className="text-[11px] text-rose-600 flex items-center gap-1"><AlertTriangle size={11} /> {v.error}</p>
                        )}
                      </div>
                      <button
                        type="button"
                        onClick={() => removeVisit(v.id)}
                        className="p-1.5 rounded-lg hover:bg-slate-100"
                        data-testid={`legacy-remove-${v.id}`}
                        aria-label="Remove file"
                      >
                        <X size={15} className="text-slate-400" />
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        )}

        {/* STEP 3 — Review */}
        {step === 3 && (
          <section className="space-y-4" data-testid="legacy-step-review">
            <div className="bg-white rounded-2xl border border-slate-200 p-4">
              <p className="text-sm font-bold text-slate-900">Review & edit</p>
              <p className="text-xs text-slate-500 mt-0.5">
                {doneVisits.length} visit{doneVisits.length === 1 ? '' : 's'} · {totalMachines} machine{totalMachines === 1 ? '' : 's'} for {customerLabel}. Tap a machine to edit its details.
              </p>
            </div>

            {doneVisits.map((v) => (
              <div key={v.id} className="bg-white rounded-2xl border border-slate-200 p-4 space-y-3" data-testid={`legacy-review-visit-${v.id}`}>
                <div className="flex items-center gap-2">
                  <FileText size={15} className="text-blue-600" />
                  <p className="text-xs font-bold text-slate-700 truncate flex-1">{v.filename}</p>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <Field label="Visit date" type="date" value={v.service_date} onChange={(val) => updateVisit(v.id, { service_date: val })} testid={`legacy-visit-date-${v.id}`} />
                  <Field label="Job number" value={v.job_number} onChange={(val) => updateVisit(v.id, { job_number: val })} testid={`legacy-visit-job-${v.id}`} />
                </div>

                <div className="space-y-2">
                  {v.machines.map((m, mi) => (
                    <MachineEditor
                      key={m._id}
                      machine={m}
                      onChange={(patch) => {
                        const machines = v.machines.map((x) => x._id === m._id ? { ...x, ...patch } : x);
                        updateVisit(v.id, { machines });
                      }}
                      onRemove={() => updateVisit(v.id, { machines: v.machines.filter((x) => x._id !== m._id) })}
                      index={mi}
                    />
                  ))}
                  <button
                    type="button"
                    onClick={() => updateVisit(v.id, { machines: [...v.machines, { _id: uid(), name: 'New machine', custom_fields: [], _open: true }] })}
                    className="w-full text-xs font-bold text-blue-700 border border-dashed border-blue-200 rounded-lg py-2 hover:bg-blue-50"
                    data-testid={`legacy-add-machine-${v.id}`}
                  >
                    <Plus size={12} className="inline mr-1" /> Add machine
                  </button>
                </div>
              </div>
            ))}

            {/* Report comments */}
            <div className="bg-white rounded-2xl border border-slate-200 p-4 space-y-2" data-testid="legacy-comments-card">
              <div className="flex items-center gap-2">
                <MessageSquare size={15} className="text-blue-600" />
                <p className="text-sm font-bold text-slate-900">Additional comments</p>
              </div>
              <textarea
                value={comments}
                onChange={(e) => setComments(e.target.value)}
                rows={3}
                maxLength={4000}
                placeholder="Any overall notes for this report — recommendations, follow-ups, parts on order…"
                className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white focus:border-blue-400 focus:outline-none"
                data-testid="legacy-comments-input"
              />
            </div>

            {/* Sign-off */}
            <div className="bg-white rounded-2xl border border-slate-200 p-4 space-y-3" data-testid="legacy-signoff-card">
              <div className="flex items-center gap-2">
                <PenLine size={15} className="text-blue-600" />
                <p className="text-sm font-bold text-slate-900">Sign-off</p>
              </div>
              <div className="grid sm:grid-cols-2 gap-4">
                <SignaturePad
                  title="Engineer"
                  who="engineer"
                  value={signatures.engineer}
                  onChange={(patch) => updateSig('engineer', patch)}
                />
                <SignaturePad
                  title="Customer acceptance"
                  who="customer"
                  value={signatures.customer}
                  onChange={(patch) => updateSig('customer', patch)}
                />
              </div>
            </div>
          </section>
        )}

        {/* STEP 4 — Done */}
        {step === 4 && savedReport && (
          <section className="bg-white rounded-2xl border border-slate-200 p-6 text-center space-y-4" data-testid="legacy-step-done">
            <div className="w-14 h-14 mx-auto rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center">
              <CheckCircle2 size={28} />
            </div>
            <div>
              <h2 className="text-lg font-extrabold text-slate-900">Report ready</h2>
              <p className="text-sm text-slate-500 mt-1">
                {savedReport.visit_count} visit{savedReport.visit_count === 1 ? '' : 's'} · {savedReport.machine_count} machine{savedReport.machine_count === 1 ? '' : 's'} saved for {savedReport.customer?.name}.
              </p>
            </div>
            <div className="flex flex-col sm:flex-row gap-2 justify-center">
              <button
                type="button"
                onClick={() => downloadPdf(savedReport.id)}
                className="inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-sm font-bold"
                data-testid="legacy-done-view-pdf"
              >
                <Download size={15} /> View branded PDF
              </button>
              <button
                type="button"
                onClick={() => {
                  // Reset for another import
                  setStep(1); setVisits([]); setSavedReport(null);
                  setSelected(null); setNewCust({ name: '', site_name: '', address: '', contact_name: '', email: '', phone: '' });
                  setQuery('');
                  setComments('');
                  setSignatures((s) => ({
                    engineer: { name: s.engineer.name, data_url: '', signed_date: todayISO() },
                    customer: { name: '', data_url: '', signed_date: todayISO() },
                  }));
                }}
                className="inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-sm font-bold text-slate-700"
                data-testid="legacy-done-another"
              >
                <Plus size={15} /> Import another
              </button>
            </div>
            <button
              type="button"
              onClick={() => navigate('/svc/engineer/customers')}
              className="text-xs font-semibold text-blue-700 hover:text-blue-800"
              data-testid="legacy-done-customers"
            >
              Go to my customers →
            </button>
          </section>
        )}
      </main>

      {/* Sticky footer nav */}
      {step < 4 && (
        <div className="fixed bottom-0 inset-x-0 bg-white border-t border-slate-200 px-4 py-3 z-[60]">
          <div className="max-w-3xl mx-auto flex items-center gap-3">
            {step > 1 ? (
              <button
                type="button"
                onClick={() => setStep((s) => s - 1)}
                className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-sm font-bold text-slate-700"
                data-testid="legacy-prev"
              >
                <ArrowLeft size={15} /> Back
              </button>
            ) : <div />}
            <div className="flex-1" />
            {step === 1 && (
              <button
                type="button"
                disabled={!canLeaveCustomer}
                onClick={() => setStep(2)}
                className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white text-sm font-bold"
                data-testid="legacy-next-upload"
              >
                Next <ArrowRight size={15} />
              </button>
            )}
            {step === 2 && (
              <button
                type="button"
                disabled={doneVisits.length === 0 || extracting}
                onClick={() => setStep(3)}
                className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white text-sm font-bold"
                data-testid="legacy-next-review"
              >
                {extracting ? <><Loader2 size={15} className="animate-spin" /> Reading…</> : <>Review {doneVisits.length > 0 ? `(${totalMachines})` : ''} <ArrowRight size={15} /></>}
              </button>
            )}
            {step === 3 && (
              <button
                type="button"
                disabled={saving || totalMachines === 0}
                onClick={save}
                className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 disabled:opacity-40 text-white text-sm font-bold"
                data-testid="legacy-save"
              >
                {saving ? <><Loader2 size={15} className="animate-spin" /> Saving…</> : <><Check size={15} /> Generate PDF</>}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── MachineEditor ────────────────────────────────────────────────
function MachineEditor({ machine, onChange, onRemove, index }) {
  const open = !!machine._open;
  const cfs = machine.custom_fields || [];
  const setCf = (i, patch) => onChange({ custom_fields: cfs.map((c, ci) => ci === i ? { ...c, ...patch } : c) });
  const addCf = () => onChange({ custom_fields: [...cfs, { label: '', value: '' }] });
  const removeCf = (i) => onChange({ custom_fields: cfs.filter((_, ci) => ci !== i) });

  return (
    <div className="rounded-xl border border-slate-200 overflow-hidden" data-testid={`legacy-machine-${machine._id}`}>
      <button
        type="button"
        onClick={() => onChange({ _open: !open })}
        className="w-full flex items-center gap-2.5 px-3 py-2.5 text-left hover:bg-slate-50"
        data-testid={`legacy-machine-toggle-${machine._id}`}
      >
        <div className="w-7 h-7 rounded-lg bg-slate-100 flex items-center justify-center flex-shrink-0">
          <Cog size={14} className="text-slate-500" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-slate-900 truncate">{machine.name || `Machine ${index + 1}`}</p>
          <p className="text-[11px] text-slate-500 truncate">
            {[machine.model, machine.serial, machine.status].filter(Boolean).join(' · ') || `${cfs.length} custom field${cfs.length === 1 ? '' : 's'}`}
          </p>
        </div>
        {open ? <ChevronUp size={15} className="text-slate-400" /> : <ChevronDown size={15} className="text-slate-400" />}
      </button>

      {open && (
        <div className="px-3 pb-3 pt-1 space-y-3 border-t border-slate-100 bg-slate-50/40">
          <div className="grid grid-cols-2 gap-2">
            <Field label="Name" value={machine.name} onChange={(v) => onChange({ name: v })} testid={`legacy-m-name-${machine._id}`} />
            <Field label="Status" value={machine.status} onChange={(v) => onChange({ status: v })} placeholder="e.g. Serviced" testid={`legacy-m-status-${machine._id}`} />
            <Field label="Model" value={machine.model} onChange={(v) => onChange({ model: v })} testid={`legacy-m-model-${machine._id}`} />
            <Field label="Serial" value={machine.serial} onChange={(v) => onChange({ serial: v })} testid={`legacy-m-serial-${machine._id}`} />
            <div className="col-span-2">
              <Field label="Location" value={machine.location} onChange={(v) => onChange({ location: v })} testid={`legacy-m-location-${machine._id}`} />
            </div>
          </div>
          <label className="block">
            <span className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Work done / notes</span>
            <textarea
              value={machine.work_done || ''}
              onChange={(e) => onChange({ work_done: e.target.value })}
              rows={2}
              className="mt-1 w-full text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white focus:border-blue-400 focus:outline-none"
              data-testid={`legacy-m-work-${machine._id}`}
            />
          </label>

          {/* Custom fields */}
          <div>
            <p className="text-[10px] font-bold uppercase tracking-wide text-slate-500 mb-1.5">Custom fields</p>
            <div className="space-y-1.5">
              {cfs.map((cf, i) => (
                <div key={i} className="flex items-center gap-1.5" data-testid={`legacy-cf-${machine._id}-${i}`}>
                  <input
                    value={cf.label || ''}
                    onChange={(e) => setCf(i, { label: e.target.value })}
                    placeholder="Label"
                    className="flex-1 min-w-0 text-xs border border-slate-200 rounded-lg px-2 py-1.5 bg-white"
                    data-testid={`legacy-cf-label-${machine._id}-${i}`}
                  />
                  <input
                    value={cf.value || ''}
                    onChange={(e) => setCf(i, { value: e.target.value })}
                    placeholder="Value"
                    className="flex-1 min-w-0 text-xs border border-slate-200 rounded-lg px-2 py-1.5 bg-white"
                    data-testid={`legacy-cf-value-${machine._id}-${i}`}
                  />
                  <button
                    type="button"
                    onClick={() => removeCf(i)}
                    className="p-1.5 rounded-lg hover:bg-rose-50"
                    aria-label="Remove field"
                    data-testid={`legacy-cf-remove-${machine._id}-${i}`}
                  >
                    <Trash2 size={13} className="text-rose-400" />
                  </button>
                </div>
              ))}
            </div>
            <button
              type="button"
              onClick={addCf}
              className="mt-1.5 text-[11px] font-bold text-blue-700 hover:text-blue-800"
              data-testid={`legacy-cf-add-${machine._id}`}
            >
              <Plus size={11} className="inline mr-0.5" /> Add field
            </button>
          </div>

          {/* Photos (max 3) */}
          <MachinePhotos
            photos={machine.photos || []}
            onChange={(photos) => onChange({ photos })}
            machineId={machine._id}
          />

          <button
            type="button"
            onClick={onRemove}
            className="text-[11px] font-bold text-rose-600 hover:text-rose-700"
            data-testid={`legacy-machine-remove-${machine._id}`}
          >
            <Trash2 size={11} className="inline mr-0.5" /> Remove machine
          </button>
        </div>
      )}
    </div>
  );
}

// ─── MachinePhotos ────────────────────────────────────────────────
function MachinePhotos({ photos, onChange, machineId }) {
  const inputRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const remaining = MAX_PHOTOS - photos.length;

  const onPick = async (e) => {
    const files = Array.from(e.target.files || []);
    if (inputRef.current) inputRef.current.value = '';
    if (!files.length) return;
    const slots = Math.min(remaining, files.length);
    if (files.length > remaining) {
      notify.error('Photo limit', `Up to ${MAX_PHOTOS} photos per machine.`);
    }
    setBusy(true);
    const added = [];
    for (const f of files.slice(0, slots)) {
      if (!f.type.startsWith('image/')) {
        notify.error('Not an image', `${f.name} isn't a photo.`);
        continue;
      }
      try {
        const blob = await compressImage(f);
        const meta = await uploadPhoto(blob);
        added.push({ ...meta, _preview: URL.createObjectURL(blob) });
      } catch (err) {
        notify.error('Upload failed', err?.response?.data?.detail || err?.message);
      }
    }
    if (added.length) onChange([...photos, ...added].slice(0, MAX_PHOTOS));
    setBusy(false);
  };

  const removeAt = (i) => onChange(photos.filter((_, idx) => idx !== i));

  return (
    <div data-testid={`legacy-photos-${machineId}`}>
      <p className="text-[10px] font-bold uppercase tracking-wide text-slate-500 mb-1.5">
        Photos <span className="text-slate-400 normal-case font-medium">({photos.length}/{MAX_PHOTOS})</span>
      </p>
      <div className="flex flex-wrap gap-2">
        {photos.map((p, i) => (
          <div key={p.file_id || i} className="relative w-20 h-20 rounded-lg overflow-hidden border border-slate-200 bg-slate-100" data-testid={`legacy-photo-${machineId}-${i}`}>
            <img src={p._preview || p.url} alt="machine" className="w-full h-full object-cover" />
            <button
              type="button"
              onClick={() => removeAt(i)}
              className="absolute top-0.5 right-0.5 w-5 h-5 rounded-full bg-black/60 text-white flex items-center justify-center hover:bg-black/80"
              data-testid={`legacy-photo-remove-${machineId}-${i}`}
              aria-label="Remove photo"
            >
              <X size={12} />
            </button>
          </div>
        ))}
        {remaining > 0 && (
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={busy}
            className="w-20 h-20 rounded-lg border-2 border-dashed border-blue-200 bg-blue-50/50 hover:bg-blue-50 flex flex-col items-center justify-center gap-1 text-blue-600 disabled:opacity-50"
            data-testid={`legacy-photo-add-${machineId}`}
          >
            {busy ? <Loader2 size={16} className="animate-spin" /> : <Camera size={16} />}
            <span className="text-[9px] font-bold">Add photo</span>
          </button>
        )}
      </div>
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        multiple
        capture="environment"
        onChange={onPick}
        className="hidden"
        data-testid={`legacy-photo-input-${machineId}`}
      />
    </div>
  );
}

// ─── SignaturePad ─────────────────────────────────────────────────
function SignaturePad({ title, who, value, onChange }) {
  const canvasRef = useRef(null);
  const drawing = useRef(false);
  const dirty = useRef(false);

  const ctxOf = () => {
    const c = canvasRef.current;
    const ctx = c.getContext('2d');
    ctx.strokeStyle = '#0f172a';
    ctx.lineWidth = 2.2;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    return ctx;
  };
  const posOf = (e) => {
    const c = canvasRef.current;
    const rect = c.getBoundingClientRect();
    const t = e.touches ? e.touches[0] : e;
    return {
      x: (t.clientX - rect.left) * (c.width / rect.width),
      y: (t.clientY - rect.top) * (c.height / rect.height),
    };
  };
  const start = (e) => { e.preventDefault(); drawing.current = true; const ctx = ctxOf(); const p = posOf(e); ctx.beginPath(); ctx.moveTo(p.x, p.y); };
  const move = (e) => { if (!drawing.current) return; e.preventDefault(); const ctx = ctxOf(); const p = posOf(e); ctx.lineTo(p.x, p.y); ctx.stroke(); dirty.current = true; };
  const end = () => {
    if (!drawing.current) return;
    drawing.current = false;
    if (dirty.current) onChange({ data_url: canvasRef.current.toDataURL('image/png') });
  };
  const clear = () => {
    const c = canvasRef.current;
    c.getContext('2d').clearRect(0, 0, c.width, c.height);
    dirty.current = false;
    onChange({ data_url: '' });
  };

  return (
    <div className="space-y-2" data-testid={`legacy-sig-${who}`}>
      <p className="text-[10px] font-bold uppercase tracking-wide text-slate-500">{title}</p>
      <div className="relative rounded-lg border border-slate-300 bg-white">
        <canvas
          ref={canvasRef}
          width={560}
          height={170}
          className="w-full h-[110px] touch-none rounded-lg"
          onMouseDown={start}
          onMouseMove={move}
          onMouseUp={end}
          onMouseLeave={end}
          onTouchStart={start}
          onTouchMove={move}
          onTouchEnd={end}
          data-testid={`legacy-sig-canvas-${who}`}
        />
        {!value.data_url && (
          <span className="pointer-events-none absolute inset-0 flex items-center justify-center text-xs text-slate-300">
            Sign here
          </span>
        )}
        <button
          type="button"
          onClick={clear}
          className="absolute top-1 right-1 inline-flex items-center gap-1 text-[10px] font-bold text-slate-500 bg-white/90 border border-slate-200 rounded px-1.5 py-0.5 hover:bg-slate-50"
          data-testid={`legacy-sig-clear-${who}`}
        >
          <RotateCcw size={10} /> Clear
        </button>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <input
          value={value.name || ''}
          onChange={(e) => onChange({ name: e.target.value })}
          placeholder={who === 'customer' ? 'Customer name' : 'Name'}
          className="text-xs border border-slate-200 rounded-lg px-2 py-1.5 bg-white focus:border-blue-400 focus:outline-none"
          data-testid={`legacy-sig-name-${who}`}
        />
        <input
          type="date"
          value={value.signed_date || ''}
          onChange={(e) => onChange({ signed_date: e.target.value })}
          className="text-xs border border-slate-200 rounded-lg px-2 py-1.5 bg-white focus:border-blue-400 focus:outline-none"
          data-testid={`legacy-sig-date-${who}`}
        />
      </div>
    </div>
  );
}
