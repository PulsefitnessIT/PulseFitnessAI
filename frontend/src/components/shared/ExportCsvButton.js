import { useState } from 'react';
import axios from 'axios';
import { useAuth } from '@/App';
import { Download, Loader2 } from 'lucide-react';

/**
 * ExportCsvButton (iter 215c0)
 * Reusable CSV download button. Streams /api/export/{module}.csv.
 *
 * Usage: <ExportCsvButton module="members" label="Export members" />
 */
const ExportCsvButton = ({ module, label = 'Export CSV', className = '', testId }) => {
  const { API } = useAuth();
  const [busy, setBusy] = useState(false);

  const click = async () => {
    if (busy) return;
    setBusy(true);
    const token = localStorage.getItem('token');
    try {
      const res = await axios.get(`${API}/export/${module}.csv`, {
        headers: { Authorization: `Bearer ${token}` },
        responseType: 'blob',
      });
      const blob = new Blob([res.data], { type: 'text/csv' });
      const href = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = href;
      const stamp = new Date().toISOString().slice(0, 10).replace(/-/g, '');
      a.download = `${module}_${stamp}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(href);
    } catch (e) {
      // Surface a small toast via window event so callers can wire to their notifier.
      window.dispatchEvent(new CustomEvent('app:toast', { detail: { type: 'error', message: 'Export failed. Please try again.' } }));
    } finally {
      setBusy(false);
    }
  };

  return (
    <button
      type="button"
      onClick={click}
      disabled={busy}
      data-testid={testId || `export-csv-${module}`}
      className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium border border-[var(--theme-border)] bg-[var(--theme-surface)] text-[var(--theme-text)] hover:bg-[var(--theme-surface-hover)] transition ${className}`}
    >
      {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
      <span>{label}</span>
    </button>
  );
};

export default ExportCsvButton;
