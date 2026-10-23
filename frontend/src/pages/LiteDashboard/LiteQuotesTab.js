/**
 * LiteQuotesTab — MOD in-portal Quotes.
 *
 * Site owners/managers review quotes raised for their site by Pulse Fitness
 * and e-sign them here (no separate public link / login). Signing a Type A
 * quote activates its service contract.
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import { FileText, Loader2, PenLine, CheckCircle2, ChevronLeft, RotateCcw, ShieldCheck } from 'lucide-react';
import { notify } from '@/components/notifications';

const money = (n, cur = 'GBP') => new Intl.NumberFormat('en-GB', { style: 'currency', currency: cur }).format(Number(n) || 0);

function StatusPill({ q }) {
  const signed = q.esign_status === 'signed' || q.status === 'accepted';
  const sent = q.esign_status === 'sent';
  const cfg = signed
    ? { t: 'Signed', c: 'bg-emerald-50 text-emerald-700 border-emerald-200' }
    : sent ? { t: 'Awaiting signature', c: 'bg-amber-50 text-amber-700 border-amber-200' }
    : { t: 'Draft', c: 'bg-slate-100 text-slate-500 border-slate-200' };
  return <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${cfg.c}`}>{cfg.t}</span>;
}

function SignPad({ onChange }) {
  const ref = useRef(null); const drawing = useRef(false); const has = useRef(false);
  const pos = (e) => { const r = ref.current.getBoundingClientRect(); const t = e.touches ? e.touches[0] : e; return { x: t.clientX - r.left, y: t.clientY - r.top }; };
  const start = (e) => { e.preventDefault(); drawing.current = true; const c = ref.current.getContext('2d'); const p = pos(e); c.beginPath(); c.moveTo(p.x, p.y); };
  const move = (e) => { if (!drawing.current) return; e.preventDefault(); const c = ref.current.getContext('2d'); const p = pos(e); c.lineWidth = 2.2; c.lineCap = 'round'; c.strokeStyle = '#0F172A'; c.lineTo(p.x, p.y); c.stroke(); has.current = true; };
  const end = () => { if (!drawing.current) return; drawing.current = false; if (has.current) onChange(ref.current.toDataURL('image/png')); };
  const clear = () => { const c = ref.current; c.getContext('2d').clearRect(0, 0, c.width, c.height); has.current = false; onChange(''); };
  useEffect(() => { const c = ref.current; c.width = c.offsetWidth; c.height = 160; }, []);
  return (
    <div>
      <canvas ref={ref} data-testid="lite-esign-pad"
        onMouseDown={start} onMouseMove={move} onMouseUp={end} onMouseLeave={end}
        onTouchStart={start} onTouchMove={move} onTouchEnd={end}
        style={{ width: '100%', height: 160, background: '#fff', border: '1px dashed #CBD5E1', borderRadius: 10, touchAction: 'none', cursor: 'crosshair' }} />
      <button type="button" onClick={clear} className="mt-2 text-xs text-slate-500 hover:text-slate-700 inline-flex items-center gap-1" data-testid="lite-esign-clear">
        <RotateCcw size={12} /> Clear signature
      </button>
    </div>
  );
}

export default function LiteQuotesTab({ API, headers, onChanged }) {
  const [list, setList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [active, setActive] = useState(null);
  const [sig, setSig] = useState('');
  const [name, setName] = useState('');
  const [agree, setAgree] = useState(false);
  const [signing, setSigning] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/mod/site/quotes`, { headers });
      setList(r.data.quotes || []);
    } catch { notify.error('Could not load quotes'); }
    setLoading(false);
  }, [API]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [load]);

  const openDetail = async (id) => {
    try {
      const r = await axios.get(`${API}/mod/site/quotes/${id}`, { headers });
      setActive(r.data); setSig(''); setName(''); setAgree(false);
    } catch { notify.error('Could not open quote'); }
  };

  const sign = async () => {
    if (!sig || !name.trim() || !agree) return;
    setSigning(true);
    try {
      await axios.post(`${API}/mod/site/quotes/${active.id}/sign`, { signature: sig, signer_name: name.trim() }, { headers });
      const r = await axios.get(`${API}/mod/site/quotes/${active.id}`, { headers });
      setActive(r.data); await load(); onChanged && onChanged();
      notify.success('Quote accepted & signed');
    } catch (e) { notify.error(e.response?.data?.detail || 'Could not sign the quote — please try again'); }
    setSigning(false);
  };

  const alreadySigned = active && (active.esign_status === 'signed' || active.status === 'accepted');

  if (loading) return <div className="py-16 flex justify-center"><Loader2 className="animate-spin text-slate-400" size={26} /></div>;

  // ── LIST ──
  if (!active) {
    return (
      <div data-testid="lite-quotes-list">
        {list.length === 0 ? (
          <div className="rounded-2xl border py-16 px-6 text-center" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }} data-testid="lite-quotes-empty">
            <FileText size={30} className="mx-auto text-slate-300" />
            <p className="mt-3 font-semibold" style={{ color: 'var(--theme-text)' }}>No quotes yet</p>
            <p className="text-sm mt-1" style={{ color: 'var(--theme-text-muted)' }}>When Pulse Fitness sends you a quote, it will appear here to review and sign — no extra login needed.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {list.map(q => (
              <button key={q.id} onClick={() => openDetail(q.id)} data-testid={`lite-quote-row-${q.id}`}
                className="w-full text-left rounded-2xl border p-4 flex items-center justify-between transition-shadow hover:shadow-md"
                style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }}>
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-bold" style={{ color: 'var(--theme-text)' }}>{q.quote_number}</span>
                    {q.mod_contract_type && <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-sky-50 text-sky-700 border border-sky-200">Type {q.mod_contract_type}</span>}
                    <StatusPill q={q} />
                  </div>
                  <p className="text-xs mt-1" style={{ color: 'var(--theme-text-muted)' }}>{q.title} · {q.line_count} line(s){q.valid_until ? ` · valid to ${q.valid_until}` : ''}</p>
                </div>
                <div className="text-right pl-3">
                  <div className="font-extrabold" style={{ color: 'var(--theme-text)' }}>{money(q.total, q.currency)}</div>
                  <div className="text-[11px] font-semibold" style={{ color: 'var(--color-brand-cyan, #0055FF)' }}>Review →</div>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }

  // ── DETAIL ──
  return (
    <div data-testid="lite-quote-detail">
      <button onClick={() => setActive(null)} className="inline-flex items-center gap-1 text-sm mb-4" style={{ color: 'var(--theme-text-muted)' }} data-testid="lite-quote-back">
        <ChevronLeft size={16} /> All quotes
      </button>
      <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-extrabold" style={{ color: 'var(--theme-text)' }}>{active.quote_number}</h2>
            {active.mod_contract_type && <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-sky-50 text-sky-700 border border-sky-200">MOD Type {active.mod_contract_type}</span>}
          </div>
          <p className="text-sm" style={{ color: 'var(--theme-text-muted)' }}>{active.title}</p>
        </div>
        <a href={`${API}/mod/site/quotes/${active.id}/pdf`} target="_blank" rel="noreferrer" className="text-sm inline-flex items-center gap-1 font-semibold" style={{ color: 'var(--color-brand-cyan, #0055FF)' }} data-testid="lite-quote-pdf">
          <FileText size={15} /> View PDF
        </a>
      </div>

      <div className="rounded-2xl border overflow-hidden mb-4" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }}>
        <table className="w-full text-sm">
          <thead><tr className="text-left" style={{ background: 'var(--theme-surface-alt, #F8FAFC)', color: 'var(--theme-text-muted)' }}>
            <th className="py-2.5 px-4 text-xs">Description</th><th className="w-14 text-center text-xs">Qty</th><th className="w-28 text-right px-4 text-xs">Amount</th>
          </tr></thead>
          <tbody>
            {(active.lines || []).map((l, i) => (
              <tr key={i} className="border-t" style={{ borderColor: 'var(--theme-border)' }}>
                <td className="py-2.5 px-4" style={{ color: 'var(--theme-text)' }}>{l.description || l.product_name}</td>
                <td className="py-2.5 text-center" style={{ color: 'var(--theme-text-muted)' }}>{l.quantity}</td>
                <td className="py-2.5 px-4 text-right" style={{ color: 'var(--theme-text)' }}>{money((Number(l.unit_price) || 0) * (Number(l.quantity) || 1), active.currency)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="px-4 py-3 border-t" style={{ borderColor: 'var(--theme-border)' }}>
          <Row label="Net" val={money(active.subtotal, active.currency)} />
          <Row label={`VAT (${active.vat_rate ?? 20}%)`} val={money(active.vat_amount, active.currency)} />
          <Row label="Total" val={money(active.total, active.currency)} bold />
        </div>
      </div>
      {active.notes && <p className="text-sm mb-4" style={{ color: 'var(--theme-text-muted)' }}>{active.notes}</p>}

      {alreadySigned ? (
        <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-6 text-center" data-testid="lite-quote-signed">
          <CheckCircle2 className="text-emerald-600 mx-auto" size={34} />
          <p className="font-bold mt-2 text-emerald-900">Accepted &amp; signed</p>
          <p className="text-sm text-emerald-700 mt-0.5">Signed by {active.signer_name}{active.signed_at ? ` on ${new Date(active.signed_at).toLocaleDateString('en-GB')}` : ''}.{active.mod_contract_type === 'A' ? ' Your service contract is now active.' : ''}</p>
        </div>
      ) : (
        <div className="rounded-2xl border p-5" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }}>
          <p className="font-bold flex items-center gap-2 mb-3" style={{ color: 'var(--theme-text)' }}><PenLine size={16} style={{ color: 'var(--color-brand-cyan, #0055FF)' }} /> Accept &amp; sign this quote</p>
          <label className="block text-xs font-semibold mb-1" style={{ color: 'var(--theme-text-muted)' }}>Your full name</label>
          <input value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Maj. A. Smith" data-testid="lite-esign-name"
            className="w-full px-3 py-2 rounded-lg border text-sm mb-3" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-bg, #fff)', color: 'var(--theme-text)' }} />
          <label className="block text-xs font-semibold mb-1" style={{ color: 'var(--theme-text-muted)' }}>Signature</label>
          <SignPad onChange={setSig} />
          <label className="flex items-start gap-2 mt-3 text-sm" style={{ color: 'var(--theme-text-muted)' }}>
            <input type="checkbox" checked={agree} onChange={e => setAgree(e.target.checked)} data-testid="lite-esign-agree" className="mt-1" />
            I confirm I'm authorised to accept this quote on behalf of my site{active.mod_contract_type === 'A' ? ' and activate the service contract' : ''}.
          </label>
          <button onClick={sign} disabled={!sig || !name.trim() || !agree || signing} data-testid="lite-quote-sign-btn"
            className="mt-4 w-full py-3 rounded-xl font-extrabold text-white flex items-center justify-center gap-2 disabled:opacity-40"
            style={{ background: (!sig || !name.trim() || !agree) ? '#94A3B8' : '#0055FF' }}>
            {signing ? <Loader2 size={16} className="animate-spin" /> : <ShieldCheck size={16} />} Accept &amp; Sign
          </button>
        </div>
      )}
    </div>
  );
}

function Row({ label, val, bold }) {
  return (
    <div className="flex justify-between py-0.5">
      <span className={bold ? 'font-bold' : ''} style={{ color: bold ? 'var(--theme-text)' : 'var(--theme-text-muted)', fontSize: bold ? 15 : 13 }}>{label}</span>
      <span className="font-bold" style={{ color: bold ? '#059669' : 'var(--theme-text)', fontSize: bold ? 16 : 13 }}>{val}</span>
    </div>
  );
}
