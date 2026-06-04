/**
 * CRM · Quote → Sage 200 export panel + quote intelligence (Iter 220 P1).
 * Shows catalogue-aware line flags + suggestions, lets staff set the Sage
 * account ref / nominal, validate, and generate a Sage-ready CSV.
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import {
  Loader2, ShieldCheck, AlertTriangle, Download, FileCheck2, Sparkles, Info, Receipt,
} from 'lucide-react';

const STATUS_COLOR = {
  ready_for_sage: 'var(--color-success-alt)', exported: 'var(--color-info-ios)',
  validation_failed: 'var(--color-danger-alt)',
};
const FLAG_COLOR = { error: 'var(--color-danger-alt)', warning: 'var(--color-accent-amber)', info: 'var(--color-info-ios)' };

export default function CRMQuoteSagePanel({ API, headers, c, isDark, quote, onChanged }) {
  const [intel, setIntel] = useState(null);
  const [report, setReport] = useState(null);
  const [exportRec, setExportRec] = useState(null);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [accountRef, setAccountRef] = useState(quote.sage_account_ref || '');
  const [nominal, setNominal] = useState(quote.sage_default_nominal || '');
  const [ackObsolete, setAckObsolete] = useState(!!quote.sage_ack_obsolete);

  const border = isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)';
  const surface2 = isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-50)';

  const loadIntel = useCallback(async () => {
    try {
      const r = await axios.post(`${API}/crm/v2/quotes/intelligence`, { lines: quote.lines || [] }, { headers: headers() });
      setIntel(r.data);
    } catch (e) { /* silent */ }
  }, [API, headers, quote.lines]);

  useEffect(() => { loadIntel(); }, [loadIntel]);

  const saveMeta = async () => {
    setBusy('meta'); setError('');
    try {
      await axios.put(`${API}/crm/v2/quotes/${quote.id}/sage/meta`, { sage_account_ref: accountRef, sage_default_nominal: nominal, sage_ack_obsolete: ackObsolete }, { headers: headers() });
      onChanged?.();
    } catch (e) { setError(e?.response?.data?.detail || 'Save failed'); }
    setBusy('');
  };

  const validate = async () => {
    setBusy('validate'); setError(''); setExportRec(null);
    try {
      const r = await axios.post(`${API}/crm/v2/quotes/${quote.id}/sage/validate`, {}, { headers: headers() });
      setReport(r.data.report);
      onChanged?.();
    } catch (e) { setError(e?.response?.data?.detail || 'Validation failed'); }
    setBusy('');
  };

  const runExport = async () => {
    setBusy('export'); setError('');
    try {
      const r = await axios.post(`${API}/crm/v2/quotes/${quote.id}/sage/export`, {}, { headers: headers() });
      setExportRec(r.data.export);
      onChanged?.();
    } catch (e) {
      const d = e?.response?.data?.detail;
      setError(typeof d === 'object' ? (d.message || 'Export blocked') + (d.errors ? `: ${d.errors.join('; ')}` : '') : (d || 'Export failed'));
    }
    setBusy('');
  };

  const downloadCsv = async () => {
    setBusy('csv'); setError('');
    try {
      const r = await axios.get(`${API}/crm/v2/quotes/${quote.id}/sage/export.csv`, { headers: headers(), responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([r.data], { type: 'text/csv' }));
      const a = document.createElement('a');
      a.href = url; a.download = `sage_${quote.quote_number || quote.id}.csv`; a.click();
      window.URL.revokeObjectURL(url);
    } catch (e) { setError('No export to download yet'); }
    setBusy('');
  };

  const t = intel?.totals || {};
  const status = quote.sage_status;

  return (
    <div className="mt-6 pt-4" style={{ borderTop: `1px solid ${border}` }} data-testid="quote-sage-panel">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold flex items-center gap-2" style={{ color: c.text }}><Receipt size={15} /> Sage 200 export</h3>
        {status && <span className="text-[10px] font-bold uppercase px-2 py-1 rounded" style={{ background: `${STATUS_COLOR[status] || c.textDim}20`, color: STATUS_COLOR[status] || c.textDim }} data-testid="quote-sage-status">{status.replace(/_/g, ' ')}</span>}
      </div>

      {error && <div className="mb-3 text-xs px-3 py-1.5 rounded-md flex items-center gap-2" style={{ background: 'rgba(239,68,68,0.08)', color: 'var(--color-danger-alt)' }} data-testid="quote-sage-error"><AlertTriangle size={13} />{error}</div>}

      {/* Quote intelligence summary */}
      {intel && (
        <div className="mb-3 rounded-lg border p-3" style={{ borderColor: border, background: surface2 }} data-testid="quote-intelligence">
          <div className="flex flex-wrap items-center gap-3 text-xs">
            <span className="inline-flex items-center gap-1 font-semibold" style={{ color: c.text }}><Sparkles size={12} /> Quote intelligence</span>
            {t.missing_sage > 0 && <span style={{ color: FLAG_COLOR.error }}>{t.missing_sage} missing Sage code</span>}
            {t.obsolete > 0 && <span style={{ color: FLAG_COLOR.warning }}>{t.obsolete} obsolete</span>}
            {t.low_margin > 0 && <span style={{ color: FLAG_COLOR.warning }}>{t.low_margin} low margin</span>}
            {t.price_changed > 0 && <span style={{ color: FLAG_COLOR.info }}>{t.price_changed} price changed</span>}
            {!t.missing_sage && !t.obsolete && !t.low_margin && !t.price_changed && <span style={{ color: 'var(--color-success-alt)' }}>All lines look good</span>}
          </div>
          {/* per-line flags */}
          {intel.lines?.some(l => l.flags.length > 0) && (
            <div className="mt-2 space-y-1">
              {intel.lines.filter(l => l.flags.length > 0).map(l => (
                <div key={l.index} className="text-[11px] flex items-center gap-2 flex-wrap" style={{ color: c.textMuted }}>
                  <span className="font-mono" style={{ color: c.textDim }}>{l.sku || `Line ${l.index + 1}`}</span>
                  {l.flags.map((f, fi) => <span key={fi} style={{ color: FLAG_COLOR[f.level] }}>· {f.msg}</span>)}
                </div>
              ))}
            </div>
          )}
          {/* suggestions */}
          {intel.suggestions?.length > 0 && (
            <div className="mt-2 text-[11px]" style={{ color: c.textDim }}>
              <Info size={11} className="inline mr-1" />
              Suggested add-ons: {intel.suggestions.slice(0, 2).map(s => (s.accessories[0]?.name || s.related[0]?.name)).filter(Boolean).join(', ') || 'related items available'}
            </div>
          )}
        </div>
      )}

      {/* Sage meta */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 mb-3">
        <div>
          <label className="text-[10px] uppercase" style={{ color: c.textDim }}>Sage account ref</label>
          <input value={accountRef} onChange={e => setAccountRef(e.target.value)} placeholder="e.g. PULSE001" className="w-full mt-1 px-2 py-1.5 text-xs rounded border" style={{ background: surface2, borderColor: border, color: c.text }} data-testid="quote-sage-account-ref" />
        </div>
        <div>
          <label className="text-[10px] uppercase" style={{ color: c.textDim }}>Default nominal</label>
          <input value={nominal} onChange={e => setNominal(e.target.value)} placeholder="e.g. 4000" className="w-full mt-1 px-2 py-1.5 text-xs rounded border" style={{ background: surface2, borderColor: border, color: c.text }} data-testid="quote-sage-nominal" />
        </div>
        <div className="flex items-end gap-2">
          <label className="flex items-center gap-1.5 text-[11px] pb-1.5" style={{ color: c.textMuted }}><input type="checkbox" checked={ackObsolete} onChange={e => setAckObsolete(e.target.checked)} data-testid="quote-sage-ack-obsolete" /> Allow obsolete</label>
          <button type="button" onClick={saveMeta} disabled={busy === 'meta'} className="text-[11px] font-semibold px-2 py-1.5 rounded border" style={{ borderColor: border, color: c.text }} data-testid="quote-sage-save-meta">{busy === 'meta' ? <Loader2 size={11} className="animate-spin" /> : 'Save'}</button>
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 flex-wrap">
        <button type="button" onClick={validate} disabled={!!busy} className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-md border" style={{ borderColor: border, color: c.text }} data-testid="quote-sage-validate">{busy === 'validate' ? <Loader2 size={13} className="animate-spin" /> : <ShieldCheck size={13} />} Validate</button>
        <button type="button" onClick={runExport} disabled={!!busy} className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-md text-white" style={{ background: 'var(--color-info-ios)' }} data-testid="quote-sage-export">{busy === 'export' ? <Loader2 size={13} className="animate-spin" /> : <FileCheck2 size={13} />} Export to Sage</button>
        <button type="button" onClick={downloadCsv} disabled={!!busy} className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-md border" style={{ borderColor: border, color: c.text }} data-testid="quote-sage-download">{busy === 'csv' ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />} Download CSV</button>
      </div>

      {/* Validation report */}
      {report && (
        <div className="mt-3 rounded-lg border p-3 text-xs" style={{ borderColor: border }} data-testid="quote-sage-report">
          <div className="font-semibold mb-1" style={{ color: report.ready ? 'var(--color-success-alt)' : 'var(--color-danger-alt)' }}>{report.ready ? 'Ready for Sage 200' : 'Validation failed'} · account {report.account_ref || '—'} · net £{report.net_total}</div>
          {report.errors?.map((e, i) => <div key={`e${i}`} style={{ color: 'var(--color-danger-alt)' }}>✕ {e}</div>)}
          {report.warnings?.map((w, i) => <div key={`w${i}`} style={{ color: 'var(--color-accent-amber)' }}>! {w}</div>)}
        </div>
      )}

      {/* Export result */}
      {exportRec && (
        <div className="mt-3 rounded-lg border p-3 text-xs" style={{ borderColor: border, background: surface2 }} data-testid="quote-sage-export-result">
          <div style={{ color: 'var(--color-success-alt)', fontWeight: 600 }}>Exported · {exportRec.line_count} lines · net £{exportRec.net_total} · VAT £{exportRec.vat_total} · gross £{exportRec.gross_total}</div>
          <div style={{ color: c.textDim }} className="mt-0.5">{exportRec.note}</div>
        </div>
      )}
    </div>
  );
}
