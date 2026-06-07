/**
 * CRM · Master Price List — "Clear price list" (permanent, owner-only).
 *
 * Two modes:
 *   - all           → wipe the entire price list (clean slate to re-import)
 *   - import_batch  → delete only the products from the most recent import
 *
 * Both are permanent hard-deletes guarded by a typed "DELETE" confirmation,
 * and the modal nudges the owner to export a backup first.
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { X, Loader2, Trash2, AlertTriangle, FileDown } from 'lucide-react';

export default function CRMClearPriceListModal({ API, headers, c, isDark, total = 0, onExport, onClose, onDone }) {
  const [mode, setMode] = useState('all');
  const [batches, setBatches] = useState([]);
  const [confirmText, setConfirmText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const border = isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)';
  const surface2 = isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-50)';

  const loadBatches = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/crm/products/import-batches`, { headers: headers() });
      setBatches(r.data.batches || []);
    } catch (e) { /* silent */ }
  }, [API, headers]);

  useEffect(() => { loadBatches(); }, [loadBatches]);

  const lastBatch = batches[0];
  const targetCount = mode === 'all' ? total : (lastBatch?.count || 0);
  const canDelete = confirmText.trim() === 'DELETE' && !busy
    && (mode === 'all' || !!lastBatch);

  const runDelete = async () => {
    setBusy(true); setError('');
    try {
      const body = { mode, confirm: confirmText.trim() };
      if (mode === 'import_batch') body.import_batch_id = lastBatch.import_batch_id;
      const r = await axios.post(`${API}/crm/products/bulk-delete`, body, { headers: headers() });
      onDone?.(r.data);
      onClose?.();
    } catch (e) {
      setError(e?.response?.data?.detail || 'Delete failed');
    }
    setBusy(false);
  };

  return (
    <div className="fixed inset-0 z-[260] flex items-center justify-center bg-black/50 backdrop-blur-sm p-3" data-testid="clear-price-list-modal">
      <div className="w-full max-w-lg max-h-[92vh] flex flex-col rounded-2xl shadow-2xl border" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: border }}>
        <div className="flex items-center justify-between px-5 py-3 border-b" style={{ borderColor: border }}>
          <h3 className="text-sm font-semibold flex items-center gap-2" style={{ color: 'var(--color-danger-alt)' }}>
            <Trash2 size={15} /> Clear price list
          </h3>
          <button type="button" onClick={onClose} className="opacity-60 hover:opacity-100" data-testid="clear-close"><X size={16} /></button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          <div className="flex items-start gap-2 text-xs rounded-md px-3 py-2" style={{ background: 'rgba(239,68,68,0.08)', color: 'var(--color-danger-alt)' }}>
            <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" />
            <span>This permanently deletes products and <strong>cannot be undone</strong>. Export a backup first if you might need the data.</span>
          </div>

          {error && <div className="text-xs px-3 py-1.5 rounded-md" style={{ background: 'rgba(239,68,68,0.08)', color: 'var(--color-danger-alt)' }} data-testid="clear-error">{error}</div>}

          {/* Backup nudge */}
          <button
            type="button"
            onClick={() => { onExport?.(); }}
            className="w-full inline-flex items-center justify-center gap-1.5 text-xs font-semibold px-3 py-2 rounded-md border"
            style={{ borderColor: border, color: c.text }}
            data-testid="clear-export-first"
          >
            <FileDown size={13} /> Export a backup first
          </button>

          {/* Mode selection */}
          <div className="space-y-2">
            <label className="flex items-start gap-2 rounded-lg border p-3 cursor-pointer" style={{ borderColor: mode === 'all' ? 'var(--color-danger-alt)' : border, background: surface2 }} data-testid="clear-mode-all">
              <input type="radio" name="clear-mode" checked={mode === 'all'} onChange={() => setMode('all')} className="mt-0.5" />
              <div>
                <div className="text-xs font-semibold" style={{ color: c.text }}>Clear entire price list</div>
                <div className="text-[11px]" style={{ color: c.textMuted }}>
                  Delete <strong>all {total}</strong> product{total === 1 ? '' : 's'} so counts reset to 0 — a clean slate to re-import.
                </div>
              </div>
            </label>

            <label className="flex items-start gap-2 rounded-lg border p-3 cursor-pointer" style={{ borderColor: mode === 'import_batch' ? 'var(--color-danger-alt)' : border, background: surface2, opacity: lastBatch ? 1 : 0.55 }} data-testid="clear-mode-batch">
              <input type="radio" name="clear-mode" checked={mode === 'import_batch'} onChange={() => setMode('import_batch')} disabled={!lastBatch} className="mt-0.5" />
              <div>
                <div className="text-xs font-semibold" style={{ color: c.text }}>Undo last import only</div>
                <div className="text-[11px]" style={{ color: c.textMuted }}>
                  {lastBatch
                    ? <>Delete the <strong>{lastBatch.count}</strong> product{lastBatch.count === 1 ? '' : 's'} from the most recent import{lastBatch.last ? ` (${new Date(lastBatch.last).toLocaleString()})` : ''}.</>
                    : 'No import batches found on this price list.'}
                </div>
              </div>
            </label>
          </div>

          {/* Typed confirm */}
          <div>
            <label className="text-[11px] uppercase tracking-wide" style={{ color: c.textDim }}>Type DELETE to confirm</label>
            <input
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              placeholder="DELETE"
              className="mt-1 w-full px-3 py-2 text-sm rounded border"
              style={{ background: surface2, borderColor: border, color: c.text }}
              data-testid="clear-confirm-input"
            />
          </div>
        </div>

        <div className="flex items-center justify-between px-5 py-3 border-t" style={{ borderColor: border }}>
          <button type="button" onClick={onClose} className="text-xs font-semibold px-3 py-1.5 rounded-md border" style={{ borderColor: border, color: c.textMuted }} data-testid="clear-cancel">Cancel</button>
          <button
            type="button"
            onClick={runDelete}
            disabled={!canDelete}
            className="inline-flex items-center gap-1.5 text-xs font-semibold px-4 py-1.5 rounded-md text-white disabled:opacity-40"
            style={{ background: 'var(--color-danger-alt)' }}
            data-testid="clear-confirm-delete"
          >
            {busy ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
            Permanently delete {targetCount > 0 ? targetCount : ''}
          </button>
        </div>
      </div>
    </div>
  );
}
