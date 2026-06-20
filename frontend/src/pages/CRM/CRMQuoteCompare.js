import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { useCRM } from './CRMApp';
import { GitCompareArrows, TrendingUp, TrendingDown, Minus, ArrowLeft } from 'lucide-react';

/**
 * CRMQuoteCompare — standalone "Compare Quotes" view.
 *
 * Pick a customer (company) and see a like-for-like comparison of every
 * item they have been quoted, matched on manufacturer + model, with the
 * net unit price in each quote plus latest-vs-previous price movement.
 * Backed by GET /crm/v2/quotes/compare?company_id=...
 */
const fmt = (n, cur = 'GBP') => {
  if (n === null || n === undefined) return '\u2014';
  const sym = cur === 'USD' ? '$' : cur === 'EUR' ? '\u20AC' : '\u00A3';
  return `${sym}${Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
};

function DeltaBadge({ delta, pct, cur, c }) {
  if (delta === null || delta === undefined) return <span style={{ color: c.textDim }}>{'\u2014'}</span>;
  const up = delta > 0;
  const flat = delta === 0;
  const col = flat ? c.textMuted : up ? 'var(--color-danger, #dc2626)' : 'var(--color-success, #16a34a)';
  const Icon = flat ? Minus : up ? TrendingUp : TrendingDown;
  return (
    <span className="inline-flex items-center gap-1 font-semibold text-sm" style={{ color: col }}>
      <Icon size={13} /> {up ? '+' : ''}{fmt(delta, cur)}{pct !== null && pct !== undefined ? ` (${up ? '+' : ''}${pct}%)` : ''}
    </span>
  );
}

export default function CRMQuoteCompare() {
  const { API, headers, c, isDark, setActiveTab } = useCRM();
  const [companies, setCompanies] = useState([]);
  const [companyId, setCompanyId] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/crm/v2/companies?limit=300`, { headers: headers() });
        setCompanies(r.data?.companies || r.data || []);
      } catch { /* ignore */ }
    })();
  }, [API, headers]);

  const load = useCallback(async (cid) => {
    if (!cid) { setData(null); return; }
    setLoading(true);
    try {
      const r = await axios.get(`${API}/crm/v2/quotes/compare?company_id=${cid}`, { headers: headers() });
      setData(r.data);
    } catch {
      setData(null);
    }
    setLoading(false);
  }, [API, headers]);

  useEffect(() => { load(companyId); }, [companyId, load]);

  const card = { background: c.surface, border: `1px solid ${c.border}`, color: c.text };
  const cur = data?.quotes?.[0]?.currency || 'GBP';

  return (
    <div className="p-4 sm:p-6 max-w-[1400px] mx-auto" data-testid="crm-quote-compare">
      <div className="flex items-center gap-3 mb-5">
        <button onClick={() => setActiveTab && setActiveTab('quotes')} className="p-2 rounded-lg" style={{ border: `1px solid ${c.border}`, color: c.textMuted }} data-testid="qc-back" title="Back to Quotes">
          <ArrowLeft size={16} />
        </button>
        <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ background: 'var(--color-brand-cyan, #19CDFF)', color: '#0A0C10' }}>
          <GitCompareArrows size={18} />
        </div>
        <div>
          <h1 className="text-xl font-bold" style={{ color: c.text }}>Compare Quotes</h1>
          <p className="text-sm" style={{ color: c.textMuted }}>Like-for-like pricing across a customer&apos;s quotes &mdash; matched on manufacturer + model.</p>
        </div>
      </div>

      <div className="rounded-xl p-4 mb-5" style={card}>
        <label className="text-xs font-semibold uppercase tracking-wide" style={{ color: c.textMuted }}>Customer</label>
        <select
          value={companyId}
          onChange={(e) => setCompanyId(e.target.value)}
          className="mt-2 w-full sm:w-96 px-3 py-2 rounded-lg text-sm"
          style={{ background: c.inputBg, border: `1px solid ${c.border}`, color: c.text }}
          data-testid="qc-company-select"
        >
          <option value="">Select a customer&hellip;</option>
          {companies.map((co) => <option key={co.id} value={co.id}>{co.name}</option>)}
        </select>
      </div>

      {loading && <p className="text-sm" style={{ color: c.textMuted }}>Loading comparison&hellip;</p>}

      {!loading && data && data.quotes?.length === 0 && (
        <div className="rounded-xl p-8 text-center" style={card}>
          <p style={{ color: c.textMuted }}>No quotes found for this customer yet.</p>
        </div>
      )}

      {!loading && data && data.quotes?.length > 0 && (
        <>
          <div className="flex flex-wrap gap-4 mb-4 text-sm">
            <span style={{ color: c.textMuted }}><strong style={{ color: c.text }}>{data.quotes.length}</strong> quotes</span>
            <span style={{ color: c.textMuted }}><strong style={{ color: c.text }}>{data.items.length}</strong> distinct items</span>
            <span style={{ color: c.textMuted }}><strong style={{ color: c.text }}>{data.compared_count}</strong> appear in 2+ quotes (comparable)</span>
          </div>

          <div className="rounded-xl overflow-x-auto" style={card}>
            <table className="w-full text-sm" data-testid="qc-table">
              <thead>
                <tr style={{ borderBottom: `1px solid ${c.border}` }}>
                  <th className="text-left p-3 font-semibold sticky left-0 z-10" style={{ color: c.textMuted, background: c.surface, minWidth: 220 }}>Item (Manufacturer &middot; Model)</th>
                  {data.quotes.map((q) => (
                    <th key={q.quote_id} className="text-right p-3 font-semibold whitespace-nowrap" style={{ color: c.textMuted }}>
                      <div style={{ color: c.text }}>{q.quote_number}</div>
                      <div className="text-[11px] font-normal">{q.created_at ? new Date(q.created_at).toLocaleDateString('en-GB') : ''}</div>
                    </th>
                  ))}
                  <th className="text-right p-3 font-semibold whitespace-nowrap" style={{ color: c.textMuted }}>{'\u0394'} latest vs prev</th>
                  <th className="text-right p-3 font-semibold whitespace-nowrap" style={{ color: c.textMuted }}>Min</th>
                  <th className="text-right p-3 font-semibold whitespace-nowrap" style={{ color: c.textMuted }}>Max</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((it) => {
                  const comparable = it.appears_in > 1;
                  return (
                    <tr key={it.key} style={{ borderBottom: `1px solid ${c.border}`, background: comparable ? (isDark ? 'rgba(25,205,255,0.05)' : 'rgba(25,205,255,0.04)') : 'transparent' }} data-testid="qc-row">
                      <td className="p-3 sticky left-0 z-10" style={{ background: comparable ? (isDark ? 'var(--color-neutral-900)' : 'var(--theme-surface)') : c.surface }}>
                        <div className="font-semibold" style={{ color: c.text }}>{it.label}</div>
                        {it.sku && <div className="text-[11px]" style={{ color: c.textDim }}>SKU {it.sku}</div>}
                      </td>
                      {data.quotes.map((q) => {
                        const p = it.prices[q.quote_id];
                        return (
                          <td key={q.quote_id} className="text-right p-3 whitespace-nowrap" style={{ color: p ? c.text : c.textDim }}>
                            {p ? fmt(p.net_price, cur) : '\u2014'}
                          </td>
                        );
                      })}
                      <td className="text-right p-3 whitespace-nowrap"><DeltaBadge delta={it.delta} pct={it.delta_pct} cur={cur} c={c} /></td>
                      <td className="text-right p-3 whitespace-nowrap" style={{ color: c.textMuted }}>{fmt(it.min, cur)}</td>
                      <td className="text-right p-3 whitespace-nowrap" style={{ color: c.textMuted }}>{fmt(it.max, cur)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
