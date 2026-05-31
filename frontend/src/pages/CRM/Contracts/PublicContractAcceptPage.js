/**
 * Iter 220e3 — Public Contract Accept page (Phase D).
 *
 * Routed at /contracts/accept/:token (set up in routes module).
 * Customer reviews the contract snapshot and signs via the existing
 * in-page canvas; the backend marks the contract Active.
 */
import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { CheckCircle, ShieldCheck, Calendar } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL + '/api';

function fmtDate(d) {
  return d ? new Date(d).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }) : '—';
}

export default function PublicContractAcceptPage() {
  const { token } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [signerName, setSignerName] = useState('');
  const [signing, setSigning] = useState(false);
  const [signed, setSigned] = useState(false);
  const canvasRef = useRef(null);
  const drawing = useRef(false);

  useEffect(() => {
    axios.get(`${API}/crm/v2/public/contracts/${token}`)
      .then(res => {
        setData(res.data);
        if (res.data.status === 'active' || res.data.signed_at) setSigned(true);
      })
      .catch(() => setError('This link is invalid or has expired.'));
  }, [token]);

  useEffect(() => {
    if (!canvasRef.current) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width;
    canvas.height = 150;
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.lineWidth = 2;
    ctx.lineCap = 'round';
    ctx.strokeStyle = '#0F172A';
  }, [data]);

  const pos = (e) => {
    const rect = canvasRef.current.getBoundingClientRect();
    const t = e.touches ? e.touches[0] : e;
    return { x: t.clientX - rect.left, y: t.clientY - rect.top };
  };
  const start = (e) => { e.preventDefault(); drawing.current = true; const p = pos(e); const ctx = canvasRef.current.getContext('2d'); ctx.beginPath(); ctx.moveTo(p.x, p.y); };
  const move = (e) => { if (!drawing.current) return; e.preventDefault(); const p = pos(e); const ctx = canvasRef.current.getContext('2d'); ctx.lineTo(p.x, p.y); ctx.stroke(); };
  const end = () => { drawing.current = false; };

  const submit = async () => {
    if (!signerName.trim()) { alert('Enter your full name to sign.'); return; }
    setSigning(true);
    try {
      const signature = canvasRef.current.toDataURL('image/png');
      await axios.post(`${API}/crm/v2/public/contracts/${token}/sign`, {
        signer_name: signerName, signature,
      });
      setSigned(true);
    } catch (e) {
      alert(e.response?.data?.detail || 'Sign failed.');
    }
    setSigning(false);
  };

  if (error) return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50">
      <div className="p-6 max-w-md rounded-2xl border bg-white text-center">
        <p className="text-base font-semibold text-rose-700" data-testid="accept-error">{error}</p>
      </div>
    </div>
  );
  if (!data) return <div className="min-h-screen flex items-center justify-center text-sm text-slate-500">Loading contract…</div>;

  return (
    <div className="min-h-screen bg-slate-50 py-8 px-4" data-testid="public-accept-page">
      <div className="max-w-3xl mx-auto bg-white rounded-2xl border shadow-sm overflow-hidden">
        {/* Brand header */}
        <header className="px-6 py-4 border-b flex items-center justify-between"
                style={{ background: 'linear-gradient(135deg, #0055FF, #003db8)' }}>
          <div>
            <p className="text-[10px] uppercase tracking-widest text-white/70 font-bold">Service Contract</p>
            <h1 className="text-lg font-extrabold text-white">{data.title}</h1>
            <p className="text-[11px] text-white/80">{data.contract_number} · {data.organization.name}</p>
          </div>
          <span className="text-[10px] uppercase font-extrabold px-2.5 py-1 rounded-full bg-white/15 text-white">{data.tier}</span>
        </header>
        <section className="px-6 py-5 space-y-5">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
            <Stat label="Customer"  value={data.company_name || '—'} />
            <Stat label="Site"      value={data.site_name || 'All sites'} />
            <Stat label="Starts"    value={fmtDate(data.start_date)} />
            <Stat label="Ends"      value={fmtDate(data.end_date)} />
          </div>
          {data.pricing?.annual_value > 0 && (
            <div className="rounded-xl border bg-emerald-50 p-3" data-testid="accept-pricing">
              <p className="text-[10px] uppercase text-emerald-700 font-bold tracking-wider">Annual value</p>
              <p className="text-2xl font-extrabold text-emerald-900">£{data.pricing.annual_value.toLocaleString('en-GB')}</p>
              <p className="text-[11px] text-emerald-700/80">Billed {data.billing_frequency || 'annually'} · VAT {data.pricing.vat_percent}%</p>
            </div>
          )}
          <div>
            <p className="text-[10px] uppercase tracking-wider font-bold text-slate-500 mb-1.5">Inclusions</p>
            <CoverSummary inclusions={data.inclusions || {}} />
          </div>
          {(data.exclusions_structured || []).length > 0 && (
            <div data-testid="accept-exclusions">
              <p className="text-[10px] uppercase tracking-wider font-bold text-rose-700 mb-1.5">Exclusions</p>
              <p className="text-xs text-rose-800/90">{data.exclusions_structured.join(' · ')}</p>
            </div>
          )}
          {data.terms_md && (
            <details className="rounded border" data-testid="accept-terms">
              <summary className="px-3 py-2 text-xs font-bold uppercase tracking-wider text-slate-500 cursor-pointer">Terms & Conditions</summary>
              <pre className="px-3 py-2 text-[11px] whitespace-pre-wrap text-slate-700 font-sans">{data.terms_md}</pre>
            </details>
          )}
        </section>
        {/* Sign block */}
        <section className="px-6 py-5 border-t bg-slate-50/60">
          {signed ? (
            <div className="text-center py-4" data-testid="accept-signed-confirmation">
              <CheckCircle size={32} className="mx-auto text-emerald-500 mb-2" />
              <p className="text-base font-bold text-emerald-900">Contract accepted</p>
              <p className="text-xs text-slate-500 mt-1">Signed by {data.signed_by || signerName}</p>
              <p className="text-[10px] text-slate-400 mt-1 flex items-center justify-center gap-1">
                <Calendar size={10} /> {fmtDate(data.signed_at || new Date().toISOString())}
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              <p className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                <ShieldCheck size={12} /> Sign & accept
              </p>
              <input value={signerName} onChange={e => setSignerName(e.target.value)}
                     placeholder="Your full legal name"
                     data-testid="accept-signer-name"
                     className="w-full px-3 py-2 rounded border text-sm" />
              <canvas ref={canvasRef} data-testid="accept-canvas"
                      className="w-full rounded border bg-white cursor-crosshair touch-none"
                      style={{ height: 150 }}
                      onMouseDown={start} onMouseMove={move} onMouseUp={end} onMouseLeave={end}
                      onTouchStart={start} onTouchMove={move} onTouchEnd={end} />
              <button onClick={submit} disabled={signing || !signerName.trim()}
                      data-testid="accept-sign-btn"
                      className="w-full py-2 rounded-md bg-emerald-600 text-white text-sm font-bold disabled:opacity-50">
                {signing ? 'Signing…' : 'Accept & sign contract'}
              </button>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div>
      <p className="text-[9px] uppercase tracking-wider font-bold text-slate-400">{label}</p>
      <p className="font-semibold text-slate-800 text-sm">{value}</p>
    </div>
  );
}
Stat.displayName = 'Stat';

function CoverSummary({ inclusions }) {
  const entries = Object.entries(inclusions || {}).filter(([, v]) => (v || []).length);
  if (!entries.length) return <p className="text-xs text-slate-400 italic">No structured inclusions configured.</p>;
  return (
    <div className="space-y-1">
      {entries.map(([groupKey, items]) => (
        <div key={groupKey} className="text-xs" data-testid={`accept-inc-${groupKey}`}>
          <p className="font-semibold text-slate-700 capitalize">{groupKey.replace(/_/g, ' ')}</p>
          <p className="text-slate-500">{items.join(' · ')}</p>
        </div>
      ))}
    </div>
  );
}
CoverSummary.displayName = 'CoverSummary';
