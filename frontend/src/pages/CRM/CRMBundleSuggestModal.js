/**
 * CRM · Master Price List — AI bundle suggestions (Iter 220 P1).
 * Proposes 3-5 sensible bundles from the catalogue. SUGGESTIONS ONLY —
 * the editor picks what (if anything) to create as a real bundle product.
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { X, Loader2, Sparkles, Package, Check } from 'lucide-react';

export default function CRMBundleSuggestModal({ API, headers, c, isDark, onClose, onCreated }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [suggestions, setSuggestions] = useState([]);
  const [creatingIdx, setCreatingIdx] = useState(null);
  const [createdIdx, setCreatedIdx] = useState({});
  const [rowError, setRowError] = useState({});

  const border = isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)';
  const surface2 = isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-50)';

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const r = await axios.get(`${API}/crm/price-list/ai-bundle-suggestions`, { headers: headers() });
      setSuggestions(r.data.suggestions || []);
    } catch (err) {
      setError(err?.response?.data?.detail || 'AI is unavailable — please try again.');
    }
    setLoading(false);
  }, [API, headers]);

  useEffect(() => { load(); }, [load]);

  const createBundle = async (s, idx) => {
    setCreatingIdx(idx);
    setRowError(m => ({ ...m, [idx]: '' }));
    try {
      const r = await axios.post(`${API}/crm/products`, {
        name: s.name,
        category: 'Other',
        is_bundle: true,
        sell_price: s.total_sell_price,
        description: s.rationale,
        bundle_items: s.components.map(comp => ({ product_id: comp.product_id, quantity: 1 })),
      }, { headers: headers() });
      if (r.data?.id) {
        setCreatedIdx(m => ({ ...m, [idx]: true }));
        onCreated?.();
      } else {
        setRowError(m => ({ ...m, [idx]: 'Unexpected response — bundle may not have been created.' }));
      }
    } catch (err) {
      setRowError(m => ({ ...m, [idx]: err?.response?.data?.detail || 'Could not create bundle.' }));
    }
    setCreatingIdx(null);
  };

  return (
    <div className="fixed inset-0 z-[260] flex items-center justify-center bg-black/50 backdrop-blur-sm p-3" data-testid="bundle-suggest-modal">
      <div className="w-full max-w-2xl max-h-[92vh] flex flex-col rounded-2xl shadow-2xl border" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: border }}>
        <div className="flex items-center justify-between px-5 py-3 border-b" style={{ borderColor: border }}>
          <h3 className="text-sm font-semibold flex items-center gap-2" style={{ color: c.text }}><Sparkles size={15} style={{ color: 'var(--color-info-ios)' }} /> AI bundle suggestions</h3>
          <button type="button" onClick={onClose} className="opacity-60 hover:opacity-100" data-testid="bundle-suggest-close"><X size={16} /></button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
          <p className="text-xs" style={{ color: c.textDim }}>These are suggestions only — your customer may want something completely different. Create the ones that make sense, then edit pricing as needed.</p>
          {loading ? (
            <div className="py-10 text-center"><Loader2 size={20} className="animate-spin mx-auto" /></div>
          ) : error ? (
            <div className="text-xs px-3 py-2 rounded-md" style={{ background: 'rgba(239,68,68,0.08)', color: 'var(--color-danger-alt)' }} data-testid="bundle-suggest-error">{error}</div>
          ) : suggestions.length === 0 ? (
            <div className="py-8 text-center text-xs" style={{ color: c.textDim }}>No bundle ideas right now.</div>
          ) : suggestions.map((s, idx) => (
            <div key={idx} className="rounded-lg border p-3" style={{ borderColor: border, background: surface2 }} data-testid={`bundle-suggestion-${idx}`}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold flex items-center gap-1.5" style={{ color: c.text }}><Package size={13} /> {s.name}</div>
                  <p className="text-[11px] mt-0.5" style={{ color: c.textDim }}>{s.rationale}</p>
                </div>
                {createdIdx[idx] ? (
                  <span className="inline-flex items-center gap-1 text-[11px] font-semibold" style={{ color: 'var(--color-success-alt)' }} data-testid={`bundle-created-${idx}`}><Check size={12} /> Created</span>
                ) : (
                  <button type="button" onClick={() => createBundle(s, idx)} disabled={creatingIdx === idx}
                    className="inline-flex items-center gap-1 text-[11px] font-semibold px-2.5 py-1 rounded-md text-white disabled:opacity-50 whitespace-nowrap"
                    style={{ background: 'var(--color-info-ios)' }} data-testid={`bundle-create-${idx}`}>
                    {creatingIdx === idx ? <Loader2 size={11} className="animate-spin" /> : <>Create bundle</>}
                  </button>
                )}
              </div>
              <div className="mt-2 border-t pt-2" style={{ borderColor: border }}>
                {s.components.map((comp, i) => (
                  <div key={i} className="flex items-center justify-between text-xs py-0.5">
                    <span style={{ color: c.text }}>{comp.name}{comp.sku ? <span style={{ color: c.textDim }}> · {comp.sku}</span> : null}</span>
                    <span style={{ color: c.textMuted }}>£{comp.sell_price}</span>
                  </div>
                ))}
                <div className="flex items-center justify-between text-xs pt-1 mt-1 border-t font-semibold" style={{ borderColor: border, color: c.text }}>
                  <span>Total</span><span>£{s.total_sell_price}</span>
                </div>
                {rowError[idx] && <div className="text-[11px] mt-1.5" style={{ color: 'var(--color-danger-alt)' }} data-testid={`bundle-error-${idx}`}>{rowError[idx]}</div>}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
