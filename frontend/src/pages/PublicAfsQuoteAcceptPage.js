/**
 * PublicAfsQuoteAcceptPage — no-login Aftersales maintenance-quote review +
 * acceptance. Commercial customers land here from an emailed link at
 * /aq/:shortcode. They review the package, equipment and pricing, download the
 * branded PDF, then accept (with signature) or decline. Acceptance auto-prepares
 * a draft agreement for the Pulse coordinator.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { useParams } from 'react-router-dom';
import { CheckCircle2, XCircle, Loader2, ShieldCheck, FileText, Clock } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';

const fmtGBP = (n) => `£${Number(n || 0).toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const fmtDate = (s) => s ? new Date(s).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }) : '—';

function SignaturePad({ onChange, height = 140 }) {
  const canvasRef = useRef(null);
  const drawing = useRef(false);
  const lastPt = useRef(null);
  const ctx = () => canvasRef.current?.getContext('2d');
  const point = (e) => {
    const rect = canvasRef.current.getBoundingClientRect();
    const t = e.touches?.[0];
    return { x: (t?.clientX ?? e.clientX) - rect.left, y: (t?.clientY ?? e.clientY) - rect.top };
  };
  const start = (e) => { e.preventDefault(); drawing.current = true; lastPt.current = point(e); };
  const move = (e) => {
    if (!drawing.current) return;
    e.preventDefault();
    const c = ctx(); const pt = point(e);
    c.strokeStyle = '#0B3D91'; c.lineWidth = 2; c.lineCap = 'round';
    c.beginPath(); c.moveTo(lastPt.current.x, lastPt.current.y); c.lineTo(pt.x, pt.y); c.stroke();
    lastPt.current = pt;
  };
  const end = () => { if (!drawing.current) return; drawing.current = false; try { onChange(canvasRef.current.toDataURL('image/png')); } catch {} };
  const clear = () => { const c = ctx(); if (!c) return; c.clearRect(0, 0, canvasRef.current.width, canvasRef.current.height); onChange(null); };
  useEffect(() => {
    const canvas = canvasRef.current; if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr; canvas.height = height * dpr;
    canvas.getContext('2d').scale(dpr, dpr);
  }, [height]);
  return (
    <div className="border border-slate-200 rounded-xl bg-white" data-testid="afs-public-signature-pad">
      <canvas ref={canvasRef}
        style={{ width: '100%', height: `${height}px`, touchAction: 'none', borderRadius: '12px' }}
        onMouseDown={start} onMouseMove={move} onMouseUp={end} onMouseLeave={end}
        onTouchStart={start} onTouchMove={move} onTouchEnd={end} />
      <div className="flex justify-between items-center px-3 py-2 border-t border-slate-100 text-xs text-slate-500">
        <span>Sign with your mouse or finger above</span>
        <button onClick={clear} className="text-slate-700 font-semibold hover:text-rose-600" data-testid="afs-public-signature-clear">Clear</button>
      </div>
    </div>
  );
}

const Card = ({ title, children, testid }) => (
  <section className="bg-white rounded-2xl border border-slate-200 p-5" data-testid={testid}>
    {title && <h2 className="text-sm font-bold text-slate-900 mb-3">{title}</h2>}
    {children}
  </section>
);

export default function PublicAfsQuoteAcceptPage() {
  const { shortcode } = useParams();
  const [quote, setQuote] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [name, setName] = useState('');
  const [note, setNote] = useState('');
  const [signature, setSignature] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(null);
  const [showDecline, setShowDecline] = useState(false);
  const [declineReason, setDeclineReason] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/public/afs/quote/${shortcode}`);
      setQuote(r.data);
      if (r.data.portal_status === 'accepted') setDone('accepted');
      if (r.data.portal_status === 'declined') setDone('declined');
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Quote not found or expired');
    } finally { setLoading(false); }
  }, [shortcode]);
  useEffect(() => { load(); }, [load]);

  const accept = async () => {
    if (!name.trim()) return;
    setSubmitting(true);
    try {
      await axios.post(`${API}/public/afs/quote/${shortcode}/accept`, {
        name: name.trim(), signature_data_url: signature, note: note.trim() || null,
      });
      setDone('accepted');
    } catch (e) { setErr(e?.response?.data?.detail || 'Accept failed'); }
    finally { setSubmitting(false); }
  };
  const decline = async () => {
    if (!name.trim()) return;
    setSubmitting(true);
    try {
      await axios.post(`${API}/public/afs/quote/${shortcode}/decline`, {
        name: name.trim(), reason: declineReason.trim() || null,
      });
      setDone('declined');
    } catch (e) { setErr(e?.response?.data?.detail || 'Decline failed'); }
    finally { setSubmitting(false); setShowDecline(false); }
  };

  if (loading) {
    return <div className="min-h-screen bg-slate-50 flex items-center justify-center text-slate-500">
      <Loader2 className="animate-spin mr-2" size={20} /> Loading quote…</div>;
  }
  if (err || !quote) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center p-6">
        <div className="bg-white rounded-2xl border border-slate-200 p-8 max-w-md text-center shadow-sm" data-testid="afs-public-error">
          <XCircle size={28} className="mx-auto mb-3 text-rose-500" />
          <p className="text-slate-900 font-bold mb-1">Quote unavailable</p>
          <p className="text-sm text-slate-500">{err || 'This link is no longer active.'}</p>
        </div>
      </div>
    );
  }
  if (done) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center p-6" data-testid="afs-public-page">
        <div className="bg-white rounded-2xl border border-slate-200 p-8 max-w-md w-full text-center shadow-sm" data-testid={`afs-public-${done}-confirmation`}>
          {done === 'accepted' ? <CheckCircle2 size={42} className="mx-auto mb-3 text-emerald-500" />
            : <XCircle size={42} className="mx-auto mb-3 text-rose-500" />}
          <p className="text-xl font-extrabold text-slate-900 mb-1">Quote {done === 'accepted' ? 'accepted' : 'declined'}</p>
          <p className="text-sm text-slate-500 mb-4">
            Quote <span className="font-mono">{quote.quote_number}</span> · Pulse Fitness has been notified.
          </p>
          {done === 'accepted' && <p className="text-xs text-slate-400">Thank you. Your maintenance agreement is being prepared and our team will be in touch to confirm the start date.</p>}
        </div>
      </div>
    );
  }

  const sm = quote.summary || {};
  const expired = quote.expired;

  return (
    <div className="min-h-screen bg-slate-50" data-testid="afs-public-page">
      <div className="text-white" style={{ background: 'linear-gradient(135deg,#0B3D91 0%,#1763B5 60%,#00B5D8 100%)' }}>
        <div className="max-w-3xl mx-auto px-5 py-8">
          <p className="text-[10px] font-bold uppercase tracking-[0.2em] opacity-80">Pulse Fitness · Maintenance Agreement</p>
          <h1 className="text-3xl font-extrabold mt-1" data-testid="afs-public-quote-number">{quote.quote_number}</h1>
          <p className="text-sm opacity-90 mt-2">
            {String(quote.contract_type || '').charAt(0).toUpperCase() + String(quote.contract_type || '').slice(1)} package
            {quote.valid_until ? ` · Valid until ${fmtDate(quote.valid_until)}` : ''}
          </p>
        </div>
      </div>

      <main className="max-w-3xl mx-auto px-5 py-6 pb-24 space-y-5">
        <Card title="Prepared for">
          <p className="text-base font-bold text-slate-900">{quote.company_name}</p>
          <p className="text-sm text-slate-600 mt-0.5">{quote.term_years} year term · {String(quote.contract_type || '').toUpperCase()} maintenance</p>
          <button onClick={() => window.open(`${API}/public/afs/quote/${shortcode}/pdf`, '_blank')}
            className="mt-3 inline-flex items-center gap-2 text-sm font-semibold text-blue-700 hover:text-blue-900" data-testid="afs-public-pdf">
            <FileText size={15} /> Download full quote (PDF)
          </button>
        </Card>

        <Card title="Equipment covered" testid="afs-public-lines">
          <div className="overflow-x-auto -mx-2 px-2">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-slate-500 text-xs border-b border-slate-200">
                  <th className="text-right py-2 pr-2 w-12">Qty</th>
                  <th className="text-left py-2 pr-2">Machine</th>
                  <th className="text-right py-2 pr-2 w-28">Annual each</th>
                  <th className="text-right py-2 w-28">Annual total</th>
                </tr>
              </thead>
              <tbody>
                {(quote.grouped_lines || []).map((g, i) => (
                  <tr key={i} className="border-b border-slate-100">
                    <td className="py-2 pr-2 text-right tabular-nums">{g.qty}</td>
                    <td className="py-2 pr-2 text-slate-900">{g.model}{g.console_type ? ` · ${g.console_type}` : ''}</td>
                    <td className="py-2 pr-2 text-right tabular-nums">{fmtGBP(g.annual_unit)}</td>
                    <td className="py-2 text-right font-semibold tabular-nums">{fmtGBP(g.annual_total)}</td>
                  </tr>
                ))}
                {(quote.grouped_lines || []).length === 0 && (
                  <tr><td colSpan={4} className="py-3 text-slate-400 text-center">No priced equipment on this quote.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>

        <Card title="Pricing">
          <div className="space-y-1.5 text-sm" data-testid="afs-public-totals">
            <div className="flex justify-between text-slate-600"><span>Annual value</span><span className="tabular-nums">{fmtGBP(sm.final_annual)}</span></div>
            <div className="flex justify-between text-slate-600"><span>Monthly (Direct Debit)</span><span className="tabular-nums">{fmtGBP(sm.monthly)}</span></div>
            <div className="flex justify-between text-slate-600"><span>Term total ({sm.term_years || quote.term_years} yr)</span><span className="tabular-nums">{fmtGBP(sm.term_total)}</span></div>
            <div className="flex justify-between text-slate-600"><span>VAT ({((sm.vat_pct || 0) * 100).toFixed(0)}%)</span><span className="tabular-nums">{fmtGBP(sm.vat_amount)}</span></div>
            <div className="border-t border-slate-200 pt-2 flex justify-between text-lg font-extrabold">
              <span className="text-slate-900">Annual inc VAT</span>
              <span className="text-blue-700 tabular-nums">{fmtGBP(sm.final_annual_inc_vat)}</span>
            </div>
          </div>
        </Card>

        {expired ? (
          <Card testid="afs-public-expired">
            <div className="flex items-center gap-2 text-amber-600">
              <Clock size={18} /><p className="text-sm font-semibold">This quote has expired. Please contact Pulse Fitness for a fresh quote.</p>
            </div>
          </Card>
        ) : !showDecline ? (
          <Card title="Accept this quote" testid="afs-public-accept-section">
            <p className="text-sm text-slate-600 mb-3">Confirm your name to accept. Adding a signature makes it legally binding.</p>
            <label className="text-[11px] uppercase font-bold tracking-wide text-slate-500 block mb-1">Your name *</label>
            <input type="text" className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white mb-3"
              value={name} onChange={e => setName(e.target.value)} placeholder="Daniel Hayes" data-testid="afs-public-name" />
            <label className="text-[11px] uppercase font-bold tracking-wide text-slate-500 block mb-1">Signature</label>
            <SignaturePad onChange={setSignature} />
            <label className="text-[11px] uppercase font-bold tracking-wide text-slate-500 block mb-1 mt-3">Note for Pulse (optional)</label>
            <textarea className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white" rows={2}
              value={note} onChange={e => setNote(e.target.value)} placeholder="e.g. Preferred start date." data-testid="afs-public-note" />
            <div className="flex gap-2 mt-4">
              <button type="button" onClick={accept} disabled={submitting || !name.trim()}
                className="flex-1 inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl text-white text-sm font-bold shadow disabled:opacity-50"
                style={{ background: 'linear-gradient(135deg,#0B3D91,#1763B5)' }} data-testid="afs-public-accept-btn">
                {submitting ? <Loader2 className="animate-spin" size={16} /> : <CheckCircle2 size={16} />} Accept &amp; sign
              </button>
              <button type="button" onClick={() => setShowDecline(true)}
                className="inline-flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-white border border-slate-200 text-slate-700 text-sm font-bold hover:bg-slate-50" data-testid="afs-public-decline-btn">
                Decline
              </button>
            </div>
            <p className="text-[10px] text-slate-400 mt-3 flex items-center gap-1.5"><ShieldCheck size={11} /> Secured by Pulse Fitness.</p>
          </Card>
        ) : (
          <Card title="Decline this quote" testid="afs-public-decline-section">
            <label className="text-[11px] uppercase font-bold tracking-wide text-slate-500 block mb-1">Your name *</label>
            <input type="text" className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white mb-3"
              value={name} onChange={e => setName(e.target.value)} data-testid="afs-public-decline-name" />
            <label className="text-[11px] uppercase font-bold tracking-wide text-slate-500 block mb-1">Reason (optional)</label>
            <textarea className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white" rows={3}
              value={declineReason} onChange={e => setDeclineReason(e.target.value)} data-testid="afs-public-decline-reason" />
            <div className="flex gap-2 mt-4">
              <button type="button" onClick={decline} disabled={submitting || !name.trim()}
                className="flex-1 inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-rose-600 text-white text-sm font-bold shadow disabled:opacity-50" data-testid="afs-public-decline-confirm">
                {submitting ? <Loader2 className="animate-spin" size={16} /> : <XCircle size={16} />} Confirm decline
              </button>
              <button type="button" onClick={() => setShowDecline(false)}
                className="px-4 py-3 rounded-xl bg-white border border-slate-200 text-slate-700 text-sm font-bold" data-testid="afs-public-decline-cancel">Go back</button>
            </div>
          </Card>
        )}
      </main>
    </div>
  );
}
