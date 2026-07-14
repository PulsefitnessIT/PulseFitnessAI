import { useEffect, useState, useCallback, useRef } from 'react';
import { Wand2, Plus, Trash2, ChevronRight, ChevronLeft, CheckCircle2, AlertTriangle, PackageCheck, Building2, UploadCloud, Sparkles, FileText } from 'lucide-react';
import { notify } from '@/components/notifications';
import { dpApi } from './api';
import { Spinner, StatCard, input, money } from './shared';

const PRIORITY_TONE = {
  critical: 'bg-red-50 text-red-700 border-red-200',
  recommended: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  optional: 'bg-blue-50 text-blue-700 border-blue-200',
  low: 'bg-slate-100 text-slate-600 border-slate-200',
};

function StepDots({ step }) {
  const labels = ['Dealer & Invoice', 'Recommendation', 'Approve & Allocate'];
  return (
    <div className="flex items-center gap-2 mb-5">
      {labels.map((l, i) => (
        <div key={l} className="flex items-center gap-2">
          <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${step >= i ? 'bg-[var(--gx-brand-from)] text-white' : 'bg-slate-100 text-slate-400'}`}>{i + 1}</div>
          <span className={`text-sm font-medium ${step >= i ? 'text-slate-900' : 'text-slate-400'}`}>{l}</span>
          {i < labels.length - 1 && <ChevronRight size={15} className="text-slate-300" />}
        </div>
      ))}
    </div>
  );
}

export default function AllocationWizardTab() {
  const [step, setStep] = useState(0);
  const [dealers, setDealers] = useState([]);
  const [dealerId, setDealerId] = useState('');
  const [orderValue, setOrderValue] = useState('');
  const [pct, setPct] = useState('');
  const [lines, setLines] = useState([{ machine_ref: '', quantity: 1 }]);
  const [rec, setRec] = useState(null);
  const [busy, setBusy] = useState(false);
  const [qtyOverrides, setQtyOverrides] = useState({});
  const [aiBusy, setAiBusy] = useState(false);
  const [aiInfo, setAiInfo] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef(null);

  useEffect(() => { dpApi.listDealers().then((d) => setDealers(d.dealers || [])); }, []);

  const setLine = (i, k, v) => { const n = [...lines]; n[i][k] = v; setLines(n); };

  const parseInvoice = async (file) => {
    if (!file) return;
    setAiBusy(true); setAiInfo(null);
    try {
      const res = await dpApi.aiParseInvoiceFile(file);
      if (!res.available) { notify.error(res.error || 'AI could not read this invoice'); return; }
      const newLines = (res.lines || []).map((l) => ({
        machine_ref: l.top_level_ref || l.input_ref || '',
        quantity: l.quantity || 1,
        matched: l.matched,
        input_ref: l.input_ref,
      }));
      if (newLines.length) setLines(newLines);
      if (res.order_value) setOrderValue(String(res.order_value));
      setAiInfo({ ref: res.order_reference, currency: res.currency, matched: res.matched_count, total: res.lines?.length || 0, note: res.note });
      notify.success(`AI read the invoice — ${res.matched_count}/${res.lines?.length || 0} machines matched to BOM`);
    } catch (e) { notify.error(e?.response?.data?.detail || 'AI parsing failed'); }
    finally { setAiBusy(false); }
  };

  const generate = async () => {
    if (!dealerId) { notify.error('Select a dealer'); return; }
    const validLines = lines.filter((l) => l.machine_ref.trim());
    if (validLines.length === 0) { notify.error('Add at least one machine line'); return; }
    setBusy(true);
    try {
      const r = await dpApi.recommendFromInvoice({
        dealer_id: dealerId,
        order_value: Number(orderValue) || 0,
        spare_parts_percentage: pct === '' ? undefined : Number(pct),
        lines: validLines.map((l) => ({ machine_ref: l.machine_ref, quantity: Number(l.quantity) || 1 })),
      });
      setRec(r);
      setQtyOverrides({});
      setStep(1);
    } catch (e) { notify.error(e?.response?.data?.detail || 'Failed to generate'); } finally { setBusy(false); }
  };

  const qtyFor = (grpIdx, itemIdx, def) => {
    const k = `${grpIdx}-${itemIdx}`;
    return qtyOverrides[k] !== undefined ? qtyOverrides[k] : def;
  };

  const selectedItems = () => {
    const out = [];
    (rec?.pack || []).forEach((grp, gi) => grp.items.forEach((it, ii) => {
      const q = Number(qtyFor(gi, ii, it.recommended_qty));
      if (q > 0) out.push({ part_sku: it.part_sku, part_name: it.part_name, machine_model: it.machine_model, quantity: q, unit_value: it.unit_value, reason: it.reason });
    }));
    return out;
  };

  const approve = async () => {
    const items = selectedItems();
    if (items.length === 0) { notify.error('No items to allocate'); return; }
    setBusy(true);
    try {
      const alloc = await dpApi.createAllocation({ dealer_id: dealerId, items });
      notify.success(`Allocation created — ${items.length} parts (draft). Open the Allocations tab to submit & dispatch.`);
      setRec({ ...rec, _createdAllocId: alloc.id });
      setStep(2);
    } catch { notify.error('Failed to create allocation'); } finally { setBusy(false); }
  };

  const reset = () => { setStep(0); setRec(null); setLines([{ machine_ref: '', quantity: 1 }]); setOrderValue(''); setPct(''); setQtyOverrides({}); };

  const liveTotal = () => {
    let t = 0;
    (rec?.pack || []).forEach((grp, gi) => grp.items.forEach((it, ii) => { t += Number(qtyFor(gi, ii, it.recommended_qty)) * (it.unit_value || 0); }));
    return Math.round(t * 100) / 100;
  };

  return (
    <div className="space-y-4" data-testid="dp-allocation-wizard-tab">
      <div className="flex items-center gap-2">
        <Wand2 size={18} className="text-[var(--gx-brand-from)]" />
        <h3 className="font-semibold text-slate-900">Dealer Allocation Wizard</h3>
        {step > 0 && <button onClick={reset} className="ml-auto text-xs text-slate-500 hover:text-slate-800">Start over</button>}
      </div>
      <StepDots step={step} />

      {step === 0 && (
        <div className="space-y-4 max-w-3xl" data-testid="dp-wiz-step0">
          <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-3">
            <label className="block">
              <span className="text-xs font-semibold text-slate-500 mb-1 flex items-center gap-1"><Building2 size={13} /> Dealer *</span>
              <select data-testid="dp-wiz-dealer" className={input} value={dealerId} onChange={(e) => setDealerId(e.target.value)}>
                <option value="">Select dealer…</option>
                {dealers.map((d) => <option key={d.id} value={d.id}>{d.name} · {d.country}</option>)}
              </select>
            </label>
            <div className="grid grid-cols-2 gap-3">
              <label className="block"><span className="text-xs font-semibold text-slate-500 mb-1 block">Order / invoice value (£)</span>
                <input data-testid="dp-wiz-value" type="number" className={input} value={orderValue} onChange={(e) => setOrderValue(e.target.value)} placeholder="50000" /></label>
              <label className="block"><span className="text-xs font-semibold text-slate-500 mb-1 block">Spare parts % (blank = dealer/global default)</span>
                <input data-testid="dp-wiz-pct" type="number" className={input} value={pct} onChange={(e) => setPct(e.target.value)} placeholder="2.5" /></label>
            </div>
          </div>

          <div
            data-testid="dp-wiz-dropzone"
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => { e.preventDefault(); setDragOver(false); parseInvoice(e.dataTransfer.files?.[0]); }}
            onClick={() => fileRef.current?.click()}
            className={`rounded-xl border-2 border-dashed p-6 text-center cursor-pointer transition-all ${dragOver ? 'border-[var(--gx-brand-from)] bg-[var(--gx-brand-from)]/5' : 'border-slate-300 bg-slate-50/50 hover:border-[var(--gx-brand-from)]/50'}`}>
            <input ref={fileRef} type="file" accept=".pdf,.xlsx,.xls,.csv,.txt,.png,.jpg,.jpeg,.webp" className="hidden"
              data-testid="dp-wiz-invoice-input" onChange={(e) => parseInvoice(e.target.files?.[0])} />
            {aiBusy ? (
              <div className="flex flex-col items-center gap-2 py-2 text-slate-500">
                <Sparkles size={22} className="text-[var(--gx-brand-from)] animate-pulse" />
                <span className="text-sm font-medium">AI is reading your invoice…</span>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-1.5">
                <UploadCloud size={26} className="text-[var(--gx-brand-from)]" />
                <div className="text-sm font-semibold text-slate-800">Drop a dealer invoice here, or click to upload</div>
                <div className="text-xs text-slate-500">AI reads the invoice, extracts the machines & values, and matches them to the BOM. <span className="text-slate-400">PDF, Excel, CSV or image.</span></div>
              </div>
            )}
          </div>
          {aiInfo && (
            <div className="rounded-lg bg-emerald-50 border border-emerald-100 p-3 text-xs text-emerald-800 flex items-start gap-2" data-testid="dp-wiz-ai-info">
              <Sparkles size={14} className="mt-0.5 shrink-0" />
              <div>
                <b>AI suggestion — please review.</b> {aiInfo.ref ? `Invoice ${aiInfo.ref}. ` : ''}Extracted {aiInfo.total} machine line(s), {aiInfo.matched} matched to BOM{aiInfo.currency ? ` (${aiInfo.currency})` : ''}. Unmatched refs stay editable below.
                {aiInfo.note ? <div className="text-emerald-700 mt-0.5">{aiInfo.note}</div> : null}
              </div>
            </div>
          )}

          <div className="relative flex items-center gap-2 text-xs text-slate-400">
            <div className="flex-1 h-px bg-slate-200" /> or enter machines manually <div className="flex-1 h-px bg-slate-200" />
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-slate-500">Machines on invoice</span>
              <button onClick={() => setLines([...lines, { machine_ref: '', quantity: 1 }])} className="text-xs text-[var(--gx-brand-from)] font-semibold">+ Add machine</button>
            </div>
            {lines.map((l, i) => (
              <div key={i} className="flex gap-2 mb-2 items-center">
                <input data-testid={`dp-wiz-machine-${i}`} placeholder="Machine ref / stock code / description" className={`${input} flex-1 font-mono`} value={l.machine_ref} onChange={(e) => setLine(i, 'machine_ref', e.target.value)} />
                {l.matched === false && l.input_ref ? <AlertTriangle size={15} className="text-amber-500 shrink-0" title="AI could not match this to a BOM machine" /> : null}
                {l.matched === true ? <CheckCircle2 size={15} className="text-emerald-500 shrink-0" title="Matched to BOM" /> : null}
                <input type="number" placeholder="Qty" className={`${input} w-20`} value={l.quantity} onChange={(e) => setLine(i, 'quantity', e.target.value)} />
                {lines.length > 1 && <button onClick={() => setLines(lines.filter((_, x) => x !== i))} className="text-slate-300 hover:text-red-500"><Trash2 size={16} /></button>}
              </div>
            ))}
          </div>

          <button data-testid="dp-wiz-generate" onClick={generate} disabled={busy}
            className="inline-flex items-center gap-2 bg-[var(--gx-brand-from)] text-white text-sm font-semibold px-5 py-2.5 rounded-lg hover:opacity-90 disabled:opacity-50">
            <Wand2 size={16} /> {busy ? 'Generating…' : 'Generate recommendation'}
          </button>
        </div>
      )}

      {step === 1 && rec && (
        <div className="space-y-4" data-testid="dp-wiz-step1">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <StatCard label="Allowance" value={money(rec.allowance)} tone="brand" />
            <StatCard label="Pack value" value={money(liveTotal())} tone={liveTotal() > rec.allowance ? 'red' : 'emerald'} testid="dp-wiz-packvalue" />
            <StatCard label="Duplicates avoided" value={rec.duplicates_avoided} tone="slate" />
            <StatCard label="Unmatched lines" value={rec.unmatched_lines?.length || 0} tone={rec.unmatched_lines?.length ? 'amber' : 'slate'} />
          </div>

          {liveTotal() > rec.allowance && rec.allowance > 0 && (
            <div className="rounded-lg bg-red-50 border border-red-100 p-3 text-xs text-red-700 flex items-center gap-2"><AlertTriangle size={14} /> Pack exceeds allowance by {money(liveTotal() - rec.allowance)}. Reduce quantities or seek manager approval.</div>
          )}
          {rec.unmatched_lines?.length > 0 && (
            <div className="rounded-lg bg-amber-50 border border-amber-100 p-3 text-xs text-amber-800 flex items-center gap-2"><AlertTriangle size={14} /> Unmatched machine lines (no BOM): {rec.unmatched_lines.map((u) => u.input_ref).join(', ')}. These produce no recommendations until matched.</div>
          )}

          {rec.pack.filter((g) => g.items.length).map((grp, gi) => (
            <div key={gi} className="rounded-xl border border-slate-200 bg-white overflow-hidden" data-testid={`dp-wiz-machine-grp-${gi}`}>
              <div className="px-4 py-2.5 bg-slate-50 border-b border-slate-100 flex items-center gap-2">
                <span className="font-mono text-sm font-semibold text-slate-900">{grp.machine_ref}</span>
                <span className="text-xs text-slate-500">{grp.machine_description}</span>
                <span className="ml-auto text-xs text-slate-400">×{grp.quantity} · {grp.item_count} parts</span>
              </div>
              <table className="w-full text-sm">
                <thead><tr className="text-left text-xs text-slate-400 border-b border-slate-100">
                  <th className="py-2 px-4">Part</th><th>Priority</th><th className="text-right">Used</th><th className="text-right">Rec. qty</th><th className="text-right">Unit</th><th className="text-right">Value</th><th>Note</th>
                </tr></thead>
                <tbody>
                  {grp.items.map((it, ii) => {
                    const q = qtyFor(gi, ii, it.recommended_qty);
                    return (
                      <tr key={ii} data-testid={`dp-wiz-item-${gi}-${ii}`} className={`border-b border-slate-50 ${it.status === 'duplicate_avoided' ? 'opacity-60' : ''}`}>
                        <td className="py-2 px-4 max-w-[240px]"><span className="font-mono text-xs text-slate-500">{it.part_sku}</span><div className="text-xs text-slate-500 truncate">{it.part_name}</div></td>
                        <td><span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border capitalize ${PRIORITY_TONE[it.priority] || PRIORITY_TONE.low}`}>{it.priority}</span></td>
                        <td className="text-right tabular-nums text-slate-500">{it.total_used}</td>
                        <td className="text-right">
                          <input type="number" min="0" data-testid={`dp-wiz-qty-${gi}-${ii}`} className="w-16 text-right rounded border border-slate-200 px-2 py-1 text-sm tabular-nums"
                            value={q} onChange={(e) => setQtyOverrides({ ...qtyOverrides, [`${gi}-${ii}`]: e.target.value })} />
                        </td>
                        <td className="text-right tabular-nums text-slate-500">{money(it.unit_value)}</td>
                        <td className="text-right tabular-nums">{money(Number(q) * (it.unit_value || 0))}</td>
                        <td className="text-xs text-slate-400 max-w-[220px] truncate" title={it.reason}>{it.already_held > 0 ? `Holds ${it.already_held}` : (it.trend || '')}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ))}

          <div className="flex items-center gap-2">
            <button onClick={() => setStep(0)} className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800"><ChevronLeft size={15} /> Back</button>
            <button data-testid="dp-wiz-approve" onClick={approve} disabled={busy} className="ml-auto inline-flex items-center gap-2 bg-[var(--gx-brand-from)] text-white text-sm font-semibold px-5 py-2.5 rounded-lg hover:opacity-90 disabled:opacity-50">
              <PackageCheck size={16} /> {busy ? 'Creating…' : `Approve & create allocation (${selectedItems().length})`}
            </button>
          </div>
        </div>
      )}

      {step === 2 && rec && (
        <div className="text-center py-16" data-testid="dp-wiz-step2">
          <CheckCircle2 size={44} className="text-emerald-500 mx-auto mb-3" />
          <h3 className="text-lg font-bold text-slate-900">Allocation created</h3>
          <p className="text-sm text-slate-500 mt-1">A draft warranty parts pack for <b>{rec.dealer_name}</b> has been created.<br />Open the <b>Allocations</b> tab to submit, approve and dispatch it to the dealer store.</p>
          <button onClick={reset} className="mt-5 inline-flex items-center gap-2 bg-slate-900 text-white text-sm font-semibold px-5 py-2.5 rounded-lg hover:opacity-90"><Plus size={15} /> New allocation</button>
        </div>
      )}
    </div>
  );
}
