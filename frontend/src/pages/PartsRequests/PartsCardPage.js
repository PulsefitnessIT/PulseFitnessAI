/**
 * Public Supplier Parts Card — /parts-card/:token
 *
 * Token-authenticated (no login). The supplier reviews the requested
 * parts + machine cover, then acknowledges, quotes, invoices, allocates
 * and despatches. Every action lands on the operator's request timeline.
 */
import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import {
  Package, Loader2, CheckCircle2, FileText, Truck, ShieldCheck, ShieldAlert, Send,
} from 'lucide-react';

const BACKEND = process.env.REACT_APP_BACKEND_URL || '';
const API = BACKEND ? `${BACKEND}/api` : '/api';

const STEPS = ['acknowledged', 'quoted', 'invoiced', 'allocated', 'despatched', 'completed'];
const STEP_LABEL = {
  submitted: 'Received', acknowledged: 'Acknowledged', quoted: 'Quoted',
  invoiced: 'Invoiced', allocated: 'Allocated', despatched: 'Despatched', completed: 'Completed',
};

function Cover({ m }) {
  if (m.coverage_status === 'covered_contract') return <span className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700"><ShieldCheck size={12} /> Contract</span>;
  if (m.coverage_status === 'covered_warranty') return <span className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full bg-blue-100 text-blue-700"><ShieldCheck size={12} /> Warranty</span>;
  return <span className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full bg-amber-100 text-amber-800"><ShieldAlert size={12} /> Chargeable</span>;
}

