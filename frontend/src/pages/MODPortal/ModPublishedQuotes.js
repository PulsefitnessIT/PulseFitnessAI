import { useState } from 'react';
import axios from 'axios';
import { Download, Archive, CheckCircle2, Eye, Send } from 'lucide-react';
import { notify } from '@/components/notifications';

const money = (n) => new Intl.NumberFormat('en-GB', { style: 'currency', currency: 'GBP' }).format(Number(n) || 0);
const TYPE = { A: ['Type A', 'Fully inclusive maintenance for 12 months'], B: ['Type B', 'One-off service or repair visit'], AB: ['Type A/B Mix', 'Cardio fully inclusive, strength one-off (as listed)'] };
const STATUS = {
  published: 'Ready to review', customer_review: 'Being reviewed', authorisation_submitted: 'Authorisation sent to Pulse Fitness',
  accepted: 'Accepted', handed_over: 'Accepted', not_selected: 'Not selected',
};

async function save(API, headers, path, fallback) {
  const r = await axios.get(`${API}${path}`, { headers, responseType: 'blob' });
  const cd = r.headers['content-disposition'] || '';
  const name = (cd.match(/filename="([^"]+)"/) || [])[1] || fallback;
  const url = URL.createObjectURL(r.data);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

function AuthoriseForm({ API, headers, quote, onDone, onCancel }) {
  const [f, setF] = useState({ po_reference: '', authorising_officer: '', authorisation_date: new Date().toISOString().slice(0, 10), notes: '' });
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (!f.authorising_officer.trim()) { notify.error('Enter the authorising officer'); return; }
    setBusy(true);
    const fd = new FormData();
    Object.entries(f).forEach(([k, v]) => fd.append(k, v));
    if (file) fd.append('evidence', file);
    try {
      await axios.post(`${API}/mod/site/quotes/${quote.id}/authorise`, fd, { headers });
      notify.success('Authorisation sent to Pulse Fitness for checking');
      onDone();
    } catch (e) { notify.error(e.response?.data?.detail || 'Could not submit'); }
    setBusy(false);
  };
  const inp = 'mt-1 w-full rounded-lg bg-white/10 border border-white/15 px-3 py-2 text-sm text-white';
  return (
    <div className="rounded-xl border border-sky-400/30 bg-white/5 p-4 space-y-3" data-testid="mod-authorise-form">
      <div className="text-white font-bold text-sm">Submit authorisation — {TYPE[quote.mod_quote_type][0]} ({quote.quote_number})</div>
      <p className="text-[11px] text-white/60">Pulse Fitness checks your approval before the work is confirmed. Nothing is ordered until then.</p>
      <div className="grid sm:grid-cols-2 gap-3">
        <label className="text-[11px] text-white/60">Purchase order reference<input className={inp} value={f.po_reference} onChange={(e) => setF({ ...f, po_reference: e.target.value })} data-testid="mod-auth-po" /></label>
        <label className="text-[11px] text-white/60">Authorising officer *<input className={inp} value={f.authorising_officer} onChange={(e) => setF({ ...f, authorising_officer: e.target.value })} data-testid="mod-auth-officer" /></label>
        <label className="text-[11px] text-white/60">Authorisation date *<input type="date" className={inp} value={f.authorisation_date} onChange={(e) => setF({ ...f, authorisation_date: e.target.value })} data-testid="mod-auth-date" /></label>
        <label className="text-[11px] text-white/60">Approval document (optional)<input type="file" className="mt-1 text-xs text-white/70" onChange={(e) => setFile(e.target.files?.[0] || null)} data-testid="mod-auth-file" /></label>
      </div>
      <label className="block text-[11px] text-white/60">Notes<textarea rows={2} className={inp} value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} data-testid="mod-auth-notes" /></label>
      <div className="flex gap-2">
        <button type="button" disabled={busy} onClick={submit} className="inline-flex items-center gap-1.5 rounded-full bg-sky-400 text-black font-bold text-sm px-4 py-2 disabled:opacity-50" data-testid="mod-auth-submit"><Send size={14} /> Submit authorisation</button>
        <button type="button" onClick={onCancel} className="rounded-full border border-white/20 text-white/80 text-sm px-4 py-2" data-testid="mod-auth-cancel">Cancel</button>
      </div>
    </div>
  );
}

