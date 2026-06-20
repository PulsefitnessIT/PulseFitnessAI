import React, { useState, useEffect, useCallback } from 'react';
import { useCRM } from './CRMApp';
import {
  Plus, FileText, X, ArrowLeft, GitCompareArrows,
  Building2, User, ChevronRight, History, Copy,
  Printer, Mail, AlertTriangle, Loader2, Package, Search, Layers,
} from 'lucide-react';
import axios from 'axios';
import CRMQuoteSagePanel from './CRMQuoteSagePanel';
import { formatMoneySync } from '@/utils/localization';

const STATUS_COLORS = { draft: 'var(--color-text-faint-alt)', sent: 'var(--color-info-ios)', accepted: 'var(--color-success-alt)', rejected: 'var(--color-danger)', pending_approval: 'var(--color-warning)', approved: 'var(--color-success-alt-2)', superseded: 'var(--color-accent-violet)' };
const fmt = (n) => formatMoneySync(n, { minimumFractionDigits: 2 });

/* ═══ SIGNATURE PAD ═══ */
function SignaturePad({ onSave, onCancel, isDark, c }) {
  const canvasRef = React.useRef(null);
  const drawingRef = React.useRef(false);
  const [signerName, setSignerName] = React.useState('');

  const getCtx = () => canvasRef.current?.getContext('2d');

  const getPos = (e) => {
    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    const clientX = e.clientX ?? e.touches?.[0]?.clientX ?? 0;
    const clientY = e.clientY ?? e.touches?.[0]?.clientY ?? 0;
    return {
      x: (clientX - rect.left) * (canvas.width / rect.width),
      y: (clientY - rect.top) * (canvas.height / rect.height),
    };
  };

  const startDraw = (e) => {
    e.preventDefault();
    drawingRef.current = true;
    const ctx = getCtx();
    const { x, y } = getPos(e);
    ctx.beginPath();
    ctx.moveTo(x, y);
  };
  const draw = (e) => {
    if (!drawingRef.current) return;
    e.preventDefault();
    const ctx = getCtx();
    const { x, y } = getPos(e);
    ctx.lineWidth = 2;
    ctx.lineCap = 'round';
    ctx.strokeStyle = isDark ? '#fff' : '#000';
    ctx.lineTo(x, y);
    ctx.stroke();
  };
  const stopDraw = () => { drawingRef.current = false; };
  const clearPad = () => {
    const ctx = getCtx();
    ctx.clearRect(0, 0, canvasRef.current.width, canvasRef.current.height);
  };
  const save = () => {
    const data = canvasRef.current.toDataURL('image/png');
    onSave(data, signerName);
  };

  return (
    <div data-testid="signature-pad">
      <div className="mb-3">
        <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Signer Name</label>
        <input value={signerName} onChange={e => setSignerName(e.target.value)} placeholder="Full name"
          className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${isDark ? 'var(--color-surface-dark-3)' : 'var(--color-border-alt)'}`, color: c.text }} />
      </div>
      <p className="text-[10px] uppercase tracking-wider font-medium mb-1" style={{ color: c.textDim }}>Draw Signature</p>
      <canvas ref={canvasRef} width={400} height={150}
        onMouseDown={startDraw} onMouseMove={draw} onMouseUp={stopDraw} onMouseLeave={stopDraw}
        onTouchStart={startDraw} onTouchMove={draw} onTouchEnd={stopDraw}
        className="w-full rounded-md cursor-crosshair" style={{ border: `1px solid ${isDark ? 'var(--color-surface-dark-3)' : 'var(--color-border-alt)'}`, background: isDark ? 'var(--color-ink-alt)' : '#fff' }} />
      <div className="flex gap-2 mt-3 justify-end">
        <button onClick={clearPad} className="px-3 py-1.5 text-xs" style={{ color: c.textMuted }}>Clear</button>
        <button onClick={onCancel} className="px-3 py-1.5 text-xs" style={{ color: c.textMuted }}>Cancel</button>
        <button onClick={save} disabled={!signerName.trim()} className="px-3 py-1.5 bg-[var(--color-success-alt)] text-white text-xs font-medium rounded-md disabled:opacity-50" data-testid="save-signature-btn">Save Signature</button>
      </div>
    </div>
  );
}

/* ═══ QUOTE DETAIL ═══ */
function QuoteDetail({ quoteId, onBack, onSelect, c, isDark, API, headers }) {
  const [quote, setQuote] = useState(null);
  const [showSign, setShowSign] = useState(false);
  const [actionLoading, setActionLoading] = useState('');
  const [showRevise, setShowRevise] = useState(false);
  const [reviseForm, setReviseForm] = useState({ lines: [], notes: '', valid_until: '', vat_rate: 20 });
  const [versions, setVersions] = useState([]);
  const [showVersions, setShowVersions] = useState(false);
  const [savingRevise, setSavingRevise] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/crm/v2/quotes?limit=200`, { headers: headers() });
      const found = res.data.quotes.find(q => q.id === quoteId);
      setQuote(found);
    } catch (e) { console.error(e); }
  }, [API, headers, quoteId]);

  useEffect(() => { load(); }, [load]);

  const loadVersions = async () => {
    try {
      const res = await axios.get(`${API}/crm/v2/quotes/${quoteId}/versions`, { headers: headers() });
      setVersions(res.data.versions || []);
      setShowVersions(true);
    } catch (e) { console.error(e); }
  };

  const submitApproval = async () => {
    setActionLoading('submit');
    try { await axios.post(`${API}/crm/v2/quotes/${quoteId}/submit-approval`, {}, { headers: headers() }); load(); } catch (e) { console.error(e); }
    setActionLoading('');
  };
  const approveReject = async (action, reason = '') => {
    setActionLoading(action);
    try { await axios.post(`${API}/crm/v2/quotes/${quoteId}/approve`, { action, reason }, { headers: headers() }); load(); } catch (e) { console.error(e); }
    setActionLoading('');
  };
  const handleSign = async (sigData, signerName) => {
    setActionLoading('sign');
    try { await axios.post(`${API}/crm/v2/quotes/${quoteId}/sign`, { signature: sigData, signer_name: signerName }, { headers: headers() }); setShowSign(false); load(); } catch (e) { console.error(e); }
    setActionLoading('');
  };

  const openRevise = () => {
    setReviseForm({
      lines: (quote.lines || []).map(l => ({ ...l })),
      notes: quote.notes || '',
      valid_until: quote.valid_until || '',
      vat_rate: quote.vat_rate || 20,
    });
    setShowRevise(true);
  };

  const addReviseLine = () => setReviseForm({ ...reviseForm, lines: [...reviseForm.lines, { description: '', quantity: 1, unit_price: 0, discount: 0 }] });
  const removeReviseLine = (i) => {
    if (reviseForm.lines.length <= 1) return;
    setReviseForm({ ...reviseForm, lines: reviseForm.lines.filter((_, idx) => idx !== i) });
  };
  const updateReviseLine = (i, field, value) => {
    const updated = [...reviseForm.lines];
    updated[i] = { ...updated[i], [field]: field === 'description' ? value : parseFloat(value) || 0 };
    setReviseForm({ ...reviseForm, lines: updated });
  };

  const reviseSubtotal = reviseForm.lines.reduce((s, l) => s + (l.quantity * l.unit_price * (1 - (l.discount || 0) / 100)), 0);
  const reviseVat = reviseSubtotal * reviseForm.vat_rate / 100;
  const reviseTotal = reviseSubtotal + reviseVat;

  const submitRevise = async () => {
    setSavingRevise(true);
    try {
      const res = await axios.post(`${API}/crm/v2/quotes/${quoteId}/revise`, reviseForm, { headers: headers() });
      setShowRevise(false);
      if (onSelect) onSelect(res.data.id);
    } catch (e) { console.error(e); }
    setSavingRevise(false);
  };

  // Iter 216h265 — print + email a quote. Print downloads the PDF;
  // email asks for a recipient (defaults to linked contact) and
  // dispatches via Resend with the PDF attached.
  const [emailDialog, setEmailDialog] = useState(null);
  const downloadPdf = async () => {
    setActionLoading('print');
    try {
      const res = await axios.get(`${API}/crm/v2/quotes/${quoteId}/pdf`, {
        headers: headers(),
        responseType: 'blob',
      });
      const url = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
      const a = document.createElement('a');
      a.href = url;
      a.download = `${quote.quote_number || 'quote'}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error(e);
      window.alert('Could not download PDF — check backend logs.');
    } finally {
      setActionLoading('');
    }
  };
  const openEmailDialog = () => {
    setEmailDialog({
      to: '',
      subject: `Quote ${quote.quote_number || ''}`.trim(),
      message: '',
      sending: false,
    });
  };
  const sendQuoteEmail = async () => {
    if (!emailDialog) return;
    setEmailDialog((d) => ({ ...d, sending: true }));
    try {
      const res = await axios.post(
        `${API}/crm/v2/quotes/${quoteId}/send-email`,
        {
          to: emailDialog.to || undefined,
          subject: emailDialog.subject || undefined,
          message: emailDialog.message || undefined,
        },
        { headers: headers() },
      );
      setEmailDialog(null);
      window.alert(`Quote emailed to ${res.data.to}`);
      load();
    } catch (e) {
      const detail = e?.response?.data?.detail || e?.message || 'Send failed';
      window.alert(detail);
      setEmailDialog((d) => d && ({ ...d, sending: false }));
    }
  };

  if (!quote) return <div className="flex items-center justify-center h-64"><div className="w-5 h-5 border-2 border-[var(--color-info-ios)] border-t-transparent rounded-full animate-spin" /></div>;

  const statusColor = STATUS_COLORS[quote.status] || 'var(--color-text-faint-alt)';

  return (
    <div data-testid="crm-quote-detail">
      <button onClick={onBack} className="flex items-center gap-1.5 text-sm mb-4 hover:underline" style={{ color: c.textMuted }} data-testid="quote-back-btn">
        <ArrowLeft size={14} /> Back to Quotes
      </button>

      <div className="rounded-lg border p-6" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between mb-6">
          <div>
            <h2 className="text-xl font-bold" style={{ color: c.text }}>{quote.quote_number}</h2>
            <p className="text-xs mt-0.5" style={{ color: c.textDim }}>Created by {quote.created_by} &middot; v{quote.version}</p>
          </div>
          <div className="flex items-center gap-2 overflow-x-auto pb-1 -mb-1 [&>*]:flex-shrink-0" data-testid="quote-actions-row">
            <button onClick={downloadPdf} disabled={actionLoading === 'print'} className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-md border transition-all hover:bg-white/5 disabled:opacity-50" style={{ borderColor: c.border, color: c.textMuted }} data-testid="quote-print-btn">
              {actionLoading === 'print' ? <Loader2 size={12} className="animate-spin" /> : <Printer size={12} />} Print
            </button>
            <button onClick={openEmailDialog} disabled={quote.status === 'superseded'} className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-md border transition-all hover:bg-white/5 disabled:opacity-50" style={{ borderColor: 'var(--color-info-ios)40', color: 'var(--color-info-ios)' }} data-testid="quote-email-btn">
              <Mail size={12} /> Email
            </button>
            <button onClick={loadVersions} className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-md border transition-all hover:bg-white/5" style={{ borderColor: c.border, color: c.textMuted }} data-testid="quote-versions-btn">
              <History size={12} /> Versions
            </button>
            {quote.status !== 'superseded' && (
              <button onClick={openRevise} className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-md border transition-all hover:bg-white/5" style={{ borderColor: 'var(--color-info-ios)40', color: 'var(--color-info-ios)' }} data-testid="quote-revise-btn">
                <Copy size={12} /> Revise
              </button>
            )}
            <span className="text-[10px] font-bold uppercase px-2 py-1 rounded" style={{ background: `${statusColor}20`, color: statusColor }}>{quote.status?.replace('_', ' ')}</span>
          </div>
        </div>

        {/* Iter 216h265 — approval-required callout (margin below min). */}
        {(quote.approval_required || quote.approval_status === 'pending_approval') && quote.status !== 'approved' && (
          <div className="mb-4 flex items-start gap-2 p-3 rounded-lg border" style={{ background: 'var(--color-warning)10', borderColor: 'var(--color-warning)40' }} data-testid="quote-approval-callout">
            <AlertTriangle size={14} style={{ color: 'var(--color-warning)', marginTop: 2 }} />
            <div className="flex-1 text-xs">
              <p className="font-semibold" style={{ color: 'var(--color-warning)' }}>
                {quote.approval_status === 'pending_approval' ? 'Awaiting management approval' : 'Approval required before sending'}
              </p>
              <p style={{ color: c.textMuted }}>
                {quote.margin_percent != null
                  ? <>Margin <b>{Number(quote.margin_percent).toFixed(1)}%</b> is below the configured minimum.</>
                  : <>This quote falls below the agreed margin floor.</>}
                {' '}A manager must approve it before it can be sent or signed.
              </p>
            </div>
          </div>
        )}

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
          {[
            { l: 'Subtotal', v: fmt(quote.subtotal) },
            { l: `VAT (${quote.vat_rate}%)`, v: fmt(quote.vat_amount) },
            { l: 'Total', v: fmt(quote.total), bold: true, color: 'var(--color-success-alt)' },
            { l: 'Valid Until', v: quote.valid_until || 'N/A' },
          ].map(kpi => (
            <div key={kpi.l} className="p-3 rounded-lg border" style={{ background: isDark ? 'var(--color-neutral-950)' : 'var(--color-neutral-50)', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
              <p className="text-[10px] uppercase tracking-wider" style={{ color: c.textDim }}>{kpi.l}</p>
              <p className={`text-lg ${kpi.bold ? 'font-bold' : 'font-medium'}`} style={{ color: kpi.color || c.text }}>{kpi.v}</p>
            </div>
          ))}
        </div>

        {/* Line Items */}
        <div className="overflow-x-auto mb-6">
          <table className="w-full text-sm" data-testid="quote-lines-table">
            <thead>
              <tr style={{ borderBottom: `1px solid ${isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)'}` }}>
                {['Description', 'Qty', 'Unit Price', 'Discount', 'Total'].map(h => (
                  <th key={h} className={`py-2 text-[10px] uppercase tracking-wider font-medium ${h === 'Description' ? 'text-left' : 'text-right'}`} style={{ color: c.textDim }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(quote.lines || []).map((line, i) => (
                <tr key={i} style={{ borderBottom: `1px solid ${isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)'}` }}>
                  <td className="py-3" style={{ color: c.text }}>{line.description || line.product_name || `Item ${i + 1}`}</td>
                  <td className="py-3 text-right" style={{ color: c.textMuted }}>{line.quantity}</td>
                  <td className="py-3 text-right" style={{ color: c.textMuted }}>{fmt(line.unit_price)}</td>
                  <td className="py-3 text-right" style={{ color: c.textMuted }}>{line.discount || 0}%</td>
                  <td className="py-3 text-right font-medium" style={{ color: c.text }}>{fmt(line.quantity * line.unit_price * (1 - (line.discount || 0) / 100))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {quote.notes && (
          <div className="p-3 rounded-lg" style={{ background: isDark ? 'var(--color-neutral-950)' : 'var(--color-neutral-100)' }}>
            <p className="text-xs" style={{ color: c.textDim }}>Notes</p>
            <p className="text-sm mt-1" style={{ color: c.text }}>{quote.notes}</p>
          </div>
        )}

        {/* Iter 220 P1 — Quote intelligence + Sage 200 export prep */}
        <CRMQuoteSagePanel API={API} headers={headers} c={c} isDark={isDark} quote={quote} onChanged={load} />

        {/* Approval Workflow */}
        <div className="mt-6 pt-4" style={{ borderTop: `1px solid ${isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)'}` }}>
          <h3 className="text-sm font-semibold mb-3" style={{ color: c.text }}>Approval & Signature</h3>
          <div className="flex items-center gap-3 flex-wrap mb-3">
            {quote.status === 'draft' && (
              <button onClick={submitApproval} disabled={!!actionLoading}
                className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-md border"
                style={{ borderColor: 'var(--color-warning)30', color: 'var(--color-warning)' }}
                data-testid="submit-approval-btn">
                {actionLoading === 'submit' ? 'Submitting...' : 'Submit for Approval'}
              </button>
            )}
            {quote.status === 'pending_approval' && (
              <>
                <button onClick={() => approveReject('approve')} disabled={!!actionLoading}
                  className="flex items-center gap-1.5 px-3 py-2 bg-[var(--color-success-alt)] text-white text-xs font-medium rounded-md"
                  data-testid="approve-quote-btn">
                  {actionLoading === 'approve' ? 'Approving...' : 'Approve'}
                </button>
                <button onClick={() => approveReject('reject')} disabled={!!actionLoading}
                  className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-md border"
                  style={{ borderColor: 'var(--color-danger-alt)30', color: 'var(--color-danger-alt)' }}
                  data-testid="reject-quote-btn">
                  {actionLoading === 'reject' ? 'Rejecting...' : 'Reject'}
                </button>
                <span className="text-[10px]" style={{ color: 'var(--color-warning)' }}>Submitted by {quote.submitted_by}</span>
              </>
            )}
            {(quote.status === 'approved' || quote.status === 'sent') && !quote.signature && (
              <button onClick={() => setShowSign(true)} disabled={!!actionLoading}
                className="flex items-center gap-1.5 px-3 py-2 bg-[var(--color-info-ios)] text-white text-xs font-medium rounded-md"
                data-testid="sign-quote-btn">
                Sign Quote
              </button>
            )}
            {quote.approved_by && <span className="text-[10px]" style={{ color: 'var(--color-success-alt)' }}>Approved by {quote.approved_by}</span>}
            {quote.rejected_by && <span className="text-[10px]" style={{ color: 'var(--color-danger-alt)' }}>Rejected by {quote.rejected_by}{quote.rejected_reason ? `: ${quote.rejected_reason}` : ''}</span>}
          </div>

          {/* Signature display */}
          {quote.signature && (
            <div className="p-4 rounded-lg border" style={{ borderColor: 'var(--color-success-alt)30', background: 'var(--color-success-alt)08' }} data-testid="signature-display">
              <div className="flex items-center gap-3">
                <img src={quote.signature} alt="Signature" className="h-16 rounded" style={{ maxWidth: '200px' }} />
                <div>
                  <p className="text-sm font-medium" style={{ color: c.text }}>Signed by {quote.signer_name}</p>
                  <p className="text-[10px]" style={{ color: c.textDim }}>{quote.signed_at ? new Date(quote.signed_at).toLocaleString('en-GB') : ''}</p>
                </div>
              </div>
            </div>
          )}

          {/* Signature Pad */}
          {showSign && (
            <div className="mt-3 p-4 rounded-lg border" style={{ borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
              <SignaturePad onSave={handleSign} onCancel={() => setShowSign(false)} isDark={isDark} c={c} />
            </div>
          )}
        </div>

        {/* Version History */}
        {showVersions && (
          <div className="mt-6 pt-4" style={{ borderTop: `1px solid ${isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)'}` }}>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold flex items-center gap-1.5" style={{ color: c.text }}><History size={14} /> Version History</h3>
              <button onClick={() => setShowVersions(false)} className="text-xs" style={{ color: c.textDim }}>Hide</button>
            </div>
            <div className="space-y-2">
              {versions.map(v => {
                const vColor = STATUS_COLORS[v.status] || 'var(--color-text-faint-alt)';
                const isCurrent = v.id === quoteId;
                return (
                  <div key={v.id} onClick={() => { if (!isCurrent && onSelect) onSelect(v.id); }}
                    className={`flex items-center gap-3 p-3 rounded-md border transition-all ${isCurrent ? '' : 'cursor-pointer hover:scale-[1.005]'}`}
                    style={{ borderColor: isCurrent ? 'var(--color-info-ios)40' : (isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)'), background: isCurrent ? (isDark ? 'var(--color-navy-950)' : 'var(--color-info-bg)') : 'transparent' }}
                    data-testid={`version-row-${v.version}`}>
                    <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0" style={{ background: `${vColor}15` }}>
                      <span className="text-xs font-bold" style={{ color: vColor }}>v{v.version}</span>
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-medium" style={{ color: c.text }}>{v.quote_number}</p>
                        <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded" style={{ background: `${vColor}20`, color: vColor }}>{v.status?.replace('_', ' ')}</span>
                        {isCurrent && <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded bg-[rgb(var(--rgb-info-ios)/0.15)] text-[var(--color-info-ios)]">Current</span>}
                      </div>
                      <p className="text-[10px]" style={{ color: c.textDim }}>
                        {v.lines?.length || 0} items &middot; {fmt(v.total)} &middot; {v.created_by} &middot; {new Date(v.created_at).toLocaleDateString('en-GB')}
                      </p>
                    </div>
                  </div>
                );
              })}
              {versions.length === 0 && <p className="text-sm text-center py-4" style={{ color: c.textDim }}>No version history</p>}
            </div>
          </div>
        )}

        {quote.status === 'superseded' && quote.superseded_by && (
          <div className="mt-4 p-3 rounded-md" style={{ background: 'var(--color-accent-violet)10', border: '1px solid var(--color-accent-violet)30' }}>
            <p className="text-xs" style={{ color: 'var(--color-accent-violet)' }}>
              This quote has been superseded by a newer version.
              <button onClick={() => onSelect && onSelect(quote.superseded_by)} className="ml-1 underline font-medium">View latest version</button>
            </p>
          </div>
        )}
      </div>

      {/* Revise Quote Dialog */}
      {showRevise && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => setShowRevise(false)}>
          <div className="w-full max-w-2xl mx-4 rounded-xl p-6 shadow-2xl max-h-[90vh] overflow-y-auto"
            style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', border: `1px solid ${c.border}` }} onClick={e => e.stopPropagation()} data-testid="revise-quote-dialog">
            <div className="sticky top-0 z-10 -mx-6 -mt-6 px-6 pt-6 pb-3 mb-4 flex items-center justify-between border-b" style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', borderColor: c.border }}>
              <div>
                <h2 className="text-lg font-semibold" style={{ color: c.text }}>Revise Quote</h2>
                <p className="text-xs" style={{ color: c.textDim }}>Creating v{(quote.version || 1) + 1} from {quote.quote_number}</p>
              </div>
              <button onClick={() => setShowRevise(false)} className="p-1 hover:opacity-70" style={{ color: c.textDim }} data-testid="revise-quote-close"><X size={16} /></button>
            </div>

            {/* Line Items */}
            <div className="mb-4">
              <div className="flex items-center justify-between mb-2">
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Line Items</label>
                <button type="button" onClick={addReviseLine} className="text-xs text-[var(--color-info-ios)] hover:underline">+ Add line</button>
              </div>
              <div className="space-y-2">
                {reviseForm.lines.map((line, i) => (
                  <div key={i} className="grid grid-cols-12 gap-2 items-end" data-testid={`revise-line-${i}`}>
                    <div className="col-span-5">
                      {i === 0 && <span className="text-[9px]" style={{ color: c.textDim }}>Description</span>}
                      <input value={line.description} onChange={e => updateReviseLine(i, 'description', e.target.value)} placeholder="Product/service"
                        className="w-full px-2 py-1.5 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
                    </div>
                    <div className="col-span-2">
                      {i === 0 && <span className="text-[9px]" style={{ color: c.textDim }}>Qty</span>}
                      <input type="number" min="1" value={line.quantity} onChange={e => updateReviseLine(i, 'quantity', e.target.value)}
                        className="w-full px-2 py-1.5 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
                    </div>
                    <div className="col-span-2">
                      {i === 0 && <span className="text-[9px]" style={{ color: c.textDim }}>Price</span>}
                      <input type="number" min="0" step="0.01" value={line.unit_price} onChange={e => updateReviseLine(i, 'unit_price', e.target.value)}
                        className="w-full px-2 py-1.5 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
                    </div>
                    <div className="col-span-2">
                      {i === 0 && <span className="text-[9px]" style={{ color: c.textDim }}>Disc %</span>}
                      <input type="number" min="0" max="100" value={line.discount} onChange={e => updateReviseLine(i, 'discount', e.target.value)}
                        className="w-full px-2 py-1.5 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
                    </div>
                    <div className="col-span-1 flex justify-center">
                      {reviseForm.lines.length > 1 && <button type="button" onClick={() => removeReviseLine(i)} style={{ color: 'var(--color-danger-alt)' }}><X size={14} /></button>}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Totals */}
            <div className="flex justify-end mb-4">
              <div className="w-56 space-y-1.5 text-sm">
                <div className="flex justify-between"><span style={{ color: c.textDim }}>Subtotal</span><span style={{ color: c.text }}>{fmt(reviseSubtotal)}</span></div>
                <div className="flex justify-between"><span style={{ color: c.textDim }}>VAT ({reviseForm.vat_rate}%)</span><span style={{ color: c.text }}>{fmt(reviseVat)}</span></div>
                <div className="flex justify-between font-bold pt-1" style={{ borderTop: `1px solid ${c.border}` }}>
                  <span style={{ color: c.text }}>Total</span><span style={{ color: 'var(--color-success-alt)' }}>{fmt(reviseTotal)}</span>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 mb-4">
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Valid Until</label>
                <input type="date" value={reviseForm.valid_until} onChange={e => setReviseForm({ ...reviseForm, valid_until: e.target.value })}
                  className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Notes</label>
                <input value={reviseForm.notes} onChange={e => setReviseForm({ ...reviseForm, notes: e.target.value })}
                  className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
              </div>
            </div>

            <div className="flex gap-2 justify-end">
              <button onClick={() => setShowRevise(false)} className="px-4 py-2 text-sm" style={{ color: c.textMuted }}>Cancel</button>
              <button onClick={submitRevise} disabled={savingRevise} className="px-4 py-2 bg-[var(--color-info-ios)] text-white text-sm font-medium rounded-md disabled:opacity-50" data-testid="submit-revise-btn">
                {savingRevise ? 'Creating...' : `Create v${(quote.version || 1) + 1}`}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Iter 216h265 — Email quote dialog */}
      {emailDialog && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" data-testid="quote-email-dialog">
          <div className="rounded-lg max-w-md w-full shadow-2xl" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', border: `1px solid ${c.border}` }}>
            <div className="p-5 border-b flex items-center justify-between" style={{ borderColor: c.border }}>
              <div>
                <p className="text-[10px] font-bold uppercase tracking-[0.14em]" style={{ color: 'var(--color-info-ios)' }}>Send quote</p>
                <h3 className="text-base font-bold" style={{ color: c.text }}>{quote.quote_number}</h3>
              </div>
              <button onClick={() => setEmailDialog(null)} className="opacity-60 hover:opacity-100" style={{ color: c.textMuted }} data-testid="quote-email-dialog-close"><X size={16} /></button>
            </div>
            <div className="p-5 space-y-3">
              <div>
                <label className="block text-[10px] font-bold uppercase tracking-wider mb-1" style={{ color: c.textDim }}>To</label>
                <input
                  type="email"
                  value={emailDialog.to}
                  onChange={(e) => setEmailDialog((d) => ({ ...d, to: e.target.value }))}
                  placeholder="customer@example.com (leave blank to use linked contact)"
                  className="w-full px-3 py-2 text-sm rounded-md border"
                  style={{ background: isDark ? 'var(--color-neutral-950)' : '#fff', borderColor: c.border, color: c.text }}
                  data-testid="quote-email-to"
                />
              </div>
              <div>
                <label className="block text-[10px] font-bold uppercase tracking-wider mb-1" style={{ color: c.textDim }}>Subject</label>
                <input
                  type="text"
                  value={emailDialog.subject}
                  onChange={(e) => setEmailDialog((d) => ({ ...d, subject: e.target.value }))}
                  className="w-full px-3 py-2 text-sm rounded-md border"
                  style={{ background: isDark ? 'var(--color-neutral-950)' : '#fff', borderColor: c.border, color: c.text }}
                  data-testid="quote-email-subject"
                />
              </div>
              <div>
                <label className="block text-[10px] font-bold uppercase tracking-wider mb-1" style={{ color: c.textDim }}>Message <span className="opacity-60 font-normal">(optional)</span></label>
                <textarea
                  rows={4}
                  value={emailDialog.message}
                  onChange={(e) => setEmailDialog((d) => ({ ...d, message: e.target.value }))}
                  placeholder="Hi, please find attached…"
                  className="w-full px-3 py-2 text-sm rounded-md border"
                  style={{ background: isDark ? 'var(--color-neutral-950)' : '#fff', borderColor: c.border, color: c.text }}
                  data-testid="quote-email-message"
                />
              </div>
              <p className="text-[11px]" style={{ color: c.textDim }}>The quote PDF will be attached automatically.</p>
            </div>
            <div className="p-5 border-t flex gap-2 justify-end" style={{ borderColor: c.border }}>
              <button onClick={() => setEmailDialog(null)} className="px-4 py-2 text-sm" style={{ color: c.textMuted }} data-testid="quote-email-cancel">Cancel</button>
              <button onClick={sendQuoteEmail} disabled={emailDialog.sending} className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-md text-white disabled:opacity-50" style={{ background: 'var(--color-info-ios)' }} data-testid="quote-email-send">
                {emailDialog.sending ? <Loader2 size={12} className="animate-spin" /> : <Mail size={12} />}
                {emailDialog.sending ? 'Sending…' : 'Send quote'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ═══ MAIN CPQ ═══ */
export default function CRMCPQ() {
  const crm = useCRM();
  const { API, headers, c, isDark, navTarget, setNavTarget } = crm;
  const [quotes, setQuotes] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [selectedQuote, setSelectedQuote] = useState(null);
  const [showCreate, setShowCreate] = useState(false);
  const [companies, setCompanies] = useState([]);
  const [contacts, setContacts] = useState([]);
  const [opps, setOpps] = useState([]);
  // Iter 216h269 — products catalogue + bundle expansion in the quote
  // builder. Each line item may carry a `product_id` (link back to
  // the master price list), `cost_price` (drives the margin badge),
  // and `from_bundle_id` / `from_bundle_name` (set when a bundle
  // exploded into N lines so the rep can see the provenance).
  const [products, setProducts] = useState([]);
  const [canSeeCost, setCanSeeCost] = useState(false);
  const [showPicker, setShowPicker] = useState(false);
  const [productSearch, setProductSearch] = useState('');
  const [expanding, setExpanding] = useState(null);  // product id being expanded
  const [form, setForm] = useState({
    company_id: '', contact_id: '', opportunity_id: '',
    valid_until: '', notes: '', vat_rate: 20,
    lines: [{ description: '', quantity: 1, unit_price: 0, discount: 0 }],
  });
  const [saving, setSaving] = useState(false);

  // Cross-module navigation
  useEffect(() => {
    if (navTarget?.type === 'quote' && navTarget?.id) {
      setSelectedQuote(navTarget.id);
      setNavTarget(null);
    }
  }, [navTarget, setNavTarget]);

  const load = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/crm/v2/quotes?limit=200`, { headers: headers() });
      setQuotes(res.data.quotes);
      setTotal(res.data.total);
    } catch (e) { console.error(e); }
    setLoading(false);
  }, [API, headers]);

  const loadLookups = useCallback(async () => {
    try {
      const [coRes, ctRes, oppRes, prodRes, permRes] = await Promise.all([
        axios.get(`${API}/crm/v2/companies?limit=200`, { headers: headers() }),
        axios.get(`${API}/crm/v2/contacts?limit=200`, { headers: headers() }),
        axios.get(`${API}/crm/v2/opportunities?limit=200`, { headers: headers() }),
        axios.get(`${API}/crm/products?active=true&limit=500`, { headers: headers() }),
        axios.get(`${API}/crm/product-perms/me`, { headers: headers() }).catch(() => ({ data: { can_see_cost: true } })),
      ]);
      setCompanies(coRes.data.companies);
      setContacts(ctRes.data.contacts);
      setOpps(oppRes.data.opportunities);
      setProducts(prodRes.data.products || []);
      setCanSeeCost(permRes.data?.can_see_cost !== false);
    } catch (e) { console.error(e); }
  }, [API, headers]);

  useEffect(() => { load(); }, [load]);

  const addLine = () => {
    setForm({ ...form, lines: [...form.lines, { description: '', quantity: 1, unit_price: 0, discount: 0 }] });
  };
  const removeLine = (i) => {
    if (form.lines.length <= 1) return;
    setForm({ ...form, lines: form.lines.filter((_, idx) => idx !== i) });
  };
  const updateLine = (i, field, value) => {
    const updated = [...form.lines];
    updated[i] = { ...updated[i], [field]: field === 'description' ? value : parseFloat(value) || 0 };
    setForm({ ...form, lines: updated });
  };

  const subtotal = form.lines.reduce((s, l) => s + (l.quantity * l.unit_price * (1 - (l.discount || 0) / 100)), 0);
  const vatAmount = subtotal * form.vat_rate / 100;
  const grandTotal = subtotal + vatAmount;

  // Iter 216h269 — margin badge. Computed only over lines that carry
  // a `cost_price` (typically populated when the line came from the
  // master price list). Manual lines without a cost are excluded.
  const totalCost = form.lines.reduce((s, l) => s + ((Number(l.cost_price) || 0) * (Number(l.quantity) || 0)), 0);
  const sellOfCosted = form.lines.reduce((s, l) => {
    if (!Number(l.cost_price)) return s;
    return s + (Number(l.quantity) * Number(l.unit_price) * (1 - (Number(l.discount) || 0) / 100));
  }, 0);
  const marginAmount = sellOfCosted - totalCost;
  const marginPercent = sellOfCosted > 0 ? (marginAmount / sellOfCosted) * 100 : 0;
  const hasCostedLines = totalCost > 0;

  // Iter 216h269 — drop a product onto the quote. Non-bundles append
  // one line. Bundles call /crm/products/{id}/expand → push N lines
  // (one per component) with `from_bundle_*` provenance so the rep
  // can see the lineage at-a-glance.
  const addProductToQuote = async (p) => {
    if (!p || !p.id) return;
    if (!p.is_bundle) {
      const next = [
        ...form.lines.filter(l => l.description.trim() || Number(l.unit_price)),
        {
          description: p.name + (p.sku ? ` (${p.sku})` : ''),
          quantity: 1,
          unit_price: Number(p.sell_price) || 0,
          discount: 0,
          product_id: p.id,
          cost_price: Number(p.cost_price) || 0,
          tax_rate: Number(p.tax_rate) || 0,
        },
      ];
      setForm(prev => ({ ...prev, lines: next.length ? next : prev.lines }));
      setShowPicker(false);
      return;
    }
    setExpanding(p.id);
    try {
      const r = await axios.get(`${API}/crm/products/${p.id}/expand`, { headers: headers() });
      const components = r.data?.items || [];
      const newLines = components.map(item => ({
        description: `${item.name}${item.sku ? ` (${item.sku})` : ''}${item.from_bundle_name ? ` · from ${item.from_bundle_name}` : ''}`,
        quantity: Number(item.quantity) || 1,
        unit_price: Number(item.sell_price) || 0,
        discount: 0,
        product_id: item.product_id,
        cost_price: Number(item.cost_price) || 0,
        tax_rate: Number(item.tax_rate) || 0,
        from_bundle_id: item.from_bundle_id || p.id,
        from_bundle_name: item.from_bundle_name || p.name,
        missing: !!item.missing,
      }));
      const keepExisting = form.lines.filter(l => l.description.trim() || Number(l.unit_price));
      setForm(prev => ({ ...prev, lines: [...keepExisting, ...newLines] }));
      setShowPicker(false);
    } catch (e) {
      console.error('Bundle expand failed', e);
    }
    setExpanding(null);
  };

  const filteredProducts = (() => {
    const q = productSearch.trim().toLowerCase();
    if (!q) return products.slice(0, 80);
    return products.filter(p =>
      (p.name || '').toLowerCase().includes(q)
      || (p.sku || '').toLowerCase().includes(q)
      || (p.category || '').toLowerCase().includes(q),
    ).slice(0, 80);
  })();

  const handleCreate = async () => {
    if (form.lines.every(l => !l.description.trim())) return;
    setSaving(true);
    try {
      await axios.post(`${API}/crm/v2/quotes`, form, { headers: headers() });
      setShowCreate(false);
      setForm({ company_id: '', contact_id: '', opportunity_id: '', valid_until: '', notes: '', vat_rate: 20, lines: [{ description: '', quantity: 1, unit_price: 0, discount: 0 }] });
      load();
    } catch (e) { console.error(e); }
    setSaving(false);
  };

  const openCreate = () => { loadLookups(); setShowCreate(true); };

  if (selectedQuote) {
    return <QuoteDetail quoteId={selectedQuote} onBack={() => { setSelectedQuote(null); load(); }} onSelect={setSelectedQuote} {...crm} />;
  }

  if (loading) return <div className="flex items-center justify-center h-64"><div className="w-5 h-5 border-2 border-[var(--color-info-ios)] border-t-transparent rounded-full animate-spin" /></div>;

  const totalValue = quotes.reduce((s, q) => s + (q.total || 0), 0);

  return (
    <div data-testid="crm-cpq">
      {/* Toolbar — counts + actions */}
      <div className="flex items-center justify-end gap-3 mb-3 flex-wrap">
        <p className="text-xs mr-auto" style={{ color: c.textDim }}>
          {total} quote{total !== 1 ? 's' : ''} &middot; {fmt(totalValue)} total value
        </p>
        <button type="button" onClick={() => crm.setActiveTab && crm.setActiveTab('quote-compare')} className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-md border transition-all hover:bg-white/5" style={{ borderColor: c.border, color: c.textMuted }} data-testid="compare-quotes-btn">
          <GitCompareArrows size={14} /> Compare
        </button>
        <button type="button" onClick={openCreate} className="btn-primary" data-testid="create-quote-btn">
          <Plus size={14} /> New Quote
        </button>
      </div>

      {/* Quote list */}
      <div className="space-y-2">
        {quotes.map(q => {
          const statusColor = STATUS_COLORS[q.status] || 'var(--color-text-faint-alt)';
          return (
            <div key={q.id} onClick={() => setSelectedQuote(q.id)}
              className="flex items-center gap-4 p-4 rounded-lg border cursor-pointer transition-all hover:scale-[1.005]"
              style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}
              data-testid={`quote-row-${q.id}`}>
              <div className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0" style={{ background: `${statusColor}15` }}>
                <FileText size={18} style={{ color: statusColor }} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-semibold" style={{ color: c.text }}>{q.quote_number}</p>
                  <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded" style={{ background: `${statusColor}20`, color: statusColor }}>{q.status}</span>
                </div>
                <p className="text-[11px] mt-0.5" style={{ color: c.textDim }}>
                  {q.company_name && <><Building2 size={10} className="inline mr-0.5" />{q.company_name}</>}
                  {q.contact_name && <> &middot; <User size={10} className="inline mr-0.5" />{q.contact_name}</>}
                  {q.created_by && <> &middot; Rep: {q.created_by}</>}
                </p>
                <p className="text-[10px] mt-0.5" style={{ color: c.textDim }}>
                  {q.lines?.length || 0} item{(q.lines?.length || 0) !== 1 ? 's' : ''} &middot; v{q.version} &middot; {new Date(q.created_at).toLocaleDateString('en-GB')}
                </p>
              </div>
              <div className="text-right shrink-0">
                <p className="text-sm font-bold" style={{ color: 'var(--color-success-alt)' }}>{fmt(q.total)}</p>
                <p className="text-[10px]" style={{ color: c.textDim }}>ex VAT {fmt(q.subtotal)}</p>
              </div>
              <ChevronRight size={16} style={{ color: c.textDim }} />
            </div>
          );
        })}
        {quotes.length === 0 && (
          <div className="text-center py-16 rounded-lg border" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
            <FileText size={40} className="mx-auto mb-3" style={{ color: c.textDim }} />
            <p className="text-sm font-medium" style={{ color: c.textMuted }}>No quotes yet</p>
            <button onClick={openCreate} className="text-sm text-[var(--color-info-ios)] mt-2 hover:underline">Create your first quote</button>
          </div>
        )}
      </div>

      {/* Create Quote Dialog */}
      {showCreate && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => setShowCreate(false)}>
          <div className="w-full max-w-2xl mx-4 rounded-xl p-6 shadow-2xl max-h-[90vh] overflow-y-auto"
            style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', border: `1px solid ${c.border}` }} onClick={e => e.stopPropagation()} data-testid="create-quote-dialog">
            <div className="sticky top-0 z-10 -mx-6 -mt-6 px-6 pt-6 pb-3 mb-4 flex items-center justify-between border-b" style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', borderColor: c.border }}>
              <h2 className="text-lg font-semibold" style={{ color: c.text }}>New Quote</h2>
              <button onClick={() => setShowCreate(false)} className="p-1 hover:opacity-70" style={{ color: c.textDim }} data-testid="create-quote-close"><X size={16} /></button>
            </div>

            <div className="grid grid-cols-3 gap-3 mb-4">
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Company</label>
                <select value={form.company_id} onChange={e => setForm({ ...form, company_id: e.target.value, contact_id: '' })}
                  className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }}>
                  <option value="">Select...</option>
                  {companies.map(co => <option key={co.id} value={co.id}>{co.name}</option>)}
                </select>
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Contact</label>
                <select value={form.contact_id} onChange={e => setForm({ ...form, contact_id: e.target.value })}
                  className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }}>
                  <option value="">{form.company_id ? 'Select...' : 'Select company first...'}</option>
                  {(form.company_id ? contacts.filter(ct => ct.company_id === form.company_id) : contacts).map(ct => <option key={ct.id} value={ct.id}>{ct.first_name} {ct.last_name}</option>)}
                </select>
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Opportunity</label>
                <select value={form.opportunity_id} onChange={e => setForm({ ...form, opportunity_id: e.target.value })}
                  className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }}>
                  <option value="">None</option>
                  {opps.map(o => <option key={o.id} value={o.id}>{o.title} ({fmt(o.value)})</option>)}
                </select>
              </div>
            </div>

            {/* Line Items */}
            <div className="mb-4">
              <div className="flex items-center justify-between mb-2">
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Line Items</label>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => { setShowPicker(s => !s); setProductSearch(''); }}
                    className="text-xs inline-flex items-center gap-1 px-2 py-1 rounded border"
                    style={{ borderColor: c.border, color: 'var(--color-info-ios)' }}
                    data-testid="quote-add-from-catalogue-btn"
                  >
                    <Package size={11} /> Add from catalogue
                  </button>
                  <button type="button" onClick={addLine} className="text-xs text-[var(--color-info-ios)] hover:underline" data-testid="quote-add-line-btn">+ Add line</button>
                </div>
              </div>
              {showPicker && (
                <div
                  className="mb-3 rounded-lg border p-3"
                  style={{ background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-25-alt)', borderColor: c.border }}
                  data-testid="quote-product-picker"
                >
                  <div className="flex items-center gap-2 mb-2">
                    <div className="relative flex-1">
                      <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 opacity-50" />
                      <input
                        type="text"
                        autoFocus
                        value={productSearch}
                        onChange={e => setProductSearch(e.target.value)}
                        placeholder="Search products, SKUs, bundles…"
                        className="w-full h-8 pl-8 pr-3 text-xs rounded-md"
                        style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }}
                        data-testid="quote-product-search"
                      />
                    </div>
                    <button
                      type="button"
                      onClick={() => setShowPicker(false)}
                      className="opacity-60 hover:opacity-100"
                      style={{ color: c.textDim }}
                      data-testid="quote-product-picker-close"
                    ><X size={14} /></button>
                  </div>
                  {filteredProducts.length === 0 && (
                    <p className="text-[11px] py-2" style={{ color: c.textDim }} data-testid="quote-product-picker-empty">
                      No products in the master price list match &ldquo;{productSearch || 'this filter'}&rdquo;. Add some in CRM Settings &rarr; Price List.
                    </p>
                  )}
                  <div className="max-h-56 overflow-y-auto -mx-1">
                    {filteredProducts.map(p => (
                      <button
                        key={p.id}
                        type="button"
                        onClick={() => addProductToQuote(p)}
                        disabled={expanding === p.id}
                        className="w-full flex items-center gap-2 px-2 py-1.5 text-left text-xs rounded-md hover:bg-black/5 dark:hover:bg-white/5 disabled:opacity-50"
                        data-testid={`quote-product-pick-${p.id}`}
                      >
                        {p.is_bundle ? <Layers size={12} style={{ color: 'var(--color-accent-violet)' }} /> : <Package size={12} style={{ color: c.textDim }} />}
                        <span className="flex-1 truncate" style={{ color: c.text }}>{p.name}</span>
                        {p.sku && <span className="opacity-60 text-[10px]" style={{ color: c.textDim }}>{p.sku}</span>}
                        {p.is_bundle && (
                          <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded" style={{ background: 'var(--color-accent-violet)20', color: 'var(--color-accent-violet)' }} data-testid={`quote-product-bundle-badge-${p.id}`}>Bundle</span>
                        )}
                        <span className="opacity-80 font-mono text-[11px]" style={{ color: c.textMuted }}>{fmt(p.sell_price)}</span>
                        {expanding === p.id && <Loader2 size={10} className="animate-spin" />}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              <div className="space-y-2">
                {form.lines.map((line, i) => (
                  <div key={i} className="grid grid-cols-12 gap-2 items-end" data-testid={`quote-line-${i}`}>
                    <div className="col-span-5">
                      {i === 0 && <span className="text-[9px]" style={{ color: c.textDim }}>Description</span>}
                      <input value={line.description} onChange={e => updateLine(i, 'description', e.target.value)} placeholder="Product/service"
                        className="w-full px-2 py-1.5 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
                    </div>
                    <div className="col-span-2">
                      {i === 0 && <span className="text-[9px]" style={{ color: c.textDim }}>Qty</span>}
                      <input type="number" min="1" value={line.quantity} onChange={e => updateLine(i, 'quantity', e.target.value)}
                        className="w-full px-2 py-1.5 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
                    </div>
                    <div className="col-span-2">
                      {i === 0 && <span className="text-[9px]" style={{ color: c.textDim }}>Price</span>}
                      <input type="number" min="0" step="0.01" value={line.unit_price} onChange={e => updateLine(i, 'unit_price', e.target.value)}
                        className="w-full px-2 py-1.5 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
                    </div>
                    <div className="col-span-2">
                      {i === 0 && <span className="text-[9px]" style={{ color: c.textDim }}>Disc %</span>}
                      <input type="number" min="0" max="100" value={line.discount} onChange={e => updateLine(i, 'discount', e.target.value)}
                        className="w-full px-2 py-1.5 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
                    </div>
                    <div className="col-span-1 flex justify-center">
                      {form.lines.length > 1 && <button type="button" onClick={() => removeLine(i)} style={{ color: 'var(--color-danger-alt)' }}><X size={14} /></button>}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Totals */}
            <div className="flex justify-end mb-4">
              <div className="w-72 space-y-1.5 text-sm">
                <div className="flex justify-between"><span style={{ color: c.textDim }}>Subtotal</span><span style={{ color: c.text }}>{fmt(subtotal)}</span></div>
                <div className="flex justify-between"><span style={{ color: c.textDim }}>VAT ({form.vat_rate}%)</span><span style={{ color: c.text }}>{fmt(vatAmount)}</span></div>
                <div className="flex justify-between font-bold pt-1" style={{ borderTop: `1px solid ${c.border}` }}>
                  <span style={{ color: c.text }}>Total</span><span style={{ color: 'var(--color-success-alt)' }}>{fmt(grandTotal)}</span>
                </div>
                {canSeeCost && hasCostedLines && (
                  <div
                    className="mt-2 px-2.5 py-1.5 rounded-md flex items-center justify-between text-[11px]"
                    style={{
                      background: marginPercent >= 30 ? 'rgba(16,185,129,0.08)' : marginPercent >= 15 ? 'rgba(245,158,11,0.08)' : 'rgba(239,68,68,0.08)',
                      color: marginPercent >= 30 ? 'var(--color-success-alt)' : marginPercent >= 15 ? 'var(--color-accent-amber)' : 'var(--color-danger-alt)',
                    }}
                    data-testid="quote-margin-badge"
                  >
                    <span className="font-semibold">Margin {marginPercent.toFixed(1)}%</span>
                    <span className="font-mono">cost {fmt(totalCost)} · sell {fmt(sellOfCosted)}</span>
                  </div>
                )}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 mb-4">
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Valid Until</label>
                <input type="date" value={form.valid_until} onChange={e => setForm({ ...form, valid_until: e.target.value })}
                  className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Notes</label>
                <input value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })}
                  className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
              </div>
            </div>

            <div className="flex gap-2 justify-end">
              <button onClick={() => setShowCreate(false)} className="px-4 py-2 text-sm" style={{ color: c.textMuted }}>Cancel</button>
              <button onClick={handleCreate} disabled={saving} className="px-4 py-2 bg-[var(--color-info-ios)] text-white text-sm font-medium rounded-md disabled:opacity-50">
                {saving ? 'Creating...' : 'Create Quote'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
