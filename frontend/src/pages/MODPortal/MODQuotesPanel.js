/**
 * MOD Portal — Quotes panel.
 *
 * Lets a MOD site owner/manager review quotes raised for their site and
 * e-sign them in-portal (no separate public link / login). Signing a Type A
 * quote activates its service contract.
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import { X, FileText, Loader2, PenLine, CheckCircle2, ChevronLeft, RotateCcw, ShieldCheck } from 'lucide-react';
import { notify } from '@/components/notifications';

const money = (n, cur = 'GBP') => new Intl.NumberFormat('en-GB', { style: 'currency', currency: cur }).format(Number(n) || 0);

function StatusPill({ q }) {
  const signed = q.esign_status === 'signed' || q.status === 'accepted';
  const sent = q.esign_status === 'sent';
  const cfg = signed
    ? { t: 'Signed', c: 'bg-emerald-500/20 text-emerald-200 border-emerald-500/40' }
    : sent ? { t: 'Awaiting signature', c: 'bg-amber-500/20 text-amber-200 border-amber-500/40' }
    : { t: 'Draft', c: 'bg-white/10 text-white/60 border-white/15' };
  return <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${cfg.c}`}>{cfg.t}</span>;
}

function SignPad({ onChange }) {
  const ref = useRef(null); const drawing = useRef(false); const has = useRef(false);
  const pos = (e) => { const r = ref.current.getBoundingClientRect(); const t = e.touches ? e.touches[0] : e; return { x: t.clientX - r.left, y: t.clientY - r.top }; };
  const start = (e) => { e.preventDefault(); drawing.current = true; const c = ref.current.getContext('2d'); const p = pos(e); c.beginPath(); c.moveTo(p.x, p.y); };
  const move = (e) => { if (!drawing.current) return; e.preventDefault(); const c = ref.current.getContext('2d'); const p = pos(e); c.lineWidth = 2.2; c.lineCap = 'round'; c.strokeStyle = '#0F172A'; c.lineTo(p.x, p.y); c.stroke(); has.current = true; };
  const end = () => { if (!drawing.current) return; drawing.current = false; if (has.current) onChange(ref.current.toDataURL('image/png')); };
  const clear = () => { const c = ref.current; c.getContext('2d').clearRect(0, 0, c.width, c.height); has.current = false; onChange(''); };
  useEffect(() => { const c = ref.current; c.width = c.offsetWidth; c.height = 150; }, []);
  return (
    <div>
      <canvas ref={ref} data-testid="mod-esign-pad"
        onMouseDown={start} onMouseMove={move} onMouseUp={end} onMouseLeave={end}
        onTouchStart={start} onTouchMove={move} onTouchEnd={end}
        style={{ width: '100%', height: 150, background: '#fff', border: '1px dashed #94A3B8', borderRadius: 8, touchAction: 'none', cursor: 'crosshair' }} />
      <button type="button" onClick={clear} className="mt-1.5 text-[11px] text-white/50 hover:text-white/80 inline-flex items-center gap-1" data-testid="mod-esign-clear">
        <RotateCcw size={11} /> Clear
      </button>
    </div>
  );
}

export default function MODQuotesPanel({ API, onClose, onSigned }) {
  const [list, setList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [active, setActive] = useState(null); // detail quote
  const [sig, setSig] = useState('');
  const [signing, setSigning] = useState(false);
  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/mod/site/quotes`, { headers });
      setList(r.data.quotes || []);
    } catch (e) { notify.error('Could not load quotes'); }
    setLoading(false);
  }, [API]);
  useEffect(() => { load(); }, [load]);

  const openDetail = async (id) => {
    try {
      const r = await axios.get(`${API}/mod/site/quotes/${id}`, { headers });
      setActive(r.data); setSig('');
    } catch (e) { notify.error('Could not open quote'); }
  };

  const sign = async () => {
    if (!sig) return;
    setSigning(true);
    try {
      await axios.post(`${API}/mod/site/quotes/${active.id}/sign`, { signature: sig }, { headers });
      notify.success('Quote accepted & signed');
      setActive(null); await load(); onSigned && onSigned();
    } catch (e) { notify.error(e.response?.data?.detail || 'Could not sign'); }
    setSigning(false);
  };

  const alreadySigned = active && (active.esign_status === 'signed' || active.status === 'accepted');

  return (
    <div className="fixed inset-0 z-[95] flex items-center justify-center bg-black/70 backdrop-blur-sm p-4" onClick={onClose}>
      <div className="w-full max-w-2xl rounded-2xl border border-white/10 bg-[#0B1220] max-h-[90vh] overflow-hidden flex flex-col"
        onClick={e => e.stopPropagation()} data-testid="mod-quotes-panel">
        {/* header */}
        <div className="px-5 py-4 border-b border-white/10 flex items-center justify-between">
          <div className="flex items-center gap-2">
            {active && <button onClick={() => setActive(null)} className="text-white/60 hover:text-white" data-testid="mod-quotes-back"><ChevronLeft size={18} /></button>}
            <FileText size={18} className="text-sky-300" />
            <div>
              <h2 className="text-white text-base font-extrabold">{active ? active.quote_number : 'Quotes'}</h2>
              <p className="text-[11px] text-white/50">{active ? (active.title || '') : 'Review & sign quotes for your site'}</p>
            </div>
          </div>
          <button onClick={onClose} className="text-white/60 hover:text-white" data-testid="mod-quotes-close"><X size={18} /></button>
        </div>

        <div className="overflow-y-auto p-5">
          {/* LIST */}
          {!active && (loading ? (
            <div className="py-12 flex justify-center"><Loader2 className="animate-spin text-white/50" size={24} /></div>
          ) : list.length === 0 ? (
            <div className="py-12 text-center text-white/50 text-sm" data-testid="mod-quotes-empty">No quotes yet. When Pulse Fitness sends you a quote it will appear here to review and sign.</div>
          ) : (
            <div className="space-y-2">
              {list.map(q => (
                <button key={q.id} onClick={() => openDetail(q.id)} data-testid={`mod-quote-row-${q.id}`}
                  className="w-full text-left rounded-xl border border-white/10 bg-white/5 hover:bg-white/10 p-3.5 flex items-center justify-between transition-colors">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-white font-bold text-sm">{q.quote_number}</span>
                      {q.mod_contract_type && <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-sky-500/20 text-sky-200 border border-sky-500/30">Type {q.mod_contract_type}</span>}
                      <StatusPill q={q} />
                    </div>
                    <p className="text-white/50 text-[11px] mt-1">{q.title} · {q.line_count} line(s){q.valid_until ? ` · valid to ${q.valid_until}` : ''}</p>
                  </div>
                  <div className="text-right">
                    <div className="text-white font-extrabold">{money(q.total, q.currency)}</div>
                    <div className="text-[10px] text-sky-300 font-semibold">Review →</div>
                  </div>
                </button>
              ))}
            </div>
          ))}

          {/* DETAIL */}
          {active && (
            <div>
              <div className="rounded-xl border border-white/10 overflow-hidden mb-4">
                <table className="w-full text-sm">
                  <thead><tr className="bg-white/5 text-white/50 text-[11px] text-left">
                    <th className="py-2 px-3">Description</th><th className="w-12 text-center">Qty</th><th className="w-24 text-right px-3">Amount</th>
                  </tr></thead>
                  <tbody>
                    {(active.lines || []).map((l, i) => (
                      <tr key={i} className="border-t border-white/5">
                        <td className="py-2 px-3 text-white/90">{l.description || l.product_name}</td>
                        <td className="py-2 text-center text-white/60">{l.quantity}</td>
                        <td className="py-2 px-3 text-right text-white/90">{money((Number(l.unit_price) || 0) * (Number(l.quantity) || 1), active.currency)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="px-3 py-3 border-t border-white/10 bg-white/[0.03] text-sm">
                  <Row label="Net" val={money(active.subtotal, active.currency)} />
                  <Row label={`VAT (${active.vat_rate ?? 20}%)`} val={money(active.vat_amount, active.currency)} />
                  <Row label="Total" val={money(active.total, active.currency)} bold />
                </div>
              </div>
              <a href={`${API}/mod/site/quotes/${active.id}/pdf`} target="_blank" rel="noreferrer" className="text-[12px] text-sky-300 inline-flex items-center gap-1 mb-4" data-testid="mod-quote-pdf">
                <FileText size={13} /> View PDF
              </a>
              {active.notes && <p className="text-white/50 text-xs mb-4">{active.notes}</p>}

              {alreadySigned ? (
                <div className="rounded-xl border border-emerald-500/40 bg-emerald-500/10 p-4 text-center" data-testid="mod-quote-signed">
                  <CheckCircle2 className="text-emerald-300 mx-auto" size={30} />
                  <p className="text-white font-bold mt-2">Accepted</p>
                  <p className="text-white/60 text-xs mt-0.5">Signed by {active.signer_name}{active.signed_at ? ` on ${new Date(active.signed_at).toLocaleDateString('en-GB')}` : ''}.</p>
                </div>
              ) : (
                <div className="rounded-xl border border-white/10 bg-white/5 p-4">
                  <p className="text-white font-bold text-sm flex items-center gap-2 mb-3"><PenLine size={15} className="text-sky-300" /> Accept &amp; sign</p>
                  <SignPad onChange={setSig} />
                  <button onClick={sign} disabled={!sig || signing} data-testid="mod-quote-sign-btn"
                    className="mt-4 w-full py-3 rounded-xl font-extrabold text-white flex items-center justify-center gap-2 disabled:opacity-40"
                    style={{ background: sig ? '#0055FF' : '#334155' }}>
                    {signing ? <Loader2 size={16} className="animate-spin" /> : <ShieldCheck size={16} />} Accept &amp; Sign
                  </button>
                  <p className="text-white/40 text-[11px] mt-2 text-center">By signing you accept this quote on behalf of your site{active.mod_contract_type === 'A' ? ' and activate the service contract' : ''}.</p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Row({ label, val, bold }) {
  return (
    <div className="flex justify-between py-0.5">
      <span className={bold ? 'text-white font-bold' : 'text-white/50'}>{label}</span>
      <span className={bold ? 'text-emerald-300 font-extrabold text-base' : 'text-white/80'}>{val}</span>
    </div>
  );
}
