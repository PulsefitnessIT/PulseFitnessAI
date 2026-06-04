/**
 * CRM · Master Price List — data-quality dashboard + reporting (Iter 220 P1).
 * Health score, issue cards with drill-down lists, per-issue CSV reports
 * and a by-category margin breakdown.
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { X, Loader2, Activity, Download, ChevronRight } from 'lucide-react';

const SEVERITY = {
  missing_sage: 'var(--color-danger-alt)', missing_sell: 'var(--color-danger-alt)',
  cost_gt_sell: 'var(--color-danger-alt)', no_category: 'var(--color-accent-amber)',
  missing_cost: 'var(--color-accent-amber)', low_margin: 'var(--color-accent-amber)',
  duplicate_sku: 'var(--color-accent-amber)', obsolete: 'var(--color-accent-amber)',
  never_quoted: 'var(--color-info-ios)', with_unmapped: 'var(--color-info-ios)',
  recently_changed: 'var(--color-info-ios)',
};

export default function CRMDataQualityModal({ API, headers, c, isDark, onClose, onOpenProduct }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeIssue, setActiveIssue] = useState(null);
  const [drill, setDrill] = useState(null);
  const [drillBusy, setDrillBusy] = useState(false);

  const border = isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)';
  const surface2 = isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-50)';

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/crm/price-list/quality`, { headers: headers() });
      setData(r.data);
    } catch (e) { /* silent */ }
    setLoading(false);
  }, [API, headers]);

  useEffect(() => { load(); }, [load]);

  const openIssue = async (issue) => {
    setActiveIssue(issue); setDrillBusy(true); setDrill(null);
    try {
      const r = await axios.get(`${API}/crm/price-list/quality/list`, { headers: headers(), params: { issue, limit: 100 } });
      setDrill(r.data);
    } catch (e) { /* silent */ }
    setDrillBusy(false);
  };

  const downloadReport = async (issue) => {
    try {
      const r = await axios.get(`${API}/crm/price-list/quality/report.csv`, { headers: headers(), params: { issue }, responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([r.data], { type: 'text/csv' }));
      const a = document.createElement('a');
      a.href = url; a.download = `quality_${issue}.csv`; a.click();
      window.URL.revokeObjectURL(url);
    } catch (e) { /* silent */ }
  };

  const health = data?.health_score ?? 0;
  const healthColor = health >= 80 ? 'var(--color-success-alt)' : health >= 50 ? 'var(--color-accent-amber)' : 'var(--color-danger-alt)';

  return (
    <div className="fixed inset-0 z-[260] flex items-center justify-center bg-black/50 backdrop-blur-sm p-3" data-testid="data-quality-modal">
      <div className="w-full max-w-4xl max-h-[92vh] flex flex-col rounded-2xl shadow-2xl border" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: border }}>
        <div className="flex items-center justify-between px-5 py-3 border-b" style={{ borderColor: border }}>
          <h3 className="text-sm font-semibold flex items-center gap-2" style={{ color: c.text }}><Activity size={15} /> Data quality dashboard</h3>
          <button type="button" onClick={onClose} className="opacity-60 hover:opacity-100" data-testid="quality-close"><X size={16} /></button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          {loading || !data ? <div className="py-10 text-center"><Loader2 size={20} className="animate-spin mx-auto" /></div> : (
            <>
              {/* Health header */}
              <div className="flex items-center gap-4 rounded-xl border p-4" style={{ borderColor: border, background: surface2 }} data-testid="quality-health">
                <div className="text-center">
                  <div className="text-3xl font-bold" style={{ color: healthColor }} data-testid="quality-health-score">{health}%</div>
                  <div className="text-[10px] uppercase tracking-wide" style={{ color: c.textDim }}>Health</div>
                </div>
                <div className="text-xs" style={{ color: c.textMuted }}>
                  <div><strong style={{ color: c.text }}>{data.total}</strong> live products · {data.archived} archived</div>
                  <div>{data.blocked_count} need attention before quoting / Sage export · margin floor {data.margin_threshold}%</div>
                </div>
              </div>

              {/* Issue cards */}
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2" data-testid="quality-cards">
                {Object.entries(data.labels).map(([key, label]) => {
                  const count = data.counts[key] ?? 0;
                  const col = SEVERITY[key] || c.textDim;
                  return (
                    <button key={key} type="button" onClick={() => openIssue(key)} disabled={count === 0}
                      className="text-left rounded-lg border px-3 py-2 transition-colors disabled:opacity-50 hover:border-current"
                      style={{ borderColor: activeIssue === key ? col : border, color: c.text }}
                      data-testid={`quality-card-${key}`}>
                      <div className="text-xl font-bold" style={{ color: count > 0 ? col : c.textDim }}>{count}</div>
                      <div className="text-[10px] uppercase tracking-wide flex items-center justify-between gap-1" style={{ color: c.textDim }}>
                        {label}{count > 0 && <ChevronRight size={11} />}
                      </div>
                    </button>
                  );
                })}
              </div>

              {/* Drill-down */}
              {activeIssue && (
                <div className="rounded-lg border" style={{ borderColor: border }} data-testid="quality-drill">
                  <div className="flex items-center justify-between px-3 py-2 border-b" style={{ borderColor: border }}>
                    <span className="text-xs font-semibold" style={{ color: c.text }}>{drill?.label || data.labels[activeIssue]} · {drill?.total ?? 0}</span>
                    <button type="button" onClick={() => downloadReport(activeIssue)} className="inline-flex items-center gap-1 text-[11px] font-semibold" style={{ color: 'var(--color-info-ios)' }} data-testid="quality-download-report"><Download size={11} /> CSV report</button>
                  </div>
                  <div className="max-h-64 overflow-y-auto">
                    {drillBusy ? <div className="py-6 text-center"><Loader2 size={16} className="animate-spin mx-auto" /></div> : (
                      <table className="w-full text-xs">
                        <thead style={{ color: c.textDim, background: surface2 }}><tr><th className="text-left px-3 py-1">Code</th><th className="text-left px-3 py-1">Name</th><th className="text-left px-3 py-1">Category</th><th className="text-right px-3 py-1">Sell</th><th className="text-right px-3 py-1">Margin</th></tr></thead>
                        <tbody>
                          {(drill?.items || []).map(p => (
                            <tr key={p.id} className="border-t cursor-pointer hover:opacity-80" style={{ borderColor: border }} onClick={() => onOpenProduct?.(p)} data-testid={`quality-item-${p.id}`}>
                              <td className="px-3 py-1.5 font-mono" style={{ color: c.textDim }}>{p.sku || '—'}</td>
                              <td className="px-3 py-1.5 truncate" style={{ color: c.text, maxWidth: 220 }}>{p.name}</td>
                              <td className="px-3 py-1.5" style={{ color: c.textMuted }}>{p.category}</td>
                              <td className="px-3 py-1.5 text-right" style={{ color: c.textMuted }}>£{p.sell_price}</td>
                              <td className="px-3 py-1.5 text-right" style={{ color: c.textMuted }}>{p.margin_percent}%</td>
                            </tr>
                          ))}
                          {drill && drill.items.length === 0 && <tr><td colSpan={5} className="px-3 py-4 text-center" style={{ color: c.textDim }}>None 🎉</td></tr>}
                        </tbody>
                      </table>
                    )}
                  </div>
                </div>
              )}

              {/* By-category */}
              <div data-testid="quality-by-category">
                <h4 className="text-xs font-semibold mb-1" style={{ color: c.text }}>Margin by category</h4>
                <table className="w-full text-xs">
                  <thead style={{ color: c.textDim }}><tr><th className="text-left px-3 py-1">Category</th><th className="text-right px-3 py-1">Products</th><th className="text-right px-3 py-1">Avg margin</th><th className="text-right px-3 py-1">Total sell</th></tr></thead>
                  <tbody>
                    {data.by_category.map(cat => (
                      <tr key={cat.category} className="border-t" style={{ borderColor: border }}>
                        <td className="px-3 py-1.5" style={{ color: c.text }}>{cat.category}</td>
                        <td className="px-3 py-1.5 text-right" style={{ color: c.textMuted }}>{cat.count}</td>
                        <td className="px-3 py-1.5 text-right" style={{ color: cat.avg_margin != null && cat.avg_margin < data.margin_threshold ? 'var(--color-accent-amber)' : c.textMuted }}>{cat.avg_margin != null ? `${cat.avg_margin}%` : '—'}</td>
                        <td className="px-3 py-1.5 text-right" style={{ color: c.textMuted }}>£{cat.total_sell}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
