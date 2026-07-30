import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { ShieldCheck, CheckCircle2, Loader2, FileText, PenLine, RotateCcw } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const money = (n, cur = 'GBP') => new Intl.NumberFormat('en-GB', { style: 'currency', currency: cur }).format(Number(n) || 0);

function SignaturePad({ onChange }) {
  const ref = useRef(null);
  const drawing = useRef(false);
  const has = useRef(false);

  const pos = (e) => {
    const r = ref.current.getBoundingClientRect();
    const t = e.touches ? e.touches[0] : e;
    return { x: t.clientX - r.left, y: t.clientY - r.top };
  };
  const start = (e) => { e.preventDefault(); drawing.current = true; const c = ref.current.getContext('2d'); const p = pos(e); c.beginPath(); c.moveTo(p.x, p.y); };
  const move = (e) => {
    if (!drawing.current) return; e.preventDefault();
    const c = ref.current.getContext('2d'); const p = pos(e);
    c.lineWidth = 2.2; c.lineCap = 'round'; c.strokeStyle = '#0F172A';
    c.lineTo(p.x, p.y); c.stroke(); has.current = true;
  };
  const end = () => { if (!drawing.current) return; drawing.current = false; if (has.current) onChange(ref.current.toDataURL('image/png')); };
  const clear = () => { const c = ref.current; c.getContext('2d').clearRect(0, 0, c.width, c.height); has.current = false; onChange(''); };

  useEffect(() => {
    const c = ref.current; c.width = c.offsetWidth; c.height = 170;
  }, []);

  return (
    <div>
      <canvas ref={ref} data-testid="esign-pad"
        onMouseDown={start} onMouseMove={move} onMouseUp={end} onMouseLeave={end}
        onTouchStart={start} onTouchMove={move} onTouchEnd={end}
        style={{ width: '100%', height: 170, background: '#fff', border: '1px dashed #CBD5E1', borderRadius: 10, touchAction: 'none', cursor: 'crosshair' }} />
      <button type="button" onClick={clear} data-testid="esign-clear"
        style={{ marginTop: 8, fontSize: 12, color: '#64748B', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
        <RotateCcw size={12} /> Clear signature
      </button>
    </div>
  );
}

export default function PublicQuoteSignPage() {
  const { token } = useParams();
  const [quote, setQuote] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [name, setName] = useState('');
  const [sig, setSig] = useState('');
  const [agree, setAgree] = useState(false);
  const [signing, setSigning] = useState(false);
  const [done, setDone] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/public/mod-quote/${token}`);
      setQuote(r.data);
      if (r.data.esign_status === 'signed' || r.data.status === 'accepted') setDone(true);
    } catch (e) {
      setError(e.response?.data?.detail || 'This quote link is invalid or has expired.');
    }
    setLoading(false);
  }, [token]);
  useEffect(() => { load(); }, [load]);

  const brand = quote?.brand_color || '#0055FF';
  const cur = quote?.currency || 'GBP';

  const sign = async () => {
    if (!name.trim() || !sig || !agree) return;
    setSigning(true);
    try {
      await axios.post(`${API}/public/mod-quote/${token}/sign`, { signer_name: name.trim(), signature: sig });
      setDone(true);
    } catch (e) {
      setError(e.response?.data?.detail || 'Could not record your signature. Please try again.');
    }
    setSigning(false);
  };

  if (loading) return <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#F1F5F9' }}><Loader2 className="animate-spin" size={28} color="#64748B" /></div>;

  if (error && !quote) return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#F1F5F9', padding: 24 }}>
      <div style={{ maxWidth: 420, textAlign: 'center', background: '#fff', padding: 40, borderRadius: 16, border: '1px solid #E2E8F0' }} data-testid="esign-error">
        <p style={{ fontSize: 16, fontWeight: 600, color: '#0F172A' }}>Link unavailable</p>
        <p style={{ fontSize: 14, color: '#64748B', marginTop: 8 }}>{error}</p>
      </div>
    </div>
  );

  return (
    <div style={{ minHeight: '100vh', background: '#F1F5F9', fontFamily: "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif" }}>
      {/* Header */}
      <div style={{ background: '#fff', borderBottom: '1px solid #E2E8F0' }}>
        <div style={{ maxWidth: 720, margin: '0 auto', padding: '18px 24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          {quote?.logo_url
            ? <img src={quote.logo_url} alt={quote.org_name} style={{ height: 36, maxWidth: 170, objectFit: 'contain' }} />
            : <span style={{ fontSize: 18, fontWeight: 700, color: '#0F172A' }}>{quote?.org_name}</span>}
          <a href={`${API}/public/mod-quote/${token}/pdf`} target="_blank" rel="noreferrer" data-testid="esign-pdf"
            style={{ fontSize: 13, color: brand, display: 'inline-flex', alignItems: 'center', gap: 6, fontWeight: 600 }}>
            <FileText size={15} /> PDF
          </a>
        </div>
      </div>

      <div style={{ maxWidth: 720, margin: '0 auto', padding: '28px 24px 60px' }}>
        {/* Title */}
        <div style={{ height: 4, background: brand, borderRadius: 999, width: 56, marginBottom: 16 }} />
        <p style={{ fontSize: 12, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', color: brand }}>
          Quote {quote?.quote_number}{quote?.mod_contract_type ? ` · MOD Contract Type ${quote.mod_contract_type}` : ''}
        </p>
        <h1 style={{ fontSize: 26, fontWeight: 800, color: '#0F172A', margin: '6px 0 4px' }}>{quote?.title}</h1>
        <p style={{ fontSize: 14, color: '#64748B' }}>{quote?.mod_site_name || quote?.company_name}</p>

        {/* Line items */}
        <div style={{ background: '#fff', border: '1px solid #E2E8F0', borderRadius: 14, marginTop: 20, overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
            <thead>
              <tr style={{ background: '#F8FAFC', color: '#64748B', fontSize: 12, textAlign: 'left' }}>
                <th style={{ padding: '10px 16px' }}>Description</th>
                <th style={{ padding: '10px 8px', textAlign: 'center', width: 50 }}>Qty</th>
                <th style={{ padding: '10px 16px', textAlign: 'right', width: 110 }}>Amount</th>
              </tr>
            </thead>
            <tbody>
              {(quote?.lines || []).map((l, i) => (
                <tr key={i} style={{ borderTop: '1px solid #F1F5F9' }}>
                  <td style={{ padding: '10px 16px', color: '#0F172A' }}>{l.description || l.product_name}</td>
                  <td style={{ padding: '10px 8px', textAlign: 'center', color: '#64748B' }}>{l.quantity}</td>
                  <td style={{ padding: '10px 16px', textAlign: 'right', color: '#0F172A' }}>{money((Number(l.unit_price) || 0) * (Number(l.quantity) || 1), cur)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ padding: '14px 16px', borderTop: '1px solid #E2E8F0', background: '#FAFCFF' }}>
            <Row label="Net" val={money(quote?.subtotal, cur)} />
            <Row label={`VAT (${quote?.vat_rate ?? 20}%)`} val={money(quote?.vat_amount, cur)} />
            <Row label="Total" val={money(quote?.total, cur)} bold color={brand} />
          </div>
        </div>
        {quote?.notes && <p style={{ fontSize: 13, color: '#64748B', marginTop: 14 }}>{quote.notes}</p>}

        {/* Sign / done */}
        {done ? (
          <div style={{ marginTop: 24, background: '#fff', border: '1px solid #BBF7D0', borderRadius: 14, padding: 28, textAlign: 'center' }} data-testid="esign-done">
            <CheckCircle2 size={40} color="#16A34A" style={{ margin: '0 auto' }} />
            <p style={{ fontSize: 18, fontWeight: 700, color: '#0F172A', marginTop: 10 }}>Quote accepted</p>
            <p style={{ fontSize: 14, color: '#64748B', marginTop: 4 }}>
              Signed by {quote?.signer_name || name}{quote?.signed_at ? ` on ${new Date(quote.signed_at).toLocaleDateString('en-GB')}` : ''}. Thank you — {quote?.org_name} has been notified.
            </p>
          </div>
        ) : (
          <div style={{ marginTop: 24, background: '#fff', border: '1px solid #E2E8F0', borderRadius: 14, padding: 24 }}>
            <p style={{ fontSize: 15, fontWeight: 700, color: '#0F172A', display: 'flex', alignItems: 'center', gap: 8 }}>
              <PenLine size={17} color={brand} /> Accept &amp; sign this quote
            </p>
            <label style={{ display: 'block', fontSize: 12, color: '#64748B', margin: '16px 0 4px', fontWeight: 600 }}>Full name</label>
            <input value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Maj. A. Smith" data-testid="esign-name"
              style={{ width: '100%', padding: '10px 12px', border: '1px solid #CBD5E1', borderRadius: 8, fontSize: 14, color: '#0F172A', outline: 'none' }} />
            <label style={{ display: 'block', fontSize: 12, color: '#64748B', margin: '16px 0 4px', fontWeight: 600 }}>Signature</label>
            <SignaturePad onChange={setSig} />
            <label style={{ display: 'flex', alignItems: 'flex-start', gap: 8, marginTop: 14, fontSize: 13, color: '#475569' }}>
              <input type="checkbox" checked={agree} onChange={e => setAgree(e.target.checked)} data-testid="esign-agree" style={{ marginTop: 2 }} />
              I confirm I am authorised to accept this quote and agree to its terms on behalf of {quote?.mod_site_name || quote?.company_name || 'the customer'}.
            </label>
            {error && <p style={{ color: '#DC2626', fontSize: 13, marginTop: 10 }}>{error}</p>}
            <button onClick={sign} disabled={!name.trim() || !sig || !agree || signing} data-testid="esign-submit"
              style={{ marginTop: 18, width: '100%', padding: '13px', background: (!name.trim() || !sig || !agree) ? '#94A3B8' : brand, color: '#fff', border: 'none', borderRadius: 10, fontSize: 15, fontWeight: 700, cursor: (!name.trim() || !sig || !agree) ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
              {signing ? <Loader2 size={17} className="animate-spin" /> : <ShieldCheck size={17} />} Accept &amp; Sign
            </button>
          </div>
        )}
        <p style={{ textAlign: 'center', fontSize: 11, color: '#94A3B8', marginTop: 24 }}>Secured by {quote?.org_name} · Pulse Fitness</p>
      </div>
    </div>
  );
}

function Row({ label, val, bold, color }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '3px 0' }}>
      <span style={{ fontSize: bold ? 15 : 13, color: bold ? '#0F172A' : '#64748B', fontWeight: bold ? 700 : 500 }}>{label}</span>
      <span style={{ fontSize: bold ? 16 : 13, color: color || (bold ? '#0F172A' : '#334155'), fontWeight: bold ? 800 : 600 }}>{val}</span>
    </div>
  );
}