export default function PartsCardPage() {
  const { token } = useParams();
  const [card, setCard] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ amount: '', invoice_number: '', carrier: '', tracking: '', note: '' });

  const load = useCallback(async () => {
    try { const { data } = await axios.get(`${API}/parts-card/${token}`); setCard(data); }
    catch (e) { setErr(e?.response?.data?.detail || 'This link is invalid or has expired.'); }
  }, [token]);
  useEffect(() => { load(); }, [load]);

  const doAction = async (action, extra = {}) => {
    setBusy(true);
    try {
      await axios.post(`${API}/parts-card/${token}/update`, { action, note: form.note, ...extra });
      toast.success('Updated');
      setForm({ amount: '', invoice_number: '', carrier: '', tracking: '', note: '' });
      await load();
    } catch (e) { toast.error(e?.response?.data?.detail || 'Update failed'); }
    finally { setBusy(false); }
  };

  if (err) return <div className="min-h-screen flex items-center justify-center bg-slate-50 pulse-font"><div className="text-center"><Package className="mx-auto text-slate-300 mb-2" size={40} /><p className="text-slate-600">{err}</p></div></div>;
  if (!card) return <div className="min-h-screen flex items-center justify-center bg-slate-50"><Loader2 className="animate-spin text-slate-400" /></div>;

  const status = card.status;
  const stepIdx = STEPS.indexOf(status);

  return (
    <div className="min-h-screen bg-slate-50 pulse-font" data-testid="parts-card-page">
      <div className="bg-slate-900 text-white px-4 py-5">
        <div className="max-w-3xl mx-auto">
          <p className="text-xs text-slate-300">Parts Request · via Pulse Fitness</p>
          <h1 className="text-2xl font-bold">{card.reference}</h1>
          <p className="text-sm text-slate-300">from {card.organization_name}</p>
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-4 py-6 space-y-5">
        {/* Progress */}
        <div className="rounded-xl border bg-white p-4">
          <div className="flex flex-wrap gap-2" data-testid="card-progress">
            {STEPS.map((s, i) => (
              <span key={s} className={`text-xs font-semibold px-2.5 py-1 rounded-full ${i <= stepIdx && stepIdx >= 0 ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-400'}`}>{STEP_LABEL[s]}</span>
            ))}
          </div>
        </div>

        {/* Machines */}
        {(card.machines || []).map((m, mi) => (
          <div key={mi} className="rounded-xl border bg-white p-4" data-testid={`card-machine-${mi}`}>
            <div className="flex items-center justify-between">
              <p className="font-semibold text-slate-900">{m.machine_name || m.equipment_type} <span className="text-slate-400 font-normal text-sm">· {m.serial_number || '—'}</span></p>
              <Cover m={m} />
            </div>
            <p className="text-xs text-slate-500">{m.manufacturer} {m.model}</p>
            <ul className="mt-2 text-sm text-slate-700 list-disc pl-5">
              {(m.parts || []).map((p, pi) => <li key={pi}>{p.qty}× {p.part_name || '—'}{p.part_number ? ` (${p.part_number})` : ''}{p.notes ? ` — ${p.notes}` : ''}</li>)}
              {(m.parts || []).length === 0 && <li className="list-none text-slate-400">No specific parts listed</li>}
            </ul>
          </div>
        ))}

        {/* Photos */}
        {card.attachments?.length > 0 && (
          <div className="rounded-xl border bg-white p-4">
            <p className="text-sm font-semibold text-slate-700 mb-2">Photos</p>
            <div className="flex flex-wrap gap-2">
              {card.attachments.map((a) => (
                <a key={a.id} href={`${BACKEND}${a.url}`} target="_blank" rel="noreferrer" data-testid={`card-photo-${a.id}`}>
                  <img src={`${BACKEND}${a.url}`} alt={a.original_filename} className="h-24 w-24 object-cover rounded-lg border" />
                </a>
              ))}
            </div>
          </div>
        )}

        {card.notes && <div className="rounded-xl border bg-white p-4 text-sm text-slate-700"><span className="font-semibold">Notes:</span> {card.notes}</div>}

        {/* Supplier actions */}
        {status !== 'cancelled' && (
          <div className="rounded-xl border bg-white p-4 space-y-3" data-testid="card-actions">
            <p className="text-sm font-semibold text-slate-700">Update this request</p>
            <textarea value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} rows={2} placeholder="Add a note (optional)" className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm" data-testid="card-note" />

            <div className="flex flex-wrap gap-2">
              <button onClick={() => doAction('acknowledge')} disabled={busy} className="px-3 py-1.5 rounded-lg bg-slate-900 text-white text-sm font-medium inline-flex items-center gap-1" data-testid="card-acknowledge"><CheckCircle2 size={14} /> Acknowledge</button>
              <button onClick={() => doAction('allocate')} disabled={busy} className="px-3 py-1.5 rounded-lg border text-sm font-medium text-slate-700 inline-flex items-center gap-1" data-testid="card-allocate"><Package size={14} /> Allocate parts</button>
              <button onClick={() => doAction('complete')} disabled={busy} className="px-3 py-1.5 rounded-lg bg-emerald-600 text-white text-sm font-medium inline-flex items-center gap-1" data-testid="card-complete"><CheckCircle2 size={14} /> Mark complete</button>
            </div>

            {/* Quote / Invoice */}
            <div className="grid sm:grid-cols-2 gap-3 pt-2 border-t">
              <div>
                <label className="text-xs font-semibold text-slate-600">Quote / Invoice amount (£)</label>
                <input value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} type="number" className="w-full mt-1 px-3 py-2 border border-slate-300 rounded-lg text-sm" data-testid="card-amount" />
                <div className="flex gap-2 mt-2">
                  <button onClick={() => doAction('quote', { amount: parseFloat(form.amount) || 0 })} disabled={busy} className="flex-1 px-3 py-1.5 rounded-lg bg-amber-500 text-white text-sm font-medium inline-flex items-center justify-center gap-1" data-testid="card-quote"><FileText size={14} /> Send quote</button>
                  <button onClick={() => doAction('invoice', { amount: parseFloat(form.amount) || 0, invoice_number: form.invoice_number })} disabled={busy} className="flex-1 px-3 py-1.5 rounded-lg bg-purple-600 text-white text-sm font-medium inline-flex items-center justify-center gap-1" data-testid="card-invoice"><FileText size={14} /> Send invoice</button>
                </div>
                <input value={form.invoice_number} onChange={(e) => setForm({ ...form, invoice_number: e.target.value })} placeholder="Invoice number" className="w-full mt-2 px-3 py-2 border border-slate-300 rounded-lg text-sm" data-testid="card-invoice-number" />
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-600">Despatch</label>
                <input value={form.carrier} onChange={(e) => setForm({ ...form, carrier: e.target.value })} placeholder="Carrier" className="w-full mt-1 px-3 py-2 border border-slate-300 rounded-lg text-sm" data-testid="card-carrier" />
                <input value={form.tracking} onChange={(e) => setForm({ ...form, tracking: e.target.value })} placeholder="Tracking number" className="w-full mt-2 px-3 py-2 border border-slate-300 rounded-lg text-sm" data-testid="card-tracking" />
                <button onClick={() => doAction('despatch', { carrier: form.carrier, tracking: form.tracking })} disabled={busy} className="w-full mt-2 px-3 py-1.5 rounded-lg bg-teal-600 text-white text-sm font-medium inline-flex items-center justify-center gap-1" data-testid="card-despatch"><Truck size={14} /> Mark despatched</button>
              </div>
            </div>
          </div>
        )}

        {/* Timeline */}
        <div className="rounded-xl border bg-white p-4">
          <p className="text-sm font-semibold text-slate-700 mb-3">History</p>
          <div className="space-y-2">
            {(card.events || []).map((e) => (
              <div key={e.id} className="text-sm text-slate-700" data-testid={`card-event-${e.action}`}>
                <span className="font-medium">{e.actor}</span> <span className="text-slate-400">({e.actor_role})</span> — {e.note || e.action}
                <span className="text-xs text-slate-400 ml-1">{new Date(e.at).toLocaleString('en-GB')}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
