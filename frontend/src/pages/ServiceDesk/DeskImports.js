/**
 * Migration Import Wizard — Iter 255.
 *
 * 4-step guided import for service suppliers migrating onto the platform:
 * Upload (CSV/XLSX) → Map columns (rule-based + AI fallback) → Preview &
 * validate (errors + duplicates) → Commit (summary + error CSV download).
 * Backed by /api/svc/imports/*.
 */
import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import {
  Upload, Users, ClipboardList, Loader2, Sparkles, ArrowRight, ArrowLeft,
  CheckCircle2, AlertTriangle, Download, RotateCcw,
} from 'lucide-react';
import { authConfig } from './authConfig';

export default function DeskImports({ API, embedded = false }) {
  const { t } = useTranslation();
  const TYPES = [
    { id: 'customers', label: t('service.imp_type_customers', 'Customers & sites'), icon: Users, blurb: t('service.imp_type_customers_blurb', 'Names, contacts and site addresses → your customer book.') },
    { id: 'cases', label: t('service.imp_type_cases', 'Historical cases'), icon: ClipboardList, blurb: t('service.imp_type_cases_blurb', 'Past jobs imported as closed records with their original dates.') },
  ];
  const STEP_LABELS = [
    t('service.imp_step_upload', 'Upload'),
    t('service.imp_step_map', 'Map columns'),
    t('service.imp_step_preview', 'Preview'),
    t('service.imp_step_done', 'Done'),
  ];
  const fileRef = useRef(null);
  const [step, setStep] = useState(0);
  const [importType, setImportType] = useState('customers');
  const [busy, setBusy] = useState(false);
  const [aiBusy, setAiBusy] = useState(false);
  const [error, setError] = useState('');
  const [job, setJob] = useState(null);          // /parse response
  const [mapping, setMapping] = useState({});    // header -> field|''
  const [validation, setValidation] = useState(null);
  const [strategy, setStrategy] = useState('skip');
  const [result, setResult] = useState(null);

  const reset = () => {
    setStep(0); setJob(null); setMapping({}); setValidation(null);
    setResult(null); setError(''); setStrategy('skip');
    if (fileRef.current) fileRef.current.value = '';
  };

  const fail = (e, fallback) => setError(e.response?.data?.detail || fallback);

  const upload = async (file) => {
    if (!file) return;
    setBusy(true); setError('');
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('import_type', importType);
      const { data } = await axios.post(`${API}/svc/imports/parse`, fd, authConfig());
      setJob(data);
      setMapping(Object.fromEntries(
        Object.entries(data.suggested_mapping).map(([h, f]) => [h, f || ''])));
      setStep(1);
    } catch (e) { fail(e, t('service.imp_upload_failed', 'Upload failed')); } finally { setBusy(false); }
  };

  const askAi = async () => {
    const unmatched = Object.entries(mapping).filter(([, f]) => !f).map(([h]) => h);
    if (!unmatched.length) return;
    setAiBusy(true); setError('');
    try {
      const { data } = await axios.post(`${API}/svc/imports/${job.import_id}/ai-map`,
        { headers: unmatched }, authConfig());
      const found = Object.entries(data.mapping || {}).filter(([, f]) => f);
      if (!found.length) { setError(t('service.imp_ai_none', 'AI could not confidently map the remaining columns — pick them manually.')); return; }
      setMapping((m) => ({ ...m, ...Object.fromEntries(found) }));
    } catch (e) { fail(e, t('service.imp_ai_failed', 'AI mapping failed — map the remaining columns manually')); }
    finally { setAiBusy(false); }
  };

  const runValidate = async () => {
    setBusy(true); setError('');
    try {
      const { data } = await axios.post(`${API}/svc/imports/${job.import_id}/validate`,
        { mapping }, authConfig());
      setValidation(data);
      setStep(2);
    } catch (e) { fail(e, t('service.imp_validation_failed', 'Validation failed')); } finally { setBusy(false); }
  };

  const runCommit = async () => {
    setBusy(true); setError('');
    try {
      const { data } = await axios.post(`${API}/svc/imports/${job.import_id}/commit`,
        { mapping, duplicate_strategy: strategy }, authConfig());
      setResult(data);
      setStep(3);
    } catch (e) { fail(e, t('service.imp_import_failed', 'Import failed')); } finally { setBusy(false); }
  };

  const downloadErrors = async () => {
    const r = await axios.get(`${API}/svc/imports/${job.import_id}/errors.csv`,
      { ...authConfig(), responseType: 'blob' });
    const url = URL.createObjectURL(new Blob([r.data], { type: 'text/csv' }));
    const a = document.createElement('a');
    a.href = url; a.download = 'import-errors.csv';
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  };

  const fields = job?.target_fields || {};
  const usedFields = new Set(Object.values(mapping).filter(Boolean));
  const requiredUnmapped = Object.entries(fields)
    .filter(([k, v]) => v.required && !usedFields.has(k)).map(([, v]) => v.label);
  const unmatchedCount = Object.values(mapping).filter((f) => !f).length;

  return (
    <div className="space-y-6 max-w-4xl" data-testid="desk-imports">
      {!embedded && (
      <div>
        <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">{t('service.imp_title', 'Import data')}</h1>
        <p className="text-sm text-zinc-500 mt-1">
          {t('service.imp_subtitle', 'Migrate customers, sites and historical cases from spreadsheets or a legacy system.')}
        </p>
      </div>
      )}

      {/* Stepper */}
      <div className="flex items-center gap-2" data-testid="import-stepper">
        {STEP_LABELS.map((label, i) => (
          <div key={i} className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold ${
            i === step ? 'bg-orange-500 text-white'
              : i < step ? 'bg-emerald-50 text-emerald-700'
                : 'bg-white text-zinc-400 border border-zinc-200'
          }`} data-testid={`import-step-${i}`}>
            {i < step ? <CheckCircle2 size={13} /> : <span>{i + 1}.</span>} {label}
          </div>
        ))}
      </div>

      {error && (
        <div className="text-sm text-red-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2" data-testid="import-error">
          {error}
        </div>
      )}

      {/* Step 1 — type + upload */}
      {step === 0 && (
        <Card className="p-6 space-y-5" data-testid="import-upload-step">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {TYPES.map(({ id, label, icon: Icon, blurb }) => (
              <button key={id} onClick={() => setImportType(id)}
                className={`text-left p-4 rounded-xl border transition-colors ${
                  importType === id ? 'border-orange-500 bg-orange-50/50 ring-1 ring-orange-500/30' : 'border-zinc-200 hover:border-zinc-300'
                }`} data-testid={`import-type-${id}`}>
                <Icon size={18} className={importType === id ? 'text-orange-600' : 'text-zinc-400'} />
                <div className="text-sm font-semibold text-zinc-900 mt-2">{label}</div>
                <div className="text-xs text-zinc-500 mt-0.5">{blurb}</div>
              </button>
            ))}
          </div>
          <div className="border-2 border-dashed border-zinc-200 rounded-xl p-8 text-center">
            <Upload className="mx-auto text-zinc-400 mb-2" size={22} />
            <p className="text-sm text-zinc-600 mb-3">{t('service.imp_file_hint', 'CSV or Excel (.xlsx) — up to 10,000 rows / 10MB')}</p>
            <input ref={fileRef} type="file" accept=".csv,.xlsx" className="hidden"
              onChange={(e) => upload(e.target.files?.[0])} data-testid="import-file-input" />
            <button onClick={() => fileRef.current?.click()} disabled={busy}
              className="inline-flex items-center gap-2 bg-orange-500 hover:bg-orange-600 disabled:opacity-60 text-white text-sm font-semibold px-5 py-2.5 rounded-lg"
              data-testid="import-choose-file">
              {busy ? <Loader2 size={15} className="animate-spin" /> : <Upload size={15} />} {t('service.imp_choose_file', 'Choose file')}
            </button>
          </div>
        </Card>
      )}

      {/* Step 2 — column mapping */}
      {step === 1 && job && (
        <Card className="p-6 space-y-4" data-testid="import-mapping-step">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div className="text-sm text-zinc-600">
              <span className="font-semibold text-zinc-900">{job.row_count.toLocaleString()}</span> {t('service.imp_rows_in', 'rows in')}{' '}
              <span className="font-mono text-xs">{job.headers.length}</span> {t('service.imp_cols_match', 'columns — match each column to a field, or ignore it.')}
            </div>
            {unmatchedCount > 0 && (
              <button onClick={askAi} disabled={aiBusy}
                className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg bg-teal-50 text-teal-700 border border-teal-200 hover:bg-teal-100 disabled:opacity-60"
                data-testid="import-ai-map">
                {aiBusy ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
                {t('service.imp_ai_map', 'Ask AI to map {{n}} unmatched', { n: unmatchedCount })}
              </button>
            )}
          </div>
          <div className="divide-y divide-zinc-100">
            {job.headers.map((h) => (
              <div key={h} className="grid grid-cols-2 gap-3 items-center py-2" data-testid={`map-row-${h}`}>
                <div className="min-w-0">
                  <div className="text-sm font-medium text-zinc-800 truncate">{h}</div>
                  <div className="text-[11px] text-zinc-400 truncate">
                    {t('service.imp_eg', 'e.g.')} {(job.sample_rows || []).map((r) => r[h]).filter(Boolean).slice(0, 2).join(' · ') || '—'}
                  </div>
                </div>
                <select value={mapping[h] || ''} onChange={(e) => setMapping({ ...mapping, [h]: e.target.value })}
                  className="px-2 py-1.5 rounded-lg border border-zinc-200 text-sm bg-white"
                  data-testid={`map-select-${h}`}>
                  <option value="">{t('service.imp_ignore', '— Ignore —')}</option>
                  {Object.entries(fields).map(([k, v]) => (
                    <option key={k} value={k} disabled={usedFields.has(k) && mapping[h] !== k}>
                      {v.label}{v.required ? ' *' : ''}
                    </option>
                  ))}
                </select>
              </div>
            ))}
          </div>
          {requiredUnmapped.length > 0 && (
            <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2" data-testid="import-required-warning">
              {t('service.imp_required', 'Required:')} {requiredUnmapped.join(', ')}
            </div>
          )}
          <div className="flex gap-3">
            <button onClick={reset} className="inline-flex items-center gap-1.5 px-4 py-2 text-sm text-zinc-600 hover:text-zinc-900">
              <ArrowLeft size={14} /> {t('service.imp_start_over', 'Start over')}
            </button>
            <button onClick={runValidate} disabled={busy || requiredUnmapped.length > 0}
              className="inline-flex items-center gap-2 bg-orange-500 hover:bg-orange-600 disabled:opacity-60 text-white text-sm font-semibold px-5 py-2.5 rounded-lg"
              data-testid="import-validate">
              {busy ? <Loader2 size={15} className="animate-spin" /> : <>{t('service.imp_preview_import', 'Preview import')} <ArrowRight size={15} /></>}
            </button>
          </div>
        </Card>
      )}

      {/* Step 3 — preview & validate */}
      {step === 2 && validation && (
        <Card className="p-6 space-y-5" data-testid="import-preview-step">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="rounded-xl bg-emerald-50 border border-emerald-100 p-4" data-testid="import-valid-count">
              <div className="text-2xl font-bold text-emerald-700 tabular-nums">{validation.valid_count.toLocaleString()}</div>
              <div className="text-xs text-emerald-700/80">{t('service.imp_ready', 'Ready to import')}</div>
            </div>
            <div className="rounded-xl bg-amber-50 border border-amber-100 p-4" data-testid="import-dupe-count">
              <div className="text-2xl font-bold text-amber-700 tabular-nums">{validation.duplicate_count.toLocaleString()}</div>
              <div className="text-xs text-amber-700/80">{t('service.imp_possible_dupes', 'Possible duplicates')}</div>
            </div>
            <div className="rounded-xl bg-red-50 border border-red-100 p-4" data-testid="import-error-count">
              <div className="text-2xl font-bold text-red-700 tabular-nums">{validation.error_count.toLocaleString()}</div>
              <div className="text-xs text-red-700/80">{t('service.imp_rows_errors', 'Rows with errors')}</div>
            </div>
          </div>

          {validation.duplicate_count > 0 && (
            <div className="flex items-center gap-4 text-sm" data-testid="import-dupe-strategy">
              <span className="text-zinc-600 font-medium">{t('service.imp_duplicates', 'Duplicates:')}</span>
              {[['skip', importType === 'cases' ? t('service.imp_skip_ref', 'Skip (matched by reference)') : t('service.imp_skip_existing', 'Skip existing')],
                ...(importType === 'customers' ? [['update', t('service.imp_update_existing', 'Update existing')]] : [])].map(([v, label]) => (
                <label key={v} className="inline-flex items-center gap-1.5 cursor-pointer">
                  <input type="radio" name="dupe" checked={strategy === v} onChange={() => setStrategy(v)}
                    data-testid={`dupe-strategy-${v}`} />
                  <span className="text-zinc-700">{label}</span>
                </label>
              ))}
            </div>
          )}

          {validation.errors.length > 0 && (
            <div className="space-y-1.5" data-testid="import-errors-list">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-red-700">
                <AlertTriangle size={13} /> {t('service.imp_first_errors', 'First {{n}} errors (these rows will be skipped)', { n: Math.min(validation.errors.length, 50) })}
              </div>
              <div className="max-h-40 overflow-y-auto rounded-lg border border-zinc-100 divide-y divide-zinc-50 text-xs">
                {validation.errors.map((e, i) => (
                  <div key={i} className="px-3 py-1.5 flex gap-3">
                    <span className="text-zinc-400 shrink-0">{t('service.imp_row', 'Row {{n}}', { n: e.row })}</span>
                    <span className="text-zinc-700">{e.reason}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {validation.preview.length > 0 && (
            <div className="overflow-x-auto rounded-lg border border-zinc-100" data-testid="import-preview-table">
              <table className="w-full text-xs">
                <thead className="bg-zinc-50 text-zinc-500">
                  <tr>{Object.keys(validation.preview[0]).map((k) => (
                    <th key={k} className="text-left px-3 py-2 font-semibold whitespace-nowrap">{fields[k]?.label || k}</th>
                  ))}</tr>
                </thead>
                <tbody className="divide-y divide-zinc-50">
                  {validation.preview.map((r, i) => (
                    <tr key={i}>{Object.keys(validation.preview[0]).map((k) => (
                      <td key={k} className="px-3 py-1.5 text-zinc-700 whitespace-nowrap max-w-[180px] truncate">{r[k] || '—'}</td>
                    ))}</tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="flex gap-3">
            <button onClick={() => setStep(1)} className="inline-flex items-center gap-1.5 px-4 py-2 text-sm text-zinc-600 hover:text-zinc-900">
              <ArrowLeft size={14} /> {t('service.imp_back_mapping', 'Back to mapping')}
            </button>
            <button onClick={runCommit} disabled={busy || validation.valid_count === 0}
              className="inline-flex items-center gap-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white text-sm font-semibold px-5 py-2.5 rounded-lg"
              data-testid="import-commit">
              {busy ? <Loader2 size={15} className="animate-spin" /> : <>{t('service.imp_import_n', 'Import {{n}} rows', { n: validation.valid_count.toLocaleString() })} <ArrowRight size={15} /></>}
            </button>
          </div>
        </Card>
      )}

      {/* Step 4 — done */}
      {step === 3 && result && (
        <Card className="p-6 space-y-5" data-testid="import-done-step">
          <div className="flex items-center gap-2 text-emerald-700">
            <CheckCircle2 size={20} />
            <div className="text-lg font-semibold">{t('service.imp_complete', 'Import complete')}</div>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[[t('service.imp_created', 'Created'), result.created, 'text-emerald-700', 'import-result-created'],
              [t('service.imp_updated', 'Updated'), result.updated, 'text-sky-700', 'import-result-updated'],
              [t('service.imp_skipped', 'Skipped'), result.skipped, 'text-zinc-600', 'import-result-skipped'],
              [t('service.imp_errored', 'Errored'), result.errored, 'text-red-700', 'import-result-errored']].map(([label, v, tone, tid]) => (
              <div key={tid} className="rounded-xl border border-zinc-100 p-4" data-testid={tid}>
                <div className={`text-2xl font-bold tabular-nums ${tone}`}>{Number(v).toLocaleString()}</div>
                <div className="text-xs text-zinc-500">{label}</div>
              </div>
            ))}
          </div>
          <div className="flex gap-3 flex-wrap">
            {result.errored > 0 && (
              <button onClick={downloadErrors}
                className="inline-flex items-center gap-2 border border-zinc-200 hover:bg-zinc-50 text-zinc-700 text-sm font-semibold px-4 py-2 rounded-lg"
                data-testid="import-download-errors">
                <Download size={14} /> {t('service.imp_download_errors', 'Download errored rows (CSV)')}
              </button>
            )}
            <button onClick={reset}
              className="inline-flex items-center gap-2 bg-orange-500 hover:bg-orange-600 text-white text-sm font-semibold px-4 py-2 rounded-lg"
              data-testid="import-another">
              <RotateCcw size={14} /> {t('service.imp_another', 'Import another file')}
            </button>
          </div>
        </Card>
      )}
    </div>
  );
}
