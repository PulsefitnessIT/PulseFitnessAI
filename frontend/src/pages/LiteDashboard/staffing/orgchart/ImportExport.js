/** Org Chart — CSV import wizard + export. */
import { useState } from 'react';
import Papa from 'papaparse';
import { toast } from 'sonner';
import {
  UploadCloud, FileSpreadsheet, Download, CheckCircle2, AlertTriangle, ArrowRight, Loader2, Image as ImageIcon, FileText,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { ocApi } from './api';
import DocumentImport from './DocumentImport';

const TARGET_FIELDS = [
  { key: 'full_name', label: 'Name', required: true },
  { key: 'email', label: 'Email' },
  { key: 'phone', label: 'Phone' },
  { key: 'job_title', label: 'Job title' },
  { key: 'department', label: 'Department' },
  { key: 'manager_name', label: 'Manager (name)' },
  { key: 'employment_type', label: 'Employment type' },
  { key: 'vacancy', label: 'Is vacancy (yes/no)' },
];

const guess = (header) => {
  const h = header.toLowerCase().replace(/[^a-z]/g, '');
  if (h.includes('name') && h.includes('manager')) return 'manager_name';
  if (h.includes('manager') || h.includes('reportsto')) return 'manager_name';
  if (h.includes('fullname') || h === 'name' || h.includes('employee')) return 'full_name';
  if (h.includes('email')) return 'email';
  if (h.includes('phone') || h.includes('mobile')) return 'phone';
  if (h.includes('title') || h.includes('role') || h.includes('position')) return 'job_title';
  if (h.includes('depart') || h.includes('team')) return 'department';
  if (h.includes('contract') || h.includes('employ')) return 'employment_type';
  if (h.includes('vacan') || h.includes('open')) return 'vacancy';
  return '';
};

export default function ImportExport({ chartId, onImported, onExportImage, onExportPdf }) {
  const { t } = useTranslation();
  const [step, setStep] = useState(1);
  const [rawRows, setRawRows] = useState([]);
  const [headers, setHeaders] = useState([]);
  const [mapping, setMapping] = useState({});
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [linkExisting, setLinkExisting] = useState(true);

  const handleFile = (file) => {
    Papa.parse(file, {
      header: true, skipEmptyLines: true,
      complete: (res) => {
        const cols = res.meta.fields || [];
        setHeaders(cols);
        setRawRows(res.data);
        const m = {};
        cols.forEach((c) => { const g = guess(c); if (g && !Object.values(m).includes(g)) m[c] = g; });
        setMapping(m);
        setStep(2);
      },
      error: () => toast.error(t('orgchart.ie_read_err', 'Could not read that file')),
    });
  };

  const buildRows = () => rawRows.map((r) => {
    const out = {};
    Object.entries(mapping).forEach(([col, field]) => { if (field) out[field] = r[col]; });
    return out;
  }).filter((r) => (r.full_name || '').trim());

  const runPreview = async () => {
    setBusy(true);
    try {
      const rows = buildRows();
      const p = await ocApi.importPreview(chartId, rows);
      setPreview({ ...p, rows: rows });
      setStep(3);
    } catch { toast.error(t('orgchart.ie_validation_failed', 'Validation failed')); } finally { setBusy(false); }
  };

  const apply = async () => {
    setBusy(true);
    try {
      const res = await ocApi.importApply(chartId, preview.rows, { link_existing: linkExisting });
      toast.success(t('orgchart.ie_imported', 'Imported {{count}} cards', { count: res.imported }));
      setStep(4);
      onImported?.();
    } catch { toast.error(t('orgchart.ie_import_failed', 'Import failed')); } finally { setBusy(false); }
  };

  const reset = () => { setStep(1); setRawRows([]); setHeaders([]); setMapping({}); setPreview(null); };

  return (
    <div className="space-y-5" data-testid="orgchart-import-export">
      {/* Import an existing chart (PDF / image) */}
      <DocumentImport chartId={chartId} onImported={onImported} />

      {/* Export */}
      <div className="rounded-2xl border p-4" style={{ borderColor: 'var(--theme-border)' }}>
        <h4 className="text-sm font-bold mb-3 inline-flex items-center gap-2" style={{ color: 'var(--theme-text)' }}><Download size={15} /> {t('orgchart.ie_export', 'Export')}</h4>
        <div className="flex flex-wrap gap-2">
          <a href={ocApi.exportCsvUrl(chartId)} className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold border" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="orgchart-export-csv">
            <FileSpreadsheet size={14} /> {t('orgchart.ie_csv', 'CSV')}
          </a>
          <button onClick={onExportImage} className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold border" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="orgchart-export-png">
            <ImageIcon size={14} /> {t('orgchart.ie_png', 'PNG image')}
          </button>
          <button onClick={onExportPdf} className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold border" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="orgchart-export-pdf">
            <FileText size={14} /> {t('orgchart.ie_pdf', 'PDF')}
          </button>
        </div>
        <p className="text-[11px] mt-2" style={{ color: 'var(--theme-text-muted)' }}>{t('orgchart.ie_export_note', 'PNG/PDF capture the full chart — we automatically open and fit the chart view before exporting.')}</p>
      </div>

      {/* Import */}
      <div className="rounded-2xl border p-4" style={{ borderColor: 'var(--theme-border)' }}>
        <h4 className="text-sm font-bold mb-3 inline-flex items-center gap-2" style={{ color: 'var(--theme-text)' }}><UploadCloud size={15} /> {t('orgchart.ie_import_csv', 'Import from CSV / Excel')}</h4>

        {step === 1 && (
          <label className="block rounded-xl border-2 border-dashed p-8 text-center cursor-pointer" style={{ borderColor: 'var(--theme-border)' }} data-testid="orgchart-import-drop">
            <UploadCloud size={26} className="mx-auto mb-2" style={{ color: 'var(--theme-text-muted)' }} />
            <p className="text-sm font-semibold" style={{ color: 'var(--theme-text)' }}>{t('orgchart.ie_choose_csv', 'Choose a CSV file')}</p>
            <p className="text-[11px] mt-1" style={{ color: 'var(--theme-text-muted)' }}>{t('orgchart.ie_csv_cols', 'Columns: name, email, job title, department, manager, vacancy…')}</p>
            <input type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => e.target.files[0] && handleFile(e.target.files[0])} data-testid="orgchart-import-file" />
          </label>
        )}

        {step === 2 && (
          <div data-testid="orgchart-import-mapping">
            <p className="text-xs mb-3" style={{ color: 'var(--theme-text-muted)' }}>{t('orgchart.ie_map_cols', 'Map your columns to chart fields ({{count}} rows found).', { count: rawRows.length })}</p>
            <div className="space-y-2 max-h-72 overflow-y-auto">
              {headers.map((col) => (
                <div key={col} className="flex items-center gap-2">
                  <span className="text-xs font-semibold w-40 truncate" style={{ color: 'var(--theme-text)' }}>{col}</span>
                  <ArrowRight size={12} style={{ color: 'var(--theme-text-muted)' }} />
                  <select value={mapping[col] || ''} onChange={(e) => setMapping({ ...mapping, [col]: e.target.value })}
                    className="flex-1 px-2 py-1.5 rounded-lg text-xs border outline-none" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-bg,#fff)', color: 'var(--theme-text)' }}>
                    <option value="">{t('orgchart.ie_ignore', '— Ignore —')}</option>
                    {TARGET_FIELDS.map((f) => <option key={f.key} value={f.key}>{t(`orgchart.ie_field_${f.key}`, f.label)}{f.required ? ' *' : ''}</option>)}
                  </select>
                </div>
              ))}
            </div>
            <div className="flex gap-2 mt-4">
              <button onClick={runPreview} disabled={busy || !Object.values(mapping).includes('full_name')} className="px-4 py-2 rounded-lg text-xs font-bold inline-flex items-center gap-1.5 disabled:opacity-50" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }} data-testid="orgchart-import-validate">
                {busy ? <Loader2 size={13} className="animate-spin" /> : null} {t('orgchart.ie_validate', 'Validate & preview')}
              </button>
              <button onClick={reset} className="px-4 py-2 rounded-lg text-xs font-semibold" style={{ color: 'var(--theme-text-muted)' }}>{t('orgchart.set_cancel', 'Cancel')}</button>
            </div>
          </div>
        )}

        {step === 3 && preview && (
          <div data-testid="orgchart-import-preview">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-3">
              {[[t('orgchart.ie_total', 'Total'), preview.total], [t('orgchart.ie_matched', 'Matched staff'), preview.matched], [t('orgchart.ie_new', 'New'), preview.new], [t('orgchart.ie_vacancies', 'Vacancies'), preview.vacancies]].map(([l, v]) => (
                <div key={l} className="rounded-xl border p-2.5" style={{ borderColor: 'var(--theme-border)' }}>
                  <div className="text-lg font-bold" style={{ color: 'var(--theme-text)' }}>{v}</div>
                  <div className="text-[10px] uppercase tracking-wide" style={{ color: 'var(--theme-text-muted)' }}>{l}</div>
                </div>
              ))}
            </div>
            {!!preview.warnings.length && (
              <div className="rounded-xl border p-2.5 mb-3 text-xs" style={{ borderColor: '#fcd34d', background: '#fffbeb', color: '#92400e' }}>
                <AlertTriangle size={13} className="inline mr-1" /> {t('orgchart.ie_warnings', "{{count}} row(s) have issues — they'll be skipped or imported as placeholders.", { count: preview.warnings.length })}
              </div>
            )}
            <label className="flex items-center gap-2 text-xs mb-3" style={{ color: 'var(--theme-text)' }}>
              <input type="checkbox" checked={linkExisting} onChange={(e) => setLinkExisting(e.target.checked)} data-testid="orgchart-import-link" />
              {t('orgchart.ie_link', 'Link rows to existing staff records when name/email matches')}
            </label>
            <div className="flex gap-2">
              <button onClick={apply} disabled={busy} className="px-4 py-2 rounded-lg text-xs font-bold inline-flex items-center gap-1.5 disabled:opacity-50" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }} data-testid="orgchart-import-apply">
                {busy ? <Loader2 size={13} className="animate-spin" /> : <CheckCircle2 size={13} />} {t('orgchart.ie_confirm', 'Confirm import')}
              </button>
              <button onClick={() => setStep(2)} className="px-4 py-2 rounded-lg text-xs font-semibold" style={{ color: 'var(--theme-text-muted)' }}>{t('orgchart.ie_back', 'Back')}</button>
            </div>
          </div>
        )}

        {step === 4 && (
          <div className="text-center py-6" data-testid="orgchart-import-done">
            <CheckCircle2 size={28} className="mx-auto mb-2" style={{ color: '#16a34a' }} />
            <p className="text-sm font-semibold" style={{ color: 'var(--theme-text)' }}>{t('orgchart.ie_complete', 'Import complete')}</p>
            <button onClick={reset} className="mt-3 px-4 py-2 rounded-lg text-xs font-bold" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}>{t('orgchart.ie_import_another', 'Import another file')}</button>
          </div>
        )}
      </div>
    </div>
  );
}
