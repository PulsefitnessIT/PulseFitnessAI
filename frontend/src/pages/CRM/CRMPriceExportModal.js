/**
 * CRM · Master Price List — exports & weekly backups (Iter 220 P1).
 * Manual export (scope/format, cost/margin gated) with secure download
 * links + weekly backup config/run + export history.
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { X, Loader2, Download, CalendarClock, ShieldCheck, Play, Save, FileDown } from 'lucide-react';

const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

export default function CRMPriceExportModal({ API, headers, c, isDark, categories = [], onClose }) {
  const [scope, setScope] = useState('live');
  const [category, setCategory] = useState('');
  const [format, setFormat] = useState('xlsx');
  const [includeCost, setIncludeCost] = useState(false);
  const [includeMargin, setIncludeMargin] = useState(false);
  const [cfg, setCfg] = useState(null);
  const [isApprover, setIsApprover] = useState(false);
  const [exports, setExports] = useState([]);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [lastLink, setLastLink] = useState(null);

  const border = isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)';
  const surface2 = isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-50)';
  const inp = { background: surface2, borderColor: border, color: c.text };

  const load = useCallback(async () => {
    try {
      const [cf, ex] = await Promise.all([
        axios.get(`${API}/crm/price-list/backup/config`, { headers: headers() }),
        axios.get(`${API}/crm/price-list/exports`, { headers: headers() }),
      ]);
      setCfg(cf.data.config); setIsApprover(cf.data.is_approver);
      setExports(ex.data.exports || []);
    } catch (e) { /* silent */ }
  }, [API, headers]);

  useEffect(() => { load(); }, [load]);

  const openLink = async (id) => {
    try {
      const r = await axios.get(`${API}/crm/price-list/export/${id}/link`, { headers: headers() });
      window.open(r.data.download_url, '_blank');
    } catch (e) { setError('Link expired or unavailable'); }
  };

  const runManual = async () => {
    setBusy('manual'); setError(''); setLastLink(null);
    try {
      const r = await axios.post(`${API}/crm/price-list/export`, { scope, category, format, include_cost: includeCost, include_margin: includeMargin }, { headers: headers() });
      setLastLink(r.data.export);
      await load();
    } catch (e) { setError(e?.response?.data?.detail || 'Export failed'); }
    setBusy('');
  };

  const saveCfg = async () => {
    setBusy('cfg'); setError('');
    try {
      const r = await axios.put(`${API}/crm/price-list/backup/config`, cfg, { headers: headers() });
      setCfg(r.data.config);
    } catch (e) { setError(e?.response?.data?.detail || 'Save failed'); }
    setBusy('');
  };

  const runBackup = async () => {
    setBusy('backup'); setError('');
    try { await axios.post(`${API}/crm/price-list/backup/run`, {}, { headers: headers() }); await load(); }
    catch (e) { setError(e?.response?.data?.detail || 'Backup failed'); }
    setBusy('');
  };

  const setC = (k, v) => setCfg(p => ({ ...p, [k]: v }));

  return (
    <div className="fixed inset-0 z-[260] flex items-center justify-center bg-black/50 backdrop-blur-sm p-3" data-testid="price-export-modal">
      <div className="w-full max-w-3xl max-h-[92vh] flex flex-col rounded-2xl shadow-2xl border" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: border }}>
        <div className="flex items-center justify-between px-5 py-3 border-b" style={{ borderColor: border }}>
          <h3 className="text-sm font-semibold flex items-center gap-2" style={{ color: c.text }}><FileDown size={15} /> Exports & backups</h3>
          <button type="button" onClick={onClose} className="opacity-60 hover:opacity-100" data-testid="export-close"><X size={16} /></button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
          {error && <div className="text-xs px-3 py-1.5 rounded-md" style={{ background: 'rgba(239,68,68,0.08)', color: 'var(--color-danger-alt)' }} data-testid="export-error">{error}</div>}

          {/* Manual export */}
          <section data-testid="manual-export-section">
            <h4 className="text-xs font-semibold mb-2 flex items-center gap-1.5" style={{ color: c.text }}><Download size={13} /> Manual export</h4>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <select value={scope} onChange={e => setScope(e.target.value)} className="px-2 py-1.5 text-xs rounded border" style={inp} data-testid="export-scope">
                <option value="live">Live products</option>
                <option value="archived">Archived</option>
                <option value="all">All</option>
                <option value="category">By category</option>
              </select>
              {scope === 'category' && (
                <select value={category} onChange={e => setCategory(e.target.value)} className="px-2 py-1.5 text-xs rounded border" style={inp} data-testid="export-category">
                  <option value="">Select…</option>
                  {categories.map(x => <option key={x} value={x}>{x}</option>)}
                </select>
              )}
              <select value={format} onChange={e => setFormat(e.target.value)} className="px-2 py-1.5 text-xs rounded border" style={inp} data-testid="export-format">
                <option value="xlsx">Excel (.xlsx)</option>
                <option value="csv">CSV</option>
              </select>
              <button type="button" onClick={runManual} disabled={!!busy} className="inline-flex items-center justify-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-md text-white" style={{ background: 'var(--color-info-ios)' }} data-testid="export-generate">{busy === 'manual' ? <Loader2 size={13} className="animate-spin" /> : 'Generate'}</button>
            </div>
            {isApprover && (
              <div className="flex items-center gap-4 mt-2 text-[11px]" style={{ color: c.textMuted }}>
                <label className="flex items-center gap-1.5"><input type="checkbox" checked={includeCost} onChange={e => setIncludeCost(e.target.checked)} data-testid="export-include-cost" /> Include cost</label>
                <label className="flex items-center gap-1.5"><input type="checkbox" checked={includeMargin} onChange={e => setIncludeMargin(e.target.checked)} data-testid="export-include-margin" /> Include margin</label>
                <span style={{ color: c.textDim }}>Cost/margin only available to owners & admins.</span>
              </div>
            )}
            {lastLink && (
              <a href={lastLink.download_url} target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center gap-1.5 text-xs font-semibold" style={{ color: 'var(--color-success-alt)' }} data-testid="export-download-link">
                <Download size={13} /> Download {lastLink.filename} ({lastLink.product_count} products) · link expires {lastLink.expires_at?.slice(0, 10)}
              </a>
            )}
          </section>

          {/* Weekly backup */}
          {cfg && (
            <section className="rounded-lg border p-3" style={{ borderColor: border }} data-testid="backup-config-section">
              <h4 className="text-xs font-semibold mb-2 flex items-center gap-1.5" style={{ color: c.text }}><CalendarClock size={13} /> Automatic weekly backup</h4>
              {!isApprover && <p className="text-[11px] mb-2" style={{ color: c.textDim }}><ShieldCheck size={11} className="inline mr-1" />Only owners/admins can configure backups.</p>}
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs" style={{ color: c.textMuted }}>
                <label className="flex items-center gap-1.5"><input type="checkbox" disabled={!isApprover} checked={!!cfg.enabled} onChange={e => setC('enabled', e.target.checked)} data-testid="backup-enabled" /> Enabled</label>
                <select disabled={!isApprover} value={cfg.day_of_week} onChange={e => setC('day_of_week', Number(e.target.value))} className="px-2 py-1.5 rounded border" style={inp} data-testid="backup-day">
                  {DAYS.map((d, i) => <option key={i} value={i}>{d}</option>)}
                </select>
                <input disabled={!isApprover} type="time" value={cfg.time} onChange={e => setC('time', e.target.value)} className="px-2 py-1.5 rounded border" style={inp} data-testid="backup-time" />
                <select disabled={!isApprover} value={cfg.file_format} onChange={e => setC('file_format', e.target.value)} className="px-2 py-1.5 rounded border" style={inp} data-testid="backup-format">
                  <option value="xlsx">Excel (.xlsx)</option>
                  <option value="csv">CSV</option>
                </select>
                <input disabled={!isApprover} type="number" value={cfg.retention_days} onChange={e => setC('retention_days', Number(e.target.value))} placeholder="Retention days" className="px-2 py-1.5 rounded border" style={inp} data-testid="backup-retention" />
              </div>
              <input disabled={!isApprover} value={(cfg.recipients || []).join(', ')} onChange={e => setC('recipients', e.target.value.split(',').map(s => s.trim()).filter(Boolean))} placeholder="Recipient emails, comma-separated" className="w-full mt-2 px-2 py-1.5 text-xs rounded border" style={inp} data-testid="backup-recipients" />
              <div className="flex items-center gap-4 mt-2 text-[11px]" style={{ color: c.textMuted }}>
                <label className="flex items-center gap-1.5"><input type="checkbox" disabled={!isApprover} checked={!!cfg.include_cost} onChange={e => setC('include_cost', e.target.checked)} data-testid="backup-include-cost" /> Include cost</label>
                <label className="flex items-center gap-1.5"><input type="checkbox" disabled={!isApprover} checked={!!cfg.include_margin} onChange={e => setC('include_margin', e.target.checked)} data-testid="backup-include-margin" /> Include margin</label>
                {cfg.next_run_at && <span style={{ color: c.textDim }}>Next run {new Date(cfg.next_run_at).toLocaleString()}</span>}
              </div>
              {isApprover && (
                <div className="flex items-center gap-2 mt-3">
                  <button type="button" onClick={saveCfg} disabled={!!busy} className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-md border" style={{ borderColor: border, color: c.text }} data-testid="backup-save">{busy === 'cfg' ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />} Save schedule</button>
                  <button type="button" onClick={runBackup} disabled={!!busy} className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-md text-white" style={{ background: 'var(--color-success-alt)' }} data-testid="backup-run-now">{busy === 'backup' ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />} Run backup now</button>
                </div>
              )}
            </section>
          )}

          {/* History */}
          <section data-testid="export-history-section">
            <h4 className="text-xs font-semibold mb-2" style={{ color: c.text }}>Export history</h4>
            <table className="w-full text-xs" data-testid="export-history-table">
              <thead style={{ color: c.textDim }}><tr><th className="text-left px-2 py-1">When</th><th className="text-left px-2 py-1">Type</th><th className="text-left px-2 py-1">Scope</th><th className="text-right px-2 py-1">Products</th><th className="px-2 py-1"></th></tr></thead>
              <tbody>
                {exports.map(e => (
                  <tr key={e.id} className="border-t" style={{ borderColor: border }}>
                    <td className="px-2 py-1.5" style={{ color: c.textDim }}>{e.created_at ? new Date(e.created_at).toLocaleString() : '—'}</td>
                    <td className="px-2 py-1.5" style={{ color: c.text }}>{e.type}{e.sensitive ? ' 🔒' : ''} · {e.format}</td>
                    <td className="px-2 py-1.5" style={{ color: c.textMuted }}>{e.scope}</td>
                    <td className="px-2 py-1.5 text-right" style={{ color: c.textMuted }}>{e.product_count}</td>
                    <td className="px-2 py-1.5 text-right">
                      {e.expires_at && e.expires_at > new Date().toISOString()
                        ? <button type="button" onClick={() => openLink(e.id)} className="text-[11px] inline-flex items-center gap-1" style={{ color: 'var(--color-info-ios)' }} data-testid={`export-download-${e.id}`}><Download size={11} /> Download</button>
                        : <span className="text-[11px]" style={{ color: c.textDim }}>expired</span>}
                    </td>
                  </tr>
                ))}
                {exports.length === 0 && <tr><td colSpan={5} className="px-2 py-4 text-center" style={{ color: c.textDim }}>No exports yet.</td></tr>}
              </tbody>
            </table>
          </section>
        </div>
      </div>
    </div>
  );
}
