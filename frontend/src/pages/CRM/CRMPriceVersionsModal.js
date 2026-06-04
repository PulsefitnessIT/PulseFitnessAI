/**
 * CRM · Master Price List — versions: compare, rollback, publish, snapshot.
 * (Iter 220 P1)
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { X, Loader2, GitCompare, RotateCcw, Camera, CheckCircle2, Plus, Minus, ArrowRight } from 'lucide-react';

const BADGE = {
  live: 'var(--color-success-alt)', draft: 'var(--color-accent-amber)',
  archived: 'var(--color-text-dim)', snapshot: 'var(--color-info-ios)',
};

export default function CRMPriceVersionsModal({ API, headers, c, isDark, isApprover, onClose, onChanged }) {
  const [versions, setVersions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [base, setBase] = useState('');
  const [target, setTarget] = useState('');
  const [diff, setDiff] = useState(null);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');

  const surface = isDark ? 'var(--color-surface-dark-1)' : '#fff';
  const surface2 = isDark ? 'var(--color-surface-dark-2)' : '#fff';
  const border = isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)';

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/crm/price-list/versions`, { headers: headers() });
      setVersions(r.data.versions || []);
      if ((r.data.versions || []).length && !base) setBase(r.data.versions[r.data.versions.length - 1].id);
    } catch (e) { /* silent */ }
    setLoading(false);
  }, [API, headers, base]);

  useEffect(() => { load(); }, [load]);

  const compare = async () => {
    if (!base) return;
    setBusy('compare'); setError(''); setDiff(null);
    try {
      const r = await axios.get(`${API}/crm/price-list/versions/${base}/compare`, { headers: headers(), params: target ? { to: target } : {} });
      setDiff(r.data);
    } catch (e) { setError(e?.response?.data?.detail || 'Compare failed'); }
    setBusy('');
  };

  const snapshot = async () => {
    setBusy('snap'); setError('');
    try { await axios.post(`${API}/crm/price-list/versions/snapshot-current`, {}, { headers: headers() }); await load(); onChanged?.(); }
    catch (e) { setError(e?.response?.data?.detail || 'Snapshot failed'); }
    setBusy('');
  };

  const rollback = async (id) => {
    if (!window.confirm('Roll back the live catalogue to this version? A new live version will be created. Existing quotes keep their prices.')) return;
    setBusy(`rb-${id}`); setError('');
    try { await axios.post(`${API}/crm/price-list/versions/${id}/rollback`, {}, { headers: headers() }); await load(); onChanged?.(); }
    catch (e) { setError(e?.response?.data?.detail || 'Rollback failed'); }
    setBusy('');
  };

  const publish = async (id) => {
    setBusy(`pub-${id}`); setError('');
    try { await axios.post(`${API}/crm/price-list/versions/${id}/publish`, {}, { headers: headers() }); await load(); onChanged?.(); }
    catch (e) { setError(e?.response?.data?.detail || 'Publish failed'); }
    setBusy('');
  };

  return (
    <div className="fixed inset-0 z-[260] flex items-center justify-center bg-black/50 backdrop-blur-sm p-3" data-testid="price-versions-modal">
      <div className="w-full max-w-3xl max-h-[92vh] flex flex-col rounded-2xl shadow-2xl border" style={{ background: surface, borderColor: border }}>
        <div className="flex items-center justify-between px-5 py-3 border-b" style={{ borderColor: border }}>
          <h3 className="text-sm font-semibold flex items-center gap-2" style={{ color: c.text }}><GitCompare size={15} /> Price list versions</h3>
          <div className="flex items-center gap-2">
            {isApprover && <button type="button" onClick={snapshot} disabled={busy === 'snap'} className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-1 rounded border disabled:opacity-50" style={{ borderColor: border, color: 'var(--color-info-ios)' }} data-testid="versions-snapshot-btn">{busy === 'snap' ? <Loader2 size={11} className="animate-spin" /> : <Camera size={11} />} Snapshot current</button>}
            <button type="button" onClick={onClose} className="opacity-60 hover:opacity-100" data-testid="versions-close"><X size={16} /></button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          {error && <div className="text-xs px-3 py-1.5 rounded-md" style={{ background: 'rgba(239,68,68,0.08)', color: 'var(--color-danger-alt)' }}>{error}</div>}

          {/* Compare bar */}
          <div className="flex flex-wrap items-end gap-2 rounded-lg border p-3" style={{ borderColor: border }}>
            <div>
              <label className="text-[10px] uppercase" style={{ color: c.textDim }}>Base (older)</label>
              <select value={base} onChange={e => setBase(e.target.value)} className="block mt-1 px-2 py-1 text-xs rounded border" style={{ background: surface2, borderColor: border, color: c.text }} data-testid="versions-compare-base">
                {versions.map(v => <option key={v.id} value={v.id}>{v.label}</option>)}
              </select>
            </div>
            <ArrowRight size={14} className="mb-2 opacity-50" />
            <div>
              <label className="text-[10px] uppercase" style={{ color: c.textDim }}>Target</label>
              <select value={target} onChange={e => setTarget(e.target.value)} className="block mt-1 px-2 py-1 text-xs rounded border" style={{ background: surface2, borderColor: border, color: c.text }} data-testid="versions-compare-target">
                <option value="">Current live catalogue</option>
                {versions.map(v => <option key={v.id} value={v.id}>{v.label}</option>)}
              </select>
            </div>
            <button type="button" onClick={compare} disabled={busy === 'compare' || !base} className="text-xs font-semibold px-3 py-1.5 rounded-md text-white disabled:opacity-50" style={{ background: 'var(--color-info-ios)' }} data-testid="versions-compare-btn">{busy === 'compare' ? <Loader2 size={13} className="animate-spin" /> : 'Compare'}</button>
          </div>

          {/* Diff result */}
          {diff && (
            <div className="rounded-lg border" style={{ borderColor: border }} data-testid="versions-diff">
              <div className="flex items-center gap-4 px-3 py-2 border-b text-xs" style={{ borderColor: border }}>
                <span className="inline-flex items-center gap-1" style={{ color: 'var(--color-success-alt)' }}><Plus size={12} />{diff.counts.added} added</span>
                <span className="inline-flex items-center gap-1" style={{ color: 'var(--color-danger-alt)' }}><Minus size={12} />{diff.counts.removed} removed</span>
                <span className="inline-flex items-center gap-1" style={{ color: 'var(--color-accent-amber)' }}><GitCompare size={12} />{diff.counts.changed} changed</span>
              </div>
              <div className="max-h-56 overflow-y-auto text-xs">
                {diff.changed.map((ch, i) => (
                  <div key={i} className="px-3 py-1.5 border-t flex items-center justify-between gap-2" style={{ borderColor: border }}>
                    <span style={{ color: c.text }}><span className="font-mono opacity-70">{ch.sku}</span> {ch.name?.slice(0, 40)}</span>
                    <span className="flex gap-2">
                      {Object.entries(ch.changes).map(([f, v]) => (
                        <span key={f} style={{ color: c.textMuted }}>{f.replace('_', ' ')}: <s style={{ color: c.textDim }}>{v.old}</s> → <strong style={{ color: 'var(--color-success-alt)' }}>{v.new}</strong></span>
                      ))}
                    </span>
                  </div>
                ))}
                {diff.counts.changed === 0 && diff.counts.added === 0 && diff.counts.removed === 0 && <div className="px-3 py-3 text-center" style={{ color: c.textDim }}>No differences.</div>}
              </div>
            </div>
          )}

          {/* Versions list */}
          {loading ? <div className="py-6 text-center"><Loader2 size={18} className="animate-spin mx-auto" /></div> : (
            <table className="w-full text-xs" data-testid="versions-table">
              <thead style={{ color: c.textDim }}><tr><th className="text-left px-2 py-1">Version</th><th className="text-left px-2 py-1">Status</th><th className="text-right px-2 py-1">Products</th><th className="text-left px-2 py-1">Created</th><th className="px-2 py-1"></th></tr></thead>
              <tbody>
                {versions.map(v => (
                  <tr key={v.id} className="border-t" style={{ borderColor: border }}>
                    <td className="px-2 py-1.5" style={{ color: c.text }}>{v.label}</td>
                    <td className="px-2 py-1.5"><span className="px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase" style={{ background: `${BADGE[v.status] || c.textDim}22`, color: BADGE[v.status] || c.textDim }}>{v.status}</span></td>
                    <td className="px-2 py-1.5 text-right" style={{ color: c.textMuted }}>{v.product_count}</td>
                    <td className="px-2 py-1.5" style={{ color: c.textDim }}>{v.created_at ? new Date(v.created_at).toLocaleDateString() : '—'}</td>
                    <td className="px-2 py-1.5 text-right whitespace-nowrap">
                      {isApprover && v.status !== 'live' && <button type="button" onClick={() => publish(v.id)} disabled={!!busy} className="text-[11px] mr-2 inline-flex items-center gap-1" style={{ color: 'var(--color-success-alt)' }} data-testid={`version-publish-${v.id}`}>{busy === `pub-${v.id}` ? <Loader2 size={10} className="animate-spin" /> : <CheckCircle2 size={11} />}Publish</button>}
                      {isApprover && <button type="button" onClick={() => rollback(v.id)} disabled={!!busy} className="text-[11px] inline-flex items-center gap-1" style={{ color: 'var(--color-info-ios)' }} data-testid={`version-rollback-${v.id}`}>{busy === `rb-${v.id}` ? <Loader2 size={10} className="animate-spin" /> : <RotateCcw size={11} />}Rollback</button>}
                    </td>
                  </tr>
                ))}
                {versions.length === 0 && <tr><td colSpan={5} className="px-2 py-4 text-center" style={{ color: c.textDim }}>No versions yet. Import a spreadsheet or snapshot the current catalogue.</td></tr>}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
