/**
 * Inline equipment importer for Account Settings → Onboarding.
 *
 * The equipment-management actions that used to live on the Equipment hub
 * (Add Equipment / AI Invoice Import / Export CSV) now live here, inside the
 * Onboarding "Import equipment" step — gyms set equipment up once during
 * onboarding and rarely touch these day-to-day.
 *
 * Modes:
 *   • Spreadsheet — CSV / .xlsx upload (Excel-serial dates parsed) + template
 *   • AI Invoice Import — pull equipment straight from a supplier invoice PDF
 *   • Add manually — single-machine dialog
 * Plus an Export CSV action.
 */
import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { toast } from 'sonner';
import { Download, Upload, Loader2, CheckCircle2, AlertCircle, FileSpreadsheet, Sparkles, Plus } from 'lucide-react';
import { API, useAuthHeaders } from './shared';
import InvoiceImportWizard from '@/pages/InvoiceImportWizard';
import AddEquipmentDialog from '@/components/equipment/AddEquipmentDialog';

export default function EquipmentImportInline({ onClose, onImported }) {
  const { t } = useTranslation();
  const headers = useAuthHeaders();
  const inputRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [mode, setMode] = useState('spreadsheet'); // spreadsheet | invoice
  const [showAdd, setShowAdd] = useState(false);

  const authToken = () => localStorage.getItem('token') || localStorage.getItem('gymaxis_token');

  const downloadTemplate = async () => {
    try {
      const r = await fetch(`${API}/account/import/equipment/template`, {
        headers: authToken() ? { Authorization: `Bearer ${authToken()}` } : {},
      });
      if (!r.ok) throw new Error('Template download failed');
      const blob = await r.blob();
      const dl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = dl; a.download = 'equipment-template.csv'; a.click();
      URL.revokeObjectURL(dl);
    } catch {
      toast.error(t('settings.eqimp_template_failed', 'Could not download the template'));
    }
  };

  const exportCsv = async () => {
    try {
      const res = await axios.get(`${API}/equipment/export/csv`, {
        headers: headers(), responseType: 'blob',
      });
      const url = URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a');
      a.href = url; a.download = 'equipment_export.csv'; a.click();
      URL.revokeObjectURL(url);
      toast.success(t('settings.eqimp_exported', 'Equipment exported'));
    } catch {
      toast.error(t('settings.eqimp_export_failed', 'Failed to export equipment'));
    }
  };

  const handleFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true); setError(''); setResult(null);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const r = await axios.post(`${API}/account/import/equipment`, fd, {
        headers: { ...headers(), 'Content-Type': 'multipart/form-data' },
      });
      setResult(r.data);
      toast.success(t('settings.eqimp_imported_n', 'Imported {{n}} items', { n: r.data.imported || 0 }));
      onImported && onImported();
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || t('settings.eqimp_failed', 'Import failed');
      setError(typeof msg === 'string' ? msg : t('settings.eqimp_failed', 'Import failed'));
      toast.error(t('settings.eqimp_failed', 'Import failed'));
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = '';
    }
  };

  const modeBtn = (key, Icon, label) => (
    <button
      type="button"
      onClick={() => setMode(key)}
      className={`inline-flex items-center gap-2 ${mode === key ? 'account-btn-primary' : 'account-btn-secondary'}`}
      data-testid={`account-equip-mode-${key}`}
    >
      <Icon size={14} /> {label}
    </button>
  );

  return (
    <div className="space-y-4" data-testid="account-equipment-import-inline">
      {/* Action toolbar — mirrors the old Equipment hub buttons */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-2">
          {modeBtn('spreadsheet', FileSpreadsheet, t('settings.eqimp_spreadsheet', 'Spreadsheet'))}
          {modeBtn('invoice', Sparkles, t('settings.eqimp_ai_invoice', 'AI Invoice Import'))}
          <button
            type="button"
            onClick={() => setShowAdd(true)}
            className="account-btn-secondary inline-flex items-center gap-2"
            data-testid="account-equip-add-manual"
          >
            <Plus size={14} /> {t('settings.eqimp_add_equipment', 'Add Equipment')}
          </button>
        </div>
        <button
          type="button"
          onClick={exportCsv}
          className="account-btn-secondary inline-flex items-center gap-2"
          data-testid="account-equip-export-csv"
        >
          <Download size={14} /> {t('settings.eqimp_export_csv', 'Export CSV')}
        </button>
      </div>

      {mode === 'spreadsheet' && (
        <>
          <div>
            <h3 className="text-base font-semibold" style={{ color: 'var(--theme-text)' }}>{t('settings.eqimp_title', 'Import equipment')}</h3>
            <p className="text-xs mt-1" style={{ color: 'var(--theme-text-muted)' }}>
              {t('settings.eqimp_sub', 'Upload a CSV or Excel (.xlsx) spreadsheet using the standard template. Dates can be in any common format — Excel serial numbers (e.g. 45979), dd/mm/yyyy, or ISO YYYY-MM-DD all parse correctly.')}
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={downloadTemplate} className="account-btn-secondary inline-flex items-center gap-2" data-testid="account-import-template-btn">
              <Download size={14} /> {t('settings.eqimp_download_template', 'Download template')}
            </button>
            <button type="button" onClick={() => inputRef.current?.click()} disabled={busy} className="account-btn-primary inline-flex items-center gap-2 disabled:opacity-50" data-testid="account-import-upload-btn">
              {busy ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
              {busy ? t('settings.eqimp_importing', 'Importing…') : t('settings.eqimp_choose_file', 'Choose file')}
            </button>
            <input ref={inputRef} type="file" accept=".csv,.xlsx,.xlsm" className="hidden" onChange={handleFile} data-testid="account-import-file-input" />
          </div>

          {result && (
            <div className="rounded-xl p-4 text-sm border" style={{ background: 'rgba(16,185,129,0.08)', borderColor: 'rgba(16,185,129,0.3)' }} data-testid="account-import-result">
              <div className="flex items-start gap-2">
                <CheckCircle2 size={16} className="mt-0.5 flex-shrink-0" style={{ color: 'rgb(16,185,129)' }} />
                <div className="flex-1">
                  <p className="font-semibold" style={{ color: 'var(--theme-text)' }}>
                    {t('settings.eqimp_items_imported', '{{n}} item(s) imported', { n: result.imported, count: result.imported })}
                    {result.skipped ? ` · ${t('settings.eqimp_skipped', '{{n}} skipped', { n: result.skipped })}` : ''}
                  </p>
                  {result.error_count > 0 && (
                    <p className="text-xs mt-1" style={{ color: 'var(--theme-text-muted)' }}>
                      {t('settings.eqimp_rows_issues', '{{n}} row(s) reported issues — see below.', { n: result.error_count, count: result.error_count })}
                    </p>
                  )}
                </div>
              </div>
              {result.errors?.length > 0 && (
                <ul className="mt-3 text-xs space-y-0.5 max-h-32 overflow-auto" style={{ color: 'var(--theme-text-muted)' }}>
                  {result.errors.slice(0, 20).map((err, i) => <li key={i}>• {err}</li>)}
                </ul>
              )}
            </div>
          )}

          {error && (
            <div className="rounded-xl p-3 text-sm border" style={{ background: 'rgba(239,68,68,0.08)', borderColor: 'rgba(239,68,68,0.3)' }} data-testid="account-import-error">
              <div className="flex items-start gap-2">
                <AlertCircle size={14} className="mt-0.5 flex-shrink-0" style={{ color: 'rgb(239,68,68)' }} />
                <p style={{ color: 'var(--theme-text)' }}>{error}</p>
              </div>
            </div>
          )}
        </>
      )}

      {mode === 'invoice' && (
        <div data-testid="account-equip-invoice-wizard">
          <InvoiceImportWizard onComplete={() => { onImported && onImported(); }} />
        </div>
      )}

      <div className="flex justify-end pt-2">
        <button type="button" onClick={onClose} className="account-btn-secondary" data-testid="account-import-close">
          {t('settings.eqimp_back_checklist', 'Back to checklist')}
        </button>
      </div>

      <AddEquipmentDialog
        open={showAdd}
        onClose={() => setShowAdd(false)}
        onCreated={() => { setShowAdd(false); onImported && onImported(); }}
      />
    </div>
  );
}
