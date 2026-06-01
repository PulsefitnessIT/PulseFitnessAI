/**
 * PartsImportWizard — Iter 220ea·20 · Phase 5b.
 *
 * 6-step CSV/Excel bulk import: Upload → Map columns → Validate/Preview →
 * Options → Import → Summary. Talks to /api/svc/parts/import/{parse,
 * validate,commit}. The file is staged server-side (session_id) so
 * thousands of rows never round-trip through the browser.
 *
 * AI column-mapping is suggested on parse; the user can override every
 * mapping before validating.
 */
import { useRef, useState } from 'react';
import axios from 'axios';
import {
  Upload, FileSpreadsheet, X, ArrowRight, ArrowLeft, Loader2,
  CheckCircle2, AlertTriangle, Sparkles, PartyPopper,
} from 'lucide-react';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });

const STEPS = ['Upload', 'Map', 'Review', 'Done'];
const FIELD_LABELS = {
  sku: 'Part number *', name: 'Part name *', description: 'Description',
  manufacturer: 'Manufacturer', mfr_part_number: 'Mfr part no.', supplier: 'Supplier',
  supplier_part_number: 'Supplier part no.', category: 'Category', cost: 'Cost price',
  list_price: 'Sell price', van_qty: 'Quantity', reorder_threshold: 'Min stock',
  reorder_qty: 'Reorder qty', bin_location: 'Van location', compatible_models: 'Compatible model',
  notes: 'Notes',
};