export default function ModPublishedQuotes({ API, groups, onChanged }) {
  const [auth, setAuth] = useState(null);
  const [open, setOpen] = useState(null);
  const headers = { Authorization: `Bearer ${localStorage.getItem('token')}` };
  const view = async (q) => {
    try {
      const r = await axios.get(`${API}/mod/site/quotes/${q.id}`, { headers });
      setOpen(r.data);
      if (q.status === 'published') axios.post(`${API}/mod/site/quotes/${q.id}/reviewing`, {}, { headers }).catch(() => {});
    } catch { notify.error('Could not open quotation'); }
  };
  if (!groups.length) return null;
  return (
    <div className="space-y-4 mb-5" data-testid="mod-published-quotes">
      {groups.map((g) => {
        const locked = ['authorisation_submitted', 'accepted', 'handed_over'].includes(g.status);
        return (
          <div key={g.id} className="rounded-xl border border-white/10 bg-white/5 p-4" data-testid={`mod-quote-group-${g.id}`}>
            <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
              <div>
                <div className="text-white font-bold text-sm">Maintenance quotations — compare your options</div>
                <div className="text-[11px] text-white/50">Downloading or viewing does not accept a quotation.</div>
              </div>
              <button type="button" onClick={() => save(API, headers, `/mod/site/quote-groups/${g.id}/zip`, 'Pulse-Fitness-Quotations.zip').catch(() => notify.error('Download failed'))}
                className="inline-flex items-center gap-1.5 rounded-full border border-white/20 text-white text-xs font-semibold px-3 py-1.5" data-testid="mod-quote-zip"><Archive size={13} /> Download all (ZIP)</button>
            </div>
            <div className="grid sm:grid-cols-3 gap-3">
              {g.quotes.map((q) => (
                <div key={q.id} className="rounded-lg border border-white/10 p-3 flex flex-col" data-testid={`mod-quote-option-${q.mod_quote_type}`}>
                  <div className="text-white font-bold text-sm">{TYPE[q.mod_quote_type]?.[0]}</div>
                  <div className="text-[11px] text-white/50 min-h-[30px]">{TYPE[q.mod_quote_type]?.[1]}</div>
                  <div className="mt-2 text-xs text-white/70 space-y-0.5">
                    <div className="flex justify-between"><span>Net</span><span>{money(q.subtotal)}</span></div>
                    <div className="flex justify-between"><span>VAT</span><span>{money(q.vat_amount)}</span></div>
                    <div className="flex justify-between text-white font-bold"><span>Total</span><span data-testid={`mod-quote-total-${q.mod_quote_type}`}>{money(q.total)}</span></div>
                  </div>
                  <div className="text-[10px] text-white/40 mt-1">{q.quote_number}{q.valid_until ? ` · valid until ${new Date(q.valid_until).toLocaleDateString('en-GB')}` : ''}</div>
                  <div className="text-[10px] text-sky-300 mt-1">{g.accepted_quote_id === q.id ? <span className="inline-flex items-center gap-1"><CheckCircle2 size={11} /> Selected option</span> : STATUS[q.status]}</div>
                  <div className="mt-auto pt-3 flex flex-wrap gap-1.5">
                    <button type="button" onClick={() => view(q)} className="inline-flex items-center gap-1 rounded-full border border-white/20 text-white text-[11px] px-2.5 py-1" data-testid={`mod-quote-view-${q.mod_quote_type}`}><Eye size={12} /> View</button>
                    <button type="button" onClick={() => save(API, headers, `/mod/site/quotes/${q.id}/pdf`, `${q.quote_number}.pdf`).catch(() => notify.error('Download failed'))}
                      className="inline-flex items-center gap-1 rounded-full border border-white/20 text-white text-[11px] px-2.5 py-1" data-testid={`mod-quote-pdf-${q.mod_quote_type}`}><Download size={12} /> PDF</button>
                    {!locked && <button type="button" onClick={() => setAuth(q)} className="inline-flex items-center gap-1 rounded-full bg-sky-400 text-black font-bold text-[11px] px-2.5 py-1" data-testid={`mod-quote-choose-${q.mod_quote_type}`}><Send size={12} /> Choose this option</button>}
                  </div>
                </div>
              ))}
            </div>
            {g.authorisation?.status === 'submitted' && <div className="mt-3 text-xs text-amber-200" data-testid="mod-auth-pending">Your authorisation has been sent — Pulse Fitness is checking it.</div>}
            {auth && g.quotes.some((q) => q.id === auth.id) && (
              <div className="mt-3"><AuthoriseForm API={API} headers={headers} quote={auth} onCancel={() => setAuth(null)} onDone={() => { setAuth(null); onChanged(); }} /></div>
            )}
            {open && g.quotes.some((q) => q.id === open.id) && (
              <div className="mt-3 rounded-lg border border-white/10 p-3 overflow-x-auto" data-testid="mod-quote-lines">
                <table className="w-full text-[11px] text-white/80">
                  <thead><tr className="text-white/50 text-left"><th>Item code</th><th>Description</th><th>Qty</th><th className="text-right">Unit</th><th className="text-right">Total</th></tr></thead>
                  <tbody>{open.lines.map((ln) => (
                    <tr key={ln.line_no} className="border-t border-white/10 align-top"><td className="pr-2 py-1 whitespace-nowrap">{ln.item_code}</td><td className="pr-2 py-1">{ln.description}</td><td>{ln.qty}</td><td className="text-right">{ln.unit_price.toFixed(2)}</td><td className="text-right">{ln.total.toFixed(2)}</td></tr>
                  ))}</tbody>
                </table>
                <button type="button" onClick={() => setOpen(null)} className="mt-2 text-[11px] text-white/60" data-testid="mod-quote-lines-close">Close</button>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
