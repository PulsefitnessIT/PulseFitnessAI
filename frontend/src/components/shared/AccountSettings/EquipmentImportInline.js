/**
 * Inline equipment importer for Account Settings → Onboarding (Iter 216h108).
 *
 * Previously, clicking "Import equipment" navigated away to
 * /pulse?tab=equipment, dropping the user out of the settings modal.
 * Now the import happens IN-PLACE — same template + parser as Master
 * Admin uses (POST /api/account/import/equipment).
 *
 * Supports:
 *   • CSV and .xlsx upload (Excel-serial dates parsed correctly)
 *   • Download a fresh template
 *   • Live progress + result summary
 */
import { useRef, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Download, Upload, Loader2, CheckCircle2, AlertCircle } from 'lucide-react';
import { API, useAuthHeaders } from './shared';

export default function EquipmentImportInline({ onClose, onImported }) {
  const headers = useAuthHeaders();
  const inputRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  const downloadTemplate = async () => {
    const token = localStorage.getItem('token') || localStorage.getItem('gymaxis_token');
    const url = `${API}/account/import/equipment/template`;
    try {
      const r = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
      if (!r.ok) throw new Error('Template download failed');
      const blob = await r.blob();
      const dl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = dl; a.download = 'equipment-template.csv'; a.click();
      URL.revokeObjectURL(dl);
    } catch {
      toast.error('Could not download the template');
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
      toast.success(`Imported ${r.data.imported || 0} items`);
      onImported && onImported();
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || 'Import failed';
      setError(typeof msg === 'string' ? msg : 'Import failed');
      toast.error('Import failed');
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = '';
    }
  };

  return (
    <div className="space-y-4" data-testid="account-equipment-import-inline">
      <div>
        <h3 className="text-base font-semibold" style={{ color: 'var(--theme-text)' }}>Import equipment</h3>
        <p className="text-xs mt-1" style={{ color: 'var(--theme-text-muted)' }}>
          Upload a CSV or Excel (.xlsx) spreadsheet using the standard template. Dates can be in any common format —
          Excel serial numbers (e.g. <code>45979</code>), <code>dd/mm/yyyy</code>, or ISO <code>YYYY-MM-DD</code> all parse correctly.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={downloadTemplate}
          className="account-btn-secondary inline-flex items-center gap-2"
          data-testid="account-import-template-btn"
        >
          <Download size={14} /> Download template
        </button>
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={busy}
          className="account-btn-primary inline-flex items-center gap-2 disabled:opacity-50"
          data-testid="account-import-upload-btn"
        >
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
          {busy ? 'Importing…' : 'Choose file'}
        </button>
        <input
          ref={inputRef}
          type="file"
          accept=".csv,.xlsx,.xlsm"
          className="hidden"
          onChange={handleFile}
          data-testid="account-import-file-input"
        />
      </div>

      {result && (
        <div
          className="rounded-xl p-4 text-sm border"
          style={{ background: 'rgba(16,185,129,0.08)', borderColor: 'rgba(16,185,129,0.3)' }}
          data-testid="account-import-result"
        >
          <div className="flex items-start gap-2">
            <CheckCircle2 size={16} className="mt-0.5 flex-shrink-0" style={{ color: 'rgb(16,185,129)' }} />
            <div className="flex-1">
              <p className="font-semibold" style={{ color: 'var(--theme-text)' }}>
                {result.imported} item{result.imported === 1 ? '' : 's'} imported
                {result.skipped ? ` · ${result.skipped} skipped` : ''}
              </p>
              {result.error_count > 0 && (
                <p className="text-xs mt-1" style={{ color: 'var(--theme-text-muted)' }}>
                  {result.error_count} row{result.error_count === 1 ? '' : 's'} reported issues — see below.
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
        <div
          className="rounded-xl p-3 text-sm border"
          style={{ background: 'rgba(239,68,68,0.08)', borderColor: 'rgba(239,68,68,0.3)' }}
          data-testid="account-import-error"
        >
          <div className="flex items-start gap-2">
            <AlertCircle size={14} className="mt-0.5 flex-shrink-0" style={{ color: 'rgb(239,68,68)' }} />
            <p style={{ color: 'var(--theme-text)' }}>{error}</p>
          </div>
        </div>
      )}

      <div className="flex justify-end pt-2">
        <button
          type="button"
          onClick={onClose}
          className="account-btn-secondary"
          data-testid="account-import-close"
        >
          Back to checklist
        </button>
      </div>
    </div>
  );
}
