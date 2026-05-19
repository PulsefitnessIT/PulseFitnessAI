/**
 * PublicQuoteAcceptPage — no-login quote review + signature flow.
 *
 * Iter 216h130. Hit by a customer clicking the "Review & Accept Quote"
 * button in their email. Pulls the redacted quote, lets them review
 * lines and total, then sign + accept (or decline with reason).
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { useParams } from 'react-router-dom';
import {
  CheckCircle2, XCircle, Loader2, ShieldCheck,
} from 'lucide-react';

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
    const x = (t?.clientX ?? e.clientX) - rect.left;
    const y = (t?.clientY ?? e.clientY) - rect.top;
    return { x, y };
  };
  const start = (e) => {
    e.preventDefault();
    drawing.current = true;
    lastPt.current = point(e);
  };
  const move = (e) => {
    if (!drawing.current) return;
    e.preventDefault();
    const c = ctx();
    const pt = point(e);
    c.strokeStyle = '#0f172a';
    c.lineWidth = 2;
    c.lineCap = 'round';
    c.beginPath();
    c.moveTo(lastPt.current.x, lastPt.current.y);
    c.lineTo(pt.x, pt.y);
    c.stroke();
    lastPt.current = pt;
  };
  const end = () => {
    if (!drawing.current) return;
    drawing.current = false;
    try { onChange(canvasRef.current.toDataURL('image/png')); } catch {}
  };
  const clear = () => {
    const c = ctx();
    if (!c) return;
    c.clearRect(0, 0, canvasRef.current.width, canvasRef.current.height);
    onChange(null);
  };
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    // High-DPI: size backing store but keep CSS size
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = height * dpr;
    canvas.getContext('2d').scale(dpr, dpr);
  }, [height]);
  return (
    <div className="border border-slate-200 rounded-xl bg-white" data-testid="public-quote-signature-pad">
      <canvas
        ref={canvasRef}
        style={{ width: '100%', height: `${height}px`, touchAction: 'none', borderRadius: '12px' }}
        onMouseDown={start} onMouseMove={move} onMouseUp={end} onMouseLeave={end}
        onTouchStart={start} onTouchMove={move} onTouchEnd={end}
      />
      <div className="flex justify-between items-center px-3 py-2 border-t border-slate-100 text-xs text-slate-500">
        <span>Sign with your mouse or finger above</span>
        <button onClick={clear} className="text-slate-700 font-semibold hover:text-rose-600"
                data-testid="public-quote-signature-clear">Clear</button>
      </div>
    </div>
  );
}

export default function PublicQuoteAcceptPage() {
  const { shortcode } = useParams();
  const [quote, setQuote] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);

  const [name, setName] = useState('');
  const [note, setNote] = useState('');
  const [signature, setSignature] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(null);  // 'accepted' | 'declined'

  const [showDecline, setShowDecline] = useState(false);
  const [declineReason, setDeclineReason] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/public/quote/${shortcode}`);
      setQuote(r.data);
      if (r.data.status === 'accepted') setDone('accepted');
      if (r.data.status === 'declined') setDone('declined');
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Quote not found or expired');
    } finally {
      setLoading(false);
    }
  }, [shortcode]);

  useEffect(() => { load(); }, [load]);

  const accept = async () => {
    if (!name.trim()) return;
    setSubmitting(true);
    try {
      await axios.post(`${API}/public/quote/${shortcode}/accept`, {
        name: name.trim(), signature_data_url: signature, note: note.trim() || null,
      });
      setDone('accepted');
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Accept failed');
    } finally {
      setSubmitting(false);
    }
  };

  const decline = async () => {
    if (!name.trim()) return;
    setSubmitting(true);
    try {
      await axios.post(`${API}/public/quote/${shortcode}/decline`, {
        name: name.trim(), reason: declineReason.trim() || null,
      });
      setDone('declined');
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Decline failed');
    } finally {
      setSubmitting(false);
      setShowDecline(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center text-slate-500">
        <Loader2 className="animate-spin mr-2" size={20} /> Loading quote…
      </div>
    );
  }
  if (err || !quote) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center p-6">
        <div className="bg-white rounded-2xl border border-slate-200 p-8 max-w-md text-center shadow-sm" data-testid="public-quote-error">
          <XCircle size={28} className="mx-auto mb-3 text-rose-500" />
          <p className="text-slate-900 font-bold mb-1">Quote unavailable</p>
          <p className="text-sm text-slate-500">{err || 'This link is no longer active.'}</p>
        </div>
      </div>
    );
  }

  if (done) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center p-6">
        <div className="bg-white rounded-2xl border border-slate-200 p-8 max-w-md w-full text-center shadow-sm"
             data-testid={`public-quote-${done}-confirmation`}>
          {done === 'accepted' ? (
            <CheckCircle2 size={42} className="mx-auto mb-3 text-emerald-500" />
          ) : (
            <XCircle size={42} className="mx-auto mb-3 text-rose-500" />
          )}
          <p className="text-xl font-extrabold text-slate-900 mb-1">
            Quote {done === 'accepted' ? 'accepted' : 'declined'}
          </p>
          <p className="text-sm text-slate-500 mb-4">
            Quote <span className="font-mono">{quote.quote_number}</span> · {quote.engineer_name || 'Your engineer'} has been notified.
          </p>
          {done === 'accepted' && (
            <p className="text-xs text-slate-400">A copy of the signed quote has been logged. The engineer will be in touch shortly.</p>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50" data-testid="public-quote-page">
      {/* Header */}
      <div className="bg-gradient-to-br from-[#1d4ed8] via-[#6366f1] to-[#8b5cf6] text-white">
        <div className="max-w-3xl mx-auto px-5 py-8">
          <p className="text-[10px] font-bold uppercase tracking-[0.2em] opacity-80">GymAxis · Quotation</p>
          <h1 className="text-3xl font-extrabold mt-1" data-testid="public-quote-number">{quote.quote_number}</h1>
          <p className="text-sm opacity-90 mt-2">
            From <strong>{quote.engineer_name}</strong>
            {quote.valid_until ? ` · Valid until ${fmtDate(quote.valid_until)}` : ''}
          </p>
        </div>
      </div>

      <main className="max-w-3xl mx-auto px-5 py-6 pb-24 space-y-5">
        {/* Customer + Site */}
        <Card title="Quote for">
          <p className="text-base font-bold text-slate-900">{quote.customer_name}</p>
          {quote.site_name && <p className="text-sm text-slate-600 mt-0.5">{quote.site_name}</p>}
          {quote.site_address && <p className="text-sm text-slate-500">{quote.site_address}</p>}
          {(quote.asset_name || quote.asset_serial) && (
            <p className="text-xs text-slate-500 mt-2 pt-2 border-t border-slate-100">
              <strong>Asset:</strong> {quote.asset_name || '—'} · Serial {quote.asset_serial || '—'}
            </p>
          )}
        </Card>

        {/* Description */}
        {quote.description_of_work && (
          <Card title="Description of work">
            <p className="text-sm text-slate-700 whitespace-pre-wrap">{quote.description_of_work}</p>
          </Card>
        )}

        {/* Lines */}
        <Card title="Line items" testid="public-quote-lines">
          <div className="overflow-x-auto -mx-2 px-2">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-slate-500 text-xs border-b border-slate-200">
                  <th className="text-left py-2 pr-2">Item</th>
                  <th className="text-right py-2 pr-2 w-16">Qty</th>
                  <th className="text-right py-2 pr-2 w-20">Unit £</th>
                  <th className="text-right py-2 w-24">Total £</th>
                </tr>
              </thead>
              <tbody>
                {(quote.lines || []).map((ln, i) => (
                  <tr key={i} className="border-b border-slate-100">
                    <td className="py-2 pr-2">
                      <div className="text-slate-900">{ln.description}</div>
                      <div className="text-[10px] uppercase tracking-wide text-slate-400 mt-0.5">{ln.kind}</div>
                    </td>
                    <td className="py-2 pr-2 text-right tabular-nums">{ln.quantity}</td>
                    <td className="py-2 pr-2 text-right tabular-nums">{Number(ln.unit_price || 0).toFixed(2)}</td>
                    <td className="py-2 text-right font-semibold tabular-nums">{Number(ln.line_total || 0).toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        {/* Totals */}
        <Card title="Totals">
          <div className="space-y-1.5 text-sm" data-testid="public-quote-totals">
            <div className="flex justify-between text-slate-600">
              <span>Subtotal</span><span className="tabular-nums">{fmtGBP(quote.subtotal)}</span>
            </div>
            {Number(quote.discount_amount) > 0 && (
              <div className="flex justify-between text-rose-600">
                <span>Discount ({quote.discount_pct}%)</span>
                <span className="tabular-nums">-{fmtGBP(quote.discount_amount)}</span>
              </div>
            )}
            <div className="flex justify-between text-slate-600">
              <span>VAT ({quote.vat_rate}%)</span><span className="tabular-nums">{fmtGBP(quote.vat_amount)}</span>
            </div>
            <div className="border-t border-slate-200 pt-2 flex justify-between text-lg font-extrabold">
              <span className="text-slate-900">Total</span>
              <span className="text-blue-700 tabular-nums">{fmtGBP(quote.total)}</span>
            </div>
          </div>
        </Card>

        {/* Terms */}
        {quote.terms && (
          <Card title="Terms &amp; conditions">
            <p className="text-xs text-slate-500 whitespace-pre-wrap">{quote.terms}</p>
          </Card>
        )}

        {/* Accept / Decline */}
        {!showDecline ? (
          <Card title="Accept this quote" testid="public-quote-accept-section">
            <p className="text-sm text-slate-600 mb-3">
              Confirm your name below to accept. Adding a signature makes it
              legally binding.
            </p>
            <label className="text-[11px] uppercase font-bold tracking-wide text-slate-500 block mb-1">Your name *</label>
            <input
              type="text"
              className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white mb-3"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="Daniel Hayes"
              data-testid="public-quote-name"
            />
            <label className="text-[11px] uppercase font-bold tracking-wide text-slate-500 block mb-1">Signature</label>
            <SignaturePad onChange={setSignature} />
            <label className="text-[11px] uppercase font-bold tracking-wide text-slate-500 block mb-1 mt-3">Note for engineer (optional)</label>
            <textarea
              className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white"
              rows={2}
              value={note}
              onChange={e => setNote(e.target.value)}
              placeholder="e.g. Please book for next Tuesday morning."
              data-testid="public-quote-note"
            />
            <div className="flex gap-2 mt-4">
              <button
                type="button"
                onClick={accept}
                disabled={submitting || !name.trim()}
                className="flex-1 inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-gradient-to-br from-[#1d4ed8] to-[#6366f1] text-white text-sm font-bold shadow disabled:opacity-50"
                data-testid="public-quote-accept-btn"
              >
                {submitting ? <Loader2 className="animate-spin" size={16} /> : <CheckCircle2 size={16} />}
                Accept &amp; sign quote
              </button>
              <button
                type="button"
                onClick={() => setShowDecline(true)}
                className="inline-flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-white border border-slate-200 text-slate-700 text-sm font-bold hover:bg-slate-50"
                data-testid="public-quote-decline-btn"
              >
                Decline
              </button>
            </div>
            <p className="text-[10px] text-slate-400 mt-3 flex items-center gap-1.5">
              <ShieldCheck size={11} /> Secured by GymAxis. Submitted at {new Date().toLocaleString('en-GB')}.
            </p>
          </Card>
        ) : (
          <Card title="Decline this quote" testid="public-quote-decline-section">
            <label className="text-[11px] uppercase font-bold tracking-wide text-slate-500 block mb-1">Your name *</label>
            <input
              type="text"
              className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white mb-3"
              value={name}
              onChange={e => setName(e.target.value)}
              data-testid="public-quote-decline-name"
            />
            <label className="text-[11px] uppercase font-bold tracking-wide text-slate-500 block mb-1">Reason (optional)</label>
            <textarea
              className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white"
              rows={3}
              value={declineReason}
              onChange={e => setDeclineReason(e.target.value)}
              placeholder="e.g. Going with another supplier this time."
              data-testid="public-quote-decline-reason"
            />
            <div className="flex gap-2 mt-4">
              <button
                type="button"
                onClick={decline}
                disabled={submitting || !name.trim()}
                className="flex-1 inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-rose-600 text-white text-sm font-bold shadow disabled:opacity-50"
                data-testid="public-quote-decline-confirm"
              >
                {submitting ? <Loader2 className="animate-spin" size={16} /> : <XCircle size={16} />}
                Confirm decline
              </button>
              <button
                type="button"
                onClick={() => setShowDecline(false)}
                className="px-4 py-3 rounded-xl bg-white border border-slate-200 text-slate-700 text-sm font-bold"
                data-testid="public-quote-decline-cancel"
              >
                Go back
              </button>
            </div>
          </Card>
        )}
      </main>
    </div>
  );
}

const Card = ({ title, children, testid }) => (
  <section className="bg-white rounded-2xl border border-slate-200 p-5" data-testid={testid}>
    <h2 className="text-sm font-bold text-slate-900 mb-3" dangerouslySetInnerHTML={{ __html: title }} />
    {children}
  </section>
);