export default function PartsImportWizard({ onClose, onComplete }) {
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [useAi, setUseAi] = useState(true);
  const [parsed, setParsed] = useState(null);   // {session_id, headers, sample, suggested_mapping, ...}
  const [mapping, setMapping] = useState({});    // {header: canonical|''}
  const [validation, setValidation] = useState(null);
  const [options, setOptions] = useState({ mode: 'upsert', van_qty_mode: 'set', skip_duplicates: true });
  const [result, setResult] = useState(null);
  const fileRef = useRef(null);

  const canonicalFields = parsed?.canonical_fields || [];

  const doParse = async (file) => {
    if (!file) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('use_ai', useAi ? 'true' : 'false');
      const r = await axios.post(`${API}/svc/parts/import/parse`, fd, {
        headers: { ...auth().headers, 'Content-Type': 'multipart/form-data' },
      });
      setParsed(r.data);
      setMapping(r.data.suggested_mapping || {});
      setStep(1);
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Could not read that file');
    } finally { setBusy(false); }
  };

  const doValidate = async () => {
    const mapped = Object.values(mapping).filter(Boolean);
    if (!mapped.includes('sku') || !mapped.includes('name')) {
      notify.error('Map both Part number and Part name to continue');
      return;
    }
    setBusy(true);
    try {
      const r = await axios.post(`${API}/svc/parts/import/validate`, {
        session_id: parsed.session_id, mapping, use_ai: useAi,
      }, auth());
      setValidation(r.data);
      setStep(2);
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Validation failed');
    } finally { setBusy(false); }
  };

  const doCommit = async () => {
    setBusy(true);
    try {
      const r = await axios.post(`${API}/svc/parts/import/commit`, {
        session_id: parsed.session_id, mapping, options,
      }, auth());
      setResult(r.data.summary);
      setStep(3);
      onComplete?.();
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Import failed');
    } finally { setBusy(false); }
  };

  const sum = validation?.summary || {};

  return (
    <div className="fixed inset-0 z-[120] bg-slate-900/60 flex items-stretch sm:items-center justify-center sm:p-4"
         data-testid="parts-import-wizard">
      <div className="w-full sm:max-w-2xl bg-white sm:rounded-2xl flex flex-col max-h-screen sm:max-h-[90vh]">
        {/* Header + steps */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-100">
          <h2 className="text-lg font-extrabold text-slate-900">Import parts</h2>
          <button onClick={onClose} className="p-2 -mr-2 text-slate-400" data-testid="import-close"><X className="w-5 h-5" /></button>
        </div>
        <div className="flex items-center gap-1 px-5 py-2.5 border-b border-slate-100">
          {STEPS.map((s, i) => (
            <div key={s} className="flex items-center gap-1 flex-1 last:flex-none">
              <span className={`shrink-0 w-6 h-6 rounded-full text-xs font-bold flex items-center justify-center ${
                i < step ? 'bg-emerald-500 text-white' : i === step ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-400'}`}>
                {i < step ? '✓' : i + 1}
              </span>
              <span className={`text-xs font-semibold ${i === step ? 'text-slate-900' : 'text-slate-400'}`}>{s}</span>
              {i < STEPS.length - 1 && <div className="flex-1 h-px bg-slate-200 mx-1" />}
            </div>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {/* STEP 0 — UPLOAD */}
          {step === 0 && (
            <div className="space-y-4">
              <button onClick={() => fileRef.current?.click()} disabled={busy}
                      data-testid="import-dropzone"
                      className="w-full border-2 border-dashed border-slate-300 rounded-2xl py-12 flex flex-col items-center gap-2 text-slate-500 hover:border-blue-400 hover:bg-blue-50/40 transition-colors">
                {busy ? <Loader2 className="w-9 h-9 animate-spin text-blue-500" /> : <Upload className="w-9 h-9" />}
                <p className="font-bold text-slate-700">{busy ? 'Reading file…' : 'Tap to choose a file'}</p>
                <p className="text-xs">CSV or Excel (.xlsx) · up to 10,000 rows</p>
              </button>
              <input ref={fileRef} type="file" accept=".csv,.xlsx,.xlsm,.txt" className="hidden"
                     data-testid="import-file-input"
                     onChange={(e) => doParse(e.target.files?.[0])} />
              <label className="flex items-center gap-2 text-sm text-slate-600 cursor-pointer" data-testid="import-ai-toggle">
                <input type="checkbox" checked={useAi} onChange={(e) => setUseAi(e.target.checked)} className="w-4 h-4 accent-blue-600" />
                <Sparkles className="w-4 h-4 text-violet-500" />
                Use AI to auto-map columns &amp; flag duplicates
              </label>
            </div>
          )}

          {/* STEP 1 — MAP */}
          {step === 1 && parsed && (
            <div className="space-y-3" data-testid="import-map-step">
              <p className="text-sm text-slate-500">
                <span className="font-bold text-slate-700">{parsed.row_count}</span> rows in
                <span className="font-mono text-xs"> {parsed.filename}</span>. Confirm how your columns map to our fields.
              </p>
              {parsed.headers.map((h) => (
                <div key={h} className="flex items-center gap-3" data-testid={`map-row-${h}`}>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-slate-800 truncate">{h}</p>
                    <p className="text-[11px] text-slate-400 truncate">e.g. {String(parsed.sample?.[0]?.[h] ?? '—')}</p>
                  </div>
                  <ArrowRight className="w-4 h-4 text-slate-300 shrink-0" />
                  <select value={mapping[h] || ''} onChange={(e) => setMapping((m) => ({ ...m, [h]: e.target.value }))}
                          data-testid={`map-select-${h}`}
                          className="w-44 shrink-0 h-10 rounded-xl border border-slate-200 text-sm px-2 bg-white">
                    <option value="">— ignore —</option>
                    {canonicalFields.map((f) => (
                      <option key={f} value={f}>{FIELD_LABELS[f] || f}</option>
                    ))}
                  </select>
                </div>
              ))}
            </div>
          )}

          {/* STEP 2 — REVIEW */}
          {step === 2 && validation && (
            <div className="space-y-4" data-testid="import-review-step">
              <div className="grid grid-cols-4 gap-2">
                <Mini label="Valid" value={sum.valid} tone="emerald" />
                <Mini label="New" value={sum.new} tone="blue" />
                <Mini label="Update" value={sum.update} tone="slate" />
                <Mini label="Errors" value={sum.errors} tone={sum.errors ? 'rose' : 'slate'} />
              </div>

              {validation.ai_duplicates?.length > 0 && (
                <div className="rounded-xl border border-violet-200 bg-violet-50 p-3" data-testid="import-ai-dupes">
                  <p className="text-xs font-bold text-violet-700 flex items-center gap-1 mb-1"><Sparkles className="w-3.5 h-3.5" /> AI flagged possible duplicates</p>
                  {validation.ai_duplicates.slice(0, 4).map((g, i) => (
                    <p key={i} className="text-[11px] text-violet-600">Rows {g.rows?.map((r) => r + 1).join(', ')} — {g.reason}</p>
                  ))}
                </div>
              )}

              {validation.issues?.length > 0 && (
                <div className="rounded-xl border border-slate-200 max-h-40 overflow-y-auto" data-testid="import-issues">
                  {validation.issues.slice(0, 50).map((iss, i) => (
                    <div key={i} className="flex items-center gap-2 px-3 py-1.5 text-xs border-b border-slate-50 last:border-0">
                      <AlertTriangle className={`w-3.5 h-3.5 shrink-0 ${iss.severity === 'error' ? 'text-rose-500' : 'text-amber-500'}`} />
                      <span className="font-semibold text-slate-600">Row {iss.row + 1}</span>
                      <span className="text-slate-400">{iss.field}</span>
                      <span className="text-slate-500 truncate">{iss.message}</span>
                    </div>
                  ))}
                </div>
              )}

              <div className="space-y-2.5 pt-1">
                <p className="text-xs font-bold uppercase tracking-wider text-slate-400">Import options</p>
                <OptRow label="Existing parts">
                  <Seg value={options.mode} set={(v) => setOptions((o) => ({ ...o, mode: v }))}
                       opts={[['upsert', 'Add + update'], ['add_new', 'Add new only'], ['update_existing', 'Update only']]} tid="opt-mode" />
                </OptRow>
                <OptRow label="Van quantity">
                  <Seg value={options.van_qty_mode} set={(v) => setOptions((o) => ({ ...o, van_qty_mode: v }))}
                       opts={[['set', 'Set'], ['adjust', 'Adjust ±'], ['ignore', 'Ignore']]} tid="opt-van" />
                </OptRow>
              </div>
            </div>
          )}

          {/* STEP 3 — DONE */}
          {step === 3 && result && (
            <div className="py-8 text-center space-y-3" data-testid="import-done-step">
              <div className="w-16 h-16 mx-auto rounded-2xl bg-emerald-50 flex items-center justify-center text-emerald-500">
                <PartyPopper className="w-8 h-8" />
              </div>
              <p className="text-lg font-extrabold text-slate-900">Import complete</p>
              <div className="grid grid-cols-3 gap-2 max-w-sm mx-auto">
                <Mini label="Created" value={result.created} tone="emerald" />
                <Mini label="Updated" value={result.updated} tone="blue" />
                <Mini label="Skipped" value={result.skipped} tone="slate" />
                <Mini label="Van lines" value={result.van_adjusted} tone="blue" />
                <Mini label="Errors" value={result.errors} tone={result.errors ? 'rose' : 'slate'} />
                <Mini label="Rows" value={result.rows} tone="slate" />
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center gap-3 px-5 py-3.5 border-t border-slate-100">
          {step > 0 && step < 3 && (
            <button onClick={() => setStep((s) => s - 1)} className="px-4 h-11 rounded-xl border border-slate-200 font-semibold text-slate-600 flex items-center gap-1"
                    data-testid="import-back"><ArrowLeft className="w-4 h-4" /> Back</button>
          )}
          <div className="flex-1" />
          {step === 1 && (
            <button onClick={doValidate} disabled={busy} data-testid="import-validate-btn"
                    className="px-5 h-11 rounded-xl bg-blue-600 text-white font-bold flex items-center gap-2 disabled:opacity-60">
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />} Validate
            </button>
          )}
          {step === 2 && (
            <button onClick={doCommit} disabled={busy} data-testid="import-commit-btn"
                    className="px-5 h-11 rounded-xl bg-blue-600 text-white font-bold flex items-center gap-2 disabled:opacity-60">
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
              Import {sum.valid || 0} parts
            </button>
          )}
          {step === 3 && (
            <button onClick={onClose} data-testid="import-finish"
                    className="px-6 h-11 rounded-xl bg-slate-900 text-white font-bold">Done</button>
          )}
        </div>
      </div>
    </div>
  );
}

const Mini = ({ label, value, tone }) => {
  const t = {
    emerald: 'bg-emerald-50 text-emerald-700 border-emerald-100',
    blue: 'bg-blue-50 text-blue-700 border-blue-100',
    rose: 'bg-rose-50 text-rose-700 border-rose-100',
    slate: 'bg-slate-50 text-slate-600 border-slate-100',
  }[tone] || 'bg-slate-50 text-slate-600 border-slate-100';
  return (
    <div className={`rounded-xl border px-2 py-2 text-center ${t}`}>
      <p className="text-lg font-extrabold leading-none">{value ?? 0}</p>
      <p className="text-[10px] font-semibold uppercase tracking-wide mt-0.5">{label}</p>
    </div>
  );
};

const OptRow = ({ label, children }) => (
  <div className="flex items-center justify-between gap-3">
    <span className="text-sm text-slate-600">{label}</span>
    {children}
  </div>
);

const Seg = ({ value, set, opts, tid }) => (
  <div className="flex rounded-xl border border-slate-200 overflow-hidden" data-testid={tid}>
    {opts.map(([v, label]) => (
      <button key={v} onClick={() => set(v)}
              className={`px-2.5 h-9 text-xs font-semibold ${value === v ? 'bg-blue-600 text-white' : 'bg-white text-slate-600'}`}>
        {label}
      </button>
    ))}
  </div>
);

export { PartsImportWizard };
