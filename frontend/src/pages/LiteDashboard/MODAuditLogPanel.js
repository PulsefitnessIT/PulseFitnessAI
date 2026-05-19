/**
 * MOD Audit Log viewer (HQ only).
 *
 * Iter 216h115 — drawer-style panel that lists the most recent audit
 * rows for a single MOD site. Includes a CSV export button that pulls
 * the full chain and appends a tamper-evident integrity verdict
 * footer line. Used by HQ owners/managers preparing DIO / ISO 27001
 * inspection packs.
 */
import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { X, ShieldCheck, ShieldAlert, Loader2, Download, Clock } from 'lucide-react';

const ACTION_LABELS = {
  'fault.create': 'Fault raised',
  'fault.update': 'Fault updated',
  'fault.resolve': 'Fault resolved',
  'fault.reopen': 'Fault reopened',
  'fault.confirm_fix': 'Reporter confirmed fix',
  'fault.classification_flag': 'Classification flag',
  'equipment.create': 'Equipment added',
  'equipment.update': 'Equipment updated',
  'equipment.supplier_change': 'Supplier changed',
  'staff.create': 'Staff added',
  'staff.update': 'Staff updated',
  'staff.delete': 'Staff removed',
  'staff.transfer': 'Staff transferred',
  'staff.posting_out': 'Posting out',
  'site_login.provision': 'Site login provisioned',
  'site_login.rotate': 'Site login rotated',
  'supplier.create': 'Supplier added',
  'supplier.update': 'Supplier updated',
  'drill.start': 'Drill started',
  'drill.complete': 'Drill completed',
};

const ACTION_TONES = {
  'fault.classification_flag': 'amber',
  'fault.reopen': 'amber',
  'staff.delete': 'rose',
  'site_login.rotate': 'cyan',
  'site_login.provision': 'cyan',
  'drill.start': 'violet',
  'drill.complete': 'violet',
};

export default function MODAuditLogPanel({ site, API, onClose }) {
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : '';
  const headers = { Authorization: `Bearer ${token}` };
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    axios
      .get(`${API}/mod/pro/audit-log/${site.id}?limit=500`, { headers })
      .then((r) => setData(r.data))
      .catch((e) => setError(e?.response?.data?.detail || 'Could not load audit log'))
      .finally(() => setLoading(false));
  }, [API, site.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { load(); }, [load]);

  const downloadCsv = async () => {
    try {
      const r = await axios.get(`${API}/mod/pro/audit-log/${site.id}/export.csv`, {
        headers, responseType: 'blob',
      });
      const url = window.URL.createObjectURL(r.data);
      const a = document.createElement('a');
      a.href = url;
      const today = new Date().toISOString().slice(0, 10);
      a.download = `mod-audit-${site.id}-${today}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Could not export CSV');
    }
  };

  const integrity = data?.integrity;
  return (
    <div className="fixed inset-0 z-50 grid place-items-end sm:place-items-center bg-black/70 p-0 sm:p-4" data-testid="mod-audit-panel">
      <div className="w-full max-w-3xl h-full sm:h-auto sm:max-h-[88vh] rounded-none sm:rounded-2xl overflow-hidden flex flex-col" style={{ background: 'var(--theme-surface)', border: '1px solid var(--theme-border)' }}>
        <header className="px-5 py-4 border-b flex items-start justify-between gap-3" style={{ borderColor: 'var(--theme-border-soft)' }}>
          <div className="flex-1 min-w-0">
            <div className="text-[10px] font-extrabold uppercase tracking-[0.3em]" style={{ color: 'var(--color-brand-cyan-hover)' }}>
              Pulse Fitness · MOD Service · Audit log
            </div>
            <h3 className="text-base font-extrabold tracking-tight mt-1 truncate" style={{ color: 'var(--theme-text)' }} data-testid="mod-audit-panel-title">
              {site.name}
            </h3>
            {integrity && (
              <div className="flex items-center gap-1.5 mt-1.5 text-[11px] font-semibold" data-testid="mod-audit-integrity">
                {integrity.valid ? (
                  <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
                    <ShieldCheck size={13} /> Chain valid · {integrity.rows} rows
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-rose-600 dark:text-rose-400">
                    <ShieldAlert size={13} /> Chain BROKEN at {integrity.first_break_at}
                  </span>
                )}
              </div>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={downloadCsv}
              disabled={!data || loading}
              className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-bold border hover:bg-[var(--theme-hover-bg)] disabled:opacity-50"
              style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
              data-testid="mod-audit-export-csv"
            >
              <Download size={12} /> CSV
            </button>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="p-1.5 rounded-full hover:bg-[var(--theme-hover-bg)]"
              data-testid="mod-audit-panel-close"
            >
              <X size={16} style={{ color: 'var(--theme-text-muted)' }} />
            </button>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto p-4" data-testid="mod-audit-rows">
          {loading && (
            <div className="flex items-center gap-2 text-sm py-10 justify-center" style={{ color: 'var(--theme-text-muted)' }}>
              <Loader2 size={14} className="animate-spin" /> Loading…
            </div>
          )}
          {error && (
            <div className="text-sm text-rose-500 py-4" data-testid="mod-audit-error">{error}</div>
          )}
          {!loading && !error && data && data.rows.length === 0 && (
            <p className="text-sm py-10 text-center" style={{ color: 'var(--theme-text-muted)' }} data-testid="mod-audit-empty">
              No audit events yet for this site.
            </p>
          )}
          {!loading && !error && data && data.rows.length > 0 && (
            <ul className="space-y-2">
              {data.rows.map((row) => (
                <li
                  key={row.id}
                  className="rounded-lg border px-3 py-2.5 text-xs"
                  style={{
                    background: 'var(--theme-surface-2)',
                    borderColor: 'var(--theme-border)',
                  }}
                  data-testid={`mod-audit-row-${row.id}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-1.5 font-bold">
                      <span
                        className="inline-block w-1.5 h-1.5 rounded-full"
                        style={{ background: toneColor(ACTION_TONES[row.action] || 'cyan') }}
                      />
                      <span style={{ color: 'var(--theme-text)' }}>
                        {ACTION_LABELS[row.action] || row.action}
                      </span>
                    </div>
                    <span className="inline-flex items-center gap-1 text-[10px] font-mono" style={{ color: 'var(--theme-text-muted)' }}>
                      <Clock size={11} /> {fmtDate(row.created_at)}
                    </span>
                  </div>
                  <div className="text-[11px] mt-1 truncate" style={{ color: 'var(--theme-text-muted)' }}>
                    {row.actor_email || 'System'} · {row.target_type || '—'}{row.target_id ? ` · ${row.target_id.slice(0, 8)}…` : ''}
                  </div>
                  {row.payload && Object.keys(row.payload).length > 0 && (
                    <details className="mt-1">
                      <summary className="cursor-pointer text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>
                        Payload
                      </summary>
                      <pre className="text-[10px] mt-1 whitespace-pre-wrap break-words" style={{ color: 'var(--theme-text)' }}>
                        {JSON.stringify(row.payload, null, 2)}
                      </pre>
                    </details>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

function toneColor(tone) {
  switch (tone) {
    case 'amber': return '#f59e0b';
    case 'rose': return '#f43f5e';
    case 'violet': return '#a78bfa';
    case 'cyan':
    default: return '#19CDFF';
  }
}

function fmtDate(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleString('en-GB', {
      day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
    });
  } catch { return iso || ''; }
}
