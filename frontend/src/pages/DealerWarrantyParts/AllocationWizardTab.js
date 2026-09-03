import { useEffect, useState, useCallback, useRef } from 'react';
import { Wand2, Plus, Trash2, ChevronRight, ChevronLeft, ChevronDown, CheckCircle2, AlertTriangle, PackageCheck, Building2, UploadCloud, Sparkles, FileText, Search, X, Loader2 } from 'lucide-react';
import { notify } from '@/components/notifications';
import { dpApi } from './api';
import { Spinner, StatCard, input, inputTight, money } from './shared';
import { useDealerPartsNav } from './navGuard';
import PlanVsActualsPanel from './PlanVsActualsPanel';

const PRIORITY_TONE = {
  critical: 'bg-red-50 text-red-700 border-red-200',
  recommended: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  optional: 'bg-blue-50 text-blue-700 border-blue-200',
  low: 'bg-slate-100 text-slate-600 border-slate-200',
  manual: 'bg-[var(--gx-brand-from)]/10 text-[var(--gx-brand-from)] border-[var(--gx-brand-from)]/20',
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

function MachinePicker({ onPick, onClose }) {
  const [q, setQ] = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    if (!q.trim()) { setResults([]); return; }
    const t = setTimeout(() => {
      setLoading(true);
      dpApi.listDataMachines({ q, limit: 8 }).then((d) => setResults(d.machines || [])).finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(t);
  }, [q]);
  return (
    <div className="mt-1 mb-2 rounded-lg border border-[var(--gx-brand-from)]/40 bg-white shadow-sm p-2" data-testid="dp-wiz-machine-picker">
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
          <input autoFocus data-testid="dp-wiz-picker-search" value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="Search BOM machines by ref, stock code or name…"
            className="w-full rounded-md border border-slate-200 pl-8 pr-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--gx-brand-from)]/30" />
        </div>
        <button onClick={onClose} className="text-slate-400 hover:text-slate-700"><X size={16} /></button>
      </div>
      {loading ? <div className="text-xs text-slate-400 px-2 py-2">Searching…</div> : results.length > 0 ? (
        <div className="mt-1.5 max-h-52 overflow-y-auto divide-y divide-slate-50">
          {results.map((m) => (
            <button key={m.id} data-testid={`dp-wiz-picker-result-${m.id}`} onClick={() => onPick(m)}
              className="w-full text-left px-2 py-1.5 hover:bg-slate-50 rounded-md">
              <span className="font-mono text-xs font-semibold text-slate-800">{m.top_level_ref}</span>
              <span className="text-xs text-slate-500"> · {m.component_count} components</span>
              <div className="text-xs text-slate-500 truncate">{m.description || 'No description'}</div>
            </button>
          ))}
        </div>
      ) : q.trim() ? <div className="text-xs text-slate-400 px-2 py-2">No machines found.</div> : null}
    </div>
  );
}

export default function AllocationWizardTab() {
  const [step, setStep] = useState(0);
  const [dealers, setDealers] = useState([]);
  const [dealerId, setDealerId] = useState('');
  const [orderValue, setOrderValue] = useState('');
  const [pct, setPct] = useState('');
  const [coverYears, setCoverYears] = useState(5);
  const [lines, setLines] = useState([{ machine_ref: '', quantity: 1 }]);
  const [rec, setRec] = useState(null);
  const [busy, setBusy] = useState(false);
  const [qtyOverrides, setQtyOverrides] = useState({});
  const [aiBusy, setAiBusy] = useState(false);
  const [aiProgress, setAiProgress] = useState(0);
  const [aiInfo, setAiInfo] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const [resolving, setResolving] = useState(null);
  const [resolvingUnmatched, setResolvingUnmatched] = useState(null); // step-1 unmatched input_ref being mapped
  const [manualParts, setManualParts] = useState({}); // `${ref}||${code}` -> {part_sku, part_name, machine_model, quantity, unit_value}
  const [bomOpen, setBomOpen] = useState(null);        // machine ref whose BOM is expanded
  const [bomData, setBomData] = useState({});          // ref -> {loading, components}
  const [bomQuery, setBomQuery] = useState('');
  const [invoiceRef, setInvoiceRef] = useState('');   // Iter 282 — invoice number for the allocation log + dedupe
  const [dupInfo, setDupInfo] = useState(null);        // duplicate-invoice warning from the parser
  const fileRef = useRef(null);

  const loadBom = (ref) => {
    if (bomOpen === ref) { setBomOpen(null); return; }
    setBomOpen(ref); setBomQuery('');
    if (bomData[ref]?.components) return;
    setBomData((s) => ({ ...s, [ref]: { loading: true } }));
    dpApi.machineParts(ref)
      .then((d) => setBomData((s) => ({ ...s, [ref]: { loading: false, components: d.components || [] } })))
      .catch(() => setBomData((s) => ({ ...s, [ref]: { loading: false, components: [] } })));
  };

  const manualKey = (ref, code) => `${ref}||${code}`;
  const setManualQty = (ref, c, qty) => {
    const q = Math.max(0, Number(qty) || 0);
    setManualParts((s) => {
      const n = { ...s };
      const k = manualKey(ref, c.code);
      if (q <= 0) delete n[k];
      else n[k] = { part_sku: c.code, part_name: c.description, machine_model: ref, quantity: q, unit_value: c.unit_value || 0 };
      return n;
    });
  };
  const manualQtyOf = (ref, code) => manualParts[manualKey(ref, code)]?.quantity || 0;

  useEffect(() => { dpApi.listDealers().then((d) => setDealers(d.dealers || [])); }, []);

  // Iter 282 — report unsaved-work state so the page can warn before the
  // user navigates away mid-allocation. Step 2 is the completed screen.
  const { setDirty } = useDealerPartsNav();
  const isDirty = step === 1 || (step === 0 && (
    !!dealerId || !!orderValue || !!invoiceRef || !!rec || !!aiInfo ||
    lines.some((l) => (l.machine_ref || '').trim())
  ));
  useEffect(() => { setDirty(isDirty); }, [isDirty, setDirty]);
  useEffect(() => () => setDirty(false), [setDirty]);

  const setLine = (i, k, v) => { const n = [...lines]; n[i][k] = v; setLines(n); };

  const pickMachine = async (i, m) => {
    const origRef = (lines[i].input_ref || lines[i].machine_ref || '').trim();
    const n = [...lines];
    n[i] = { ...n[i], machine_ref: m.top_level_ref, matched: true, description: m.description || '', input_ref: origRef };
    setLines(n);
    setResolving(null);
    notify.success(`Matched to ${m.top_level_ref}`);
    // Remember the mapping so this invoice ref auto-resolves next time.
    const differs = origRef && origRef.replace(/\s/g, '').toLowerCase() !== (m.top_level_ref || '').replace(/\s/g, '').toLowerCase();
    if (differs) {
      try {
        await dpApi.createMachineAlias({ input_ref: origRef, top_level_ref: m.top_level_ref });
        notify.success(`Remembered — “${origRef}” will map to ${m.top_level_ref} automatically next time.`);
      } catch {
        notify.error(`Matched for this order, but couldn’t save “${origRef}” for next time.`);
      }
    }
  };

  const parseInvoice = async (file) => {
    if (!file) return;
    setAiBusy(true); setAiInfo(null); setAiProgress(0);
    try {
      const res = await dpApi.aiParseInvoiceFile(file, setAiProgress);
      if (!res.available) { notify.error(res.error || 'AI could not read this invoice'); return; }
      const newLines = (res.lines || []).map((l) => ({
        machine_ref: l.top_level_ref || l.input_ref || '',
        quantity: l.quantity || 1,
        matched: l.matched,
        input_ref: l.input_ref,
        description: l.machine_description || '',
        unit_value: l.unit_value,
      }));
      if (newLines.length) setLines(newLines);
      if (res.order_value) setOrderValue(String(res.order_value));
      if (res.order_reference) setInvoiceRef(res.order_reference);
      if (res.duplicate_invoice) {
        setDupInfo({ dealer: res.duplicate_dealer_name, at: res.duplicate_allocated_at });
        notify.error(`Invoice ${res.order_reference} has already been allocated${res.duplicate_dealer_name ? ` to ${res.duplicate_dealer_name}` : ''}.`);
      } else {
        setDupInfo(null);
      }
      setAiInfo({ ref: res.order_reference, currency: res.currency, matched: res.matched_count, total: res.lines?.length || 0, note: res.note,
        machinesTotal: res.machines_total, machinesMatched: res.machines_matched, source: res.source });
      const machineMsg = res.machines_total != null
        ? `AI found ${res.machines_total} machines — ${res.machines_matched} matched to BOM`
        : `AI read the invoice — ${res.matched_count}/${res.lines?.length || 0} machines matched to BOM`;
      notify.success(machineMsg);
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
        cover_years: coverYears,
        lines: validLines.map((l) => ({ machine_ref: l.machine_ref, quantity: Number(l.quantity) || 1 })),
      });
      setRec(r);
      setQtyOverrides({});
      setStep(1);
    } catch (e) { notify.error(e?.response?.data?.detail || 'Failed to generate'); } finally { setBusy(false); }
  };

  const resolveUnmatched = async (inputRef, m) => {
    setResolvingUnmatched(null);
    try {
      await dpApi.createMachineAlias({ input_ref: inputRef, top_level_ref: m.top_level_ref });
      notify.success(`Remembered — “${inputRef}” maps to ${m.top_level_ref}. Updating recommendation…`);
      await generate();
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Could not save the mapping');
    }
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
    Object.values(manualParts).forEach((m) => { if (m.quantity > 0) out.push({ ...m, reason: `Manually selected from ${m.machine_model} BOM` }); });
    return out;
  };

  const approve = async () => {
    const items = selectedItems();
    if (items.length === 0) { notify.error('No items to allocate'); return; }
    if (dupInfo) { notify.error('This invoice has already been allocated — change the invoice number to continue.'); return; }
    setBusy(true);
    try {
      const alloc = await dpApi.createAllocation({ dealer_id: dealerId, items, invoice_reference: invoiceRef.trim() });
      notify.success(`Allocation created — ${items.length} parts (draft). Open the Allocations tab to submit & dispatch.`);
      setRec({ ...rec, _createdAllocId: alloc.id });
      setStep(2);
    } catch (e) {
      if (e?.response?.status === 409) {
        setDupInfo({ dealer: '', at: null });
        notify.error(e?.response?.data?.detail || 'This invoice has already been allocated.');
      } else {
        notify.error('Failed to create allocation');
      }
    } finally { setBusy(false); }
  };

  const reset = () => { setStep(0); setRec(null); setLines([{ machine_ref: '', quantity: 1 }]); setOrderValue(''); setPct(''); setCoverYears(5); setQtyOverrides({}); setManualParts({}); setBomOpen(null); setBomData({}); setInvoiceRef(''); setDupInfo(null); };

  const liveTotal = () => {
    let t = 0;
    (rec?.pack || []).forEach((grp, gi) => grp.items.forEach((it, ii) => { t += Number(qtyFor(gi, ii, it.recommended_qty)) * (it.unit_value || 0); }));
    Object.values(manualParts).forEach((m) => { t += m.quantity * (m.unit_value || 0); });
    return Math.round(t * 100) / 100;
  };

  const consolidatedParts = () => {
    const map = {};
    const add = (sku, name, priority, q, unit, machine) => {
      if (q <= 0) return;
      if (!map[sku]) map[sku] = { sku, name, priority: priority || 'low', qty: 0, unit: unit || 0, value: 0, machines: new Set() };
      map[sku].qty += q; map[sku].value += q * (unit || 0);
      if (machine) map[sku].machines.add(machine);
    };
    (rec?.pack || []).forEach((grp, gi) => grp.items.forEach((it, ii) => add(it.part_sku, it.part_name, it.priority, Number(qtyFor(gi, ii, it.recommended_qty)), it.unit_value, it.machine_model)));
    Object.values(manualParts).forEach((m) => add(m.part_sku, m.part_name, 'manual', m.quantity, m.unit_value, m.machine_model));
    return Object.values(map).sort((a, b) => b.value - a.value);
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
            <div>
              <span className="text-xs font-semibold text-slate-500 mb-1 block">Cover period <span className="text-slate-400 font-normal">— how many years of expected failures to pack</span></span>
              <div className="flex gap-1.5" data-testid="dp-wiz-cover-years">
                {[1, 2, 3, 4, 5].map((y) => (
                  <button key={y} type="button" data-testid={`dp-wiz-cover-${y}`} onClick={() => setCoverYears(y)}
                    className={`flex-1 py-2 rounded-lg text-sm font-semibold border transition-colors ${coverYears === y ? 'bg-[var(--gx-brand-from)] text-white border-[var(--gx-brand-from)]' : 'bg-white text-slate-600 border-slate-200 hover:border-[var(--gx-brand-from)]/40'}`}>
                    {y} {y === 1 ? 'yr' : 'yrs'}
                  </button>
                ))}
              </div>
            </div>
            <label className="block"><span className="text-xs font-semibold text-slate-500 mb-1 block">Invoice number <span className="text-slate-400 font-normal">— logged against the dealer; each invoice can only be allocated once</span></span>
              <input data-testid="dp-wiz-invoice-ref" className={`${input} font-mono ${dupInfo ? 'border-red-300 bg-red-50/50' : ''}`} value={invoiceRef}
                onChange={(e) => { setInvoiceRef(e.target.value); setDupInfo(null); }} placeholder="e.g. INV-2051 (auto-filled from the invoice)" /></label>
            {dupInfo && (
              <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-xs text-red-700 flex items-start gap-2" data-testid="dp-wiz-duplicate-warning">
                <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                <div><b>Invoice already used.</b> Invoice <span className="font-mono">{invoiceRef}</span> has already had parts allocated{dupInfo.dealer ? ` to ${dupInfo.dealer}` : ''}. Change the invoice number to continue — an invoice can only be allocated once.</div>
              </div>
            )}
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
              <div className="flex flex-col items-center gap-2.5 py-3 text-slate-600" data-testid="dp-wiz-ai-status">
                <div className="flex items-center gap-2">
                  <Sparkles size={20} className="text-[var(--gx-brand-from)] animate-pulse" />
                  <span className="text-sm font-semibold">{aiProgress < 100 ? `Uploading invoice… ${aiProgress}%` : 'AI is reading your invoice…'}</span>
                </div>
                <div className="w-64 h-2 rounded-full bg-slate-100 overflow-hidden">
                  {aiProgress < 100
                    ? <div className="h-full bg-[var(--gx-brand-from)] transition-all duration-200" style={{ width: `${aiProgress}%` }} />
                    : <div className="h-full w-1/3 bg-[var(--gx-brand-from)] rounded-full dp-indeterminate" />}
                </div>
                <span className="text-xs text-slate-400">
                  {aiProgress < 100 ? 'Securely streaming your file…' : 'Extracting machines, quantities & values and matching them to the BOM…'}
                </span>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-1.5">
                <UploadCloud size={26} className="text-[var(--gx-brand-from)]" />
                <div className="text-sm font-semibold text-slate-800">Drop a dealer invoice here, or click to upload</div>
                <div className="text-xs text-slate-500">AI reads the invoice, extracts the machines & values, and matches them to the BOM. <span className="text-slate-400">PDF, Excel, CSV or image — large files supported, never stored.</span></div>
              </div>
            )}
          </div>
          {aiInfo && (
            <div className="rounded-lg bg-emerald-50 border border-emerald-100 p-3 text-xs text-emerald-800 flex items-start gap-2" data-testid="dp-wiz-ai-info">
              <Sparkles size={14} className="mt-0.5 shrink-0" />
              <div>
                <b>AI suggestion — please review.</b> {aiInfo.note
                  ? aiInfo.note
                  : `${aiInfo.ref ? `Invoice ${aiInfo.ref}. ` : ''}Extracted ${aiInfo.total} machine line(s), ${aiInfo.matched} matched to BOM${aiInfo.currency ? ` (${aiInfo.currency})` : ''}.`}
                {' '}Unmatched machines stay editable below — use “Find in BOM” to map them.
              </div>
            </div>
          )}

          <div className="relative flex items-center gap-2 text-xs text-slate-400">
            <div className="flex-1 h-px bg-slate-200" /> or enter machines manually <div className="flex-1 h-px bg-slate-200" />
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-slate-500">Machines on invoice <span className="text-slate-400 font-normal">— item code matched to your BOM</span></span>
              <button onClick={() => setLines([...lines, { machine_ref: '', quantity: 1 }])} className="text-xs text-[var(--gx-brand-from)] font-semibold">+ Add machine</button>
            </div>
            <div className="hidden sm:grid grid-cols-[1fr_92px_40px] gap-2 px-1 pb-1.5 text-[11px] font-semibold text-slate-400">
              <span>Item code / machine</span><span className="text-center">Qty</span><span />
            </div>
            {lines.map((l, i) => (
              <div key={i} className="mb-2.5">
                <div className="grid grid-cols-[1fr_92px_40px] gap-2 items-start">
                  <div>
                    <div className="relative">
                      <input data-testid={`dp-wiz-machine-${i}`} placeholder="Item code / stock code / description"
                        className={`${inputTight} w-full font-mono font-semibold pr-8 ${l.matched === true ? 'border-emerald-300 bg-emerald-50/40' : l.matched === false && l.input_ref ? 'border-amber-300 bg-amber-50/40' : ''}`}
                        value={l.machine_ref} onChange={(e) => setLine(i, 'machine_ref', e.target.value)} />
                      {l.matched === true ? <CheckCircle2 size={15} className="text-emerald-500 absolute right-2.5 top-1/2 -translate-y-1/2" /> : null}
                      {l.matched === false && l.input_ref ? <AlertTriangle size={15} className="text-amber-500 absolute right-2.5 top-1/2 -translate-y-1/2" title="Not found in BOM" /> : null}
                    </div>
                    {l.description ? (
                      <div className="text-xs text-slate-500 mt-1 pl-1 truncate" title={l.description}>{l.description}</div>
                    ) : l.matched === false && l.input_ref ? (
                      <div className="text-xs text-amber-600 mt-1 pl-1">Not matched to BOM — use “Find in BOM” to map it.</div>
                    ) : null}
                    <button type="button" data-testid={`dp-wiz-resolve-${i}`} onClick={() => setResolving(resolving === i ? null : i)}
                      className={`mt-1 inline-flex items-center gap-1 text-xs font-semibold ${l.matched === false && l.input_ref ? 'text-amber-700' : 'text-[var(--gx-brand-from)]'}`}
                      title="Find & pick a BOM machine">
                      <Search size={12} /> Find in BOM
                    </button>
                    {resolving === i && <MachinePicker onPick={(m) => pickMachine(i, m)} onClose={() => setResolving(null)} />}
                  </div>
                  <input type="number" min="1" placeholder="Qty" data-testid={`dp-wiz-qty-input-${i}`} className={`${inputTight} w-full text-center tabular-nums`} value={l.quantity} onChange={(e) => setLine(i, 'quantity', e.target.value)} />
                  <div className="flex items-center justify-center pt-2">
                    {lines.length > 1 && <button onClick={() => setLines(lines.filter((_, x) => x !== i))} className="text-slate-300 hover:text-red-500"><Trash2 size={16} /></button>}
                  </div>
                </div>
              </div>
            ))}
          </div>

          <button data-testid="dp-wiz-generate" onClick={generate} disabled={busy || !!dupInfo}
            className="inline-flex items-center gap-2 bg-[var(--gx-brand-from)] text-white text-sm font-semibold px-5 py-2.5 rounded-lg hover:opacity-90 disabled:opacity-50">
            <Wand2 size={16} /> {busy ? 'Generating…' : dupInfo ? 'Invoice already used' : 'Generate recommendation'}
          </button>
        </div>
      )}

      {step === 1 && rec && (
        <div className="space-y-4" data-testid="dp-wiz-step1">
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
            <StatCard label="Allowance" value={money(rec.allowance)} tone="brand" />
            <StatCard label="Pack value" value={money(liveTotal())} tone={liveTotal() > rec.allowance ? 'red' : 'emerald'} testid="dp-wiz-packvalue" />
            <StatCard label="Allowance remaining" value={money(rec.allowance - liveTotal())} tone={(rec.allowance - liveTotal()) < 0 ? 'red' : 'emerald'} testid="dp-wiz-remaining" />
            <StatCard label="Duplicates avoided" value={rec.duplicates_avoided} tone="slate" />
            <StatCard label="Unmatched lines" value={rec.unmatched_lines?.length || 0} tone={rec.unmatched_lines?.length ? 'amber' : 'slate'} />
          </div>

          {rec.plan_used && (
            <div className="rounded-lg bg-emerald-50 border border-emerald-100 p-3 text-xs text-emerald-800 flex items-center gap-2" data-testid="dp-wiz-plan-badge">
              <CheckCircle2 size={14} /> Based on Pulse's {rec.cover_years || 5}-year warranty failure plan — the most-likely parts per machine over {rec.cover_years || 5} year{(rec.cover_years || 5) !== 1 ? 's' : ''}, topped up with proven-usage parts to use the remaining allowance.
            </div>
          )}

          {liveTotal() > rec.allowance && rec.allowance > 0 && (
            <div className="rounded-lg bg-red-50 border border-red-100 p-3 text-xs text-red-700 flex items-center gap-2"><AlertTriangle size={14} /> Pack exceeds allowance by {money(liveTotal() - rec.allowance)}. Reduce quantities or seek manager approval.</div>
          )}
          {rec.unmatched_lines?.length > 0 && (
            <div className="rounded-lg bg-amber-50 border border-amber-100 p-3 text-xs text-amber-800" data-testid="dp-wiz-unmatched-warning">
              <div className="flex items-start gap-2">
                <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                <div className="flex-1">
                  <b>{rec.unmatched_lines.length} machine line(s) not found in the BOM.</b> They produce no recommendations until mapped. Pick the right BOM machine — we’ll remember it for next time.
                  {busy && <span className="ml-1 inline-flex items-center gap-1 font-semibold text-amber-700"><Loader2 size={11} className="animate-spin" /> Re-checking BOM…</span>}
                  <div className="mt-2 space-y-1.5">
                    {rec.unmatched_lines.map((u) => (
                      <div key={u.input_ref} data-testid={`dp-wiz-unmatched-${u.input_ref}`}>
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-mono font-semibold text-amber-900">{u.input_ref}</span>
                          <span className="text-amber-500">×{u.quantity}</span>
                          <button data-testid={`dp-wiz-unmatched-find-${u.input_ref}`}
                            onClick={() => setResolvingUnmatched(resolvingUnmatched === u.input_ref ? null : u.input_ref)}
                            className="inline-flex items-center gap-1 font-semibold text-amber-800 hover:underline">
                            <Search size={12} /> Find in BOM
                          </button>
                        </div>
                        {resolvingUnmatched === u.input_ref && (
                          <MachinePicker onPick={(m) => resolveUnmatched(u.input_ref, m)} onClose={() => setResolvingUnmatched(null)} />
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {rec.note && (
            <div className={`rounded-lg p-3 text-xs flex items-start gap-2 border ${rec.parts_total === 0 ? 'bg-amber-50 border-amber-100 text-amber-800' : 'bg-blue-50 border-blue-100 text-blue-800'}`} data-testid="dp-wiz-rec-note">
              <AlertTriangle size={14} className="mt-0.5 shrink-0" /><div>{rec.note}</div>
            </div>
          )}

          {rec.matched_machine_count > 0 && (
            <PlanVsActualsPanel lines={(rec.machine_lines || []).filter((l) => l.matched).map((l) => ({ machine_ref: l.top_level_ref || l.input_ref, quantity: l.quantity }))} />
          )}

          {(() => {
            const machines = [];
            const seen = new Set();
            (rec?.pack || []).forEach((g) => { if (g.machine_ref && !seen.has(g.machine_ref)) { seen.add(g.machine_ref); machines.push({ machine_ref: g.machine_ref, description: g.machine_description }); } });
            if (!machines.length) return null;
            return (
              <div className="rounded-xl border border-slate-200 bg-white" data-testid="dp-wiz-bom-browser">
                <div className="px-4 py-2.5 border-b border-slate-100 flex items-center gap-2 flex-wrap">
                  <PackageCheck size={15} className="text-[var(--gx-brand-from)]" />
                  <span className="text-sm font-bold text-slate-900">Choose parts from the machine BOM</span>
                  <span className="text-xs text-slate-500">Browse each machine’s full BOM and add parts by hand — ideal when there’s no usage history yet.</span>
                </div>
                {machines.map((mac) => {
                  const ref = mac.machine_ref;
                  const bd = bomData[ref] || {};
                  const opened = bomOpen === ref;
                  const chosen = Object.keys(manualParts).filter((k) => k.startsWith(`${ref}||`)).length;
                  const comps = (bd.components || []).filter((c) => {
                    const q = bomQuery.trim().toLowerCase();
                    return !q || (c.code || '').toLowerCase().includes(q) || (c.description || '').toLowerCase().includes(q);
                  });
                  return (
                    <div key={ref} className="border-b border-slate-50 last:border-0">
                      <button onClick={() => loadBom(ref)} className="w-full flex items-center gap-2 px-4 py-2.5 hover:bg-slate-50 text-left" data-testid={`dp-wiz-bom-toggle-${ref}`}>
                        {opened ? <ChevronDown size={15} className="text-slate-400" /> : <ChevronRight size={15} className="text-slate-400" />}
                        <span className="font-mono text-sm font-semibold text-slate-900">{ref}</span>
                        <span className="text-xs text-slate-500 truncate">{mac.description}</span>
                        {chosen > 0
                          ? <span className="ml-auto text-xs font-semibold text-[var(--gx-brand-from)]">{chosen} part{chosen > 1 ? 's' : ''} chosen</span>
                          : <span className="ml-auto text-xs text-slate-400">Browse BOM</span>}
                      </button>
                      {opened && (
                        <div className="px-4 pb-3">
                          {bd.loading ? <div className="py-5 flex justify-center"><Spinner /></div> : (
                            <>
                              <div className="relative mb-2">
                                <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
                                <input className={`${inputTight} w-full pl-8`} placeholder="Filter parts by code or description…" value={bomQuery} onChange={(e) => setBomQuery(e.target.value)} data-testid={`dp-wiz-bom-filter-${ref}`} />
                              </div>
                              <div className="max-h-80 overflow-y-auto rounded-lg border border-slate-100">
                                <table className="w-full text-sm">
                                  <thead className="sticky top-0 bg-white shadow-sm"><tr className="text-left text-xs text-slate-400 border-b border-slate-100">
                                    <th className="py-1.5 px-3">Part ({comps.length})</th><th className="text-right">Used 12m</th><th className="text-right">Unit</th><th className="text-right px-3">Send qty</th>
                                  </tr></thead>
                                  <tbody>
                                    {comps.slice(0, 400).map((c) => (
                                      <tr key={c.code} className={`border-b border-slate-50 ${manualQtyOf(ref, c.code) > 0 ? 'bg-emerald-50/50' : ''}`}>
                                        <td className="py-1.5 px-3 max-w-[340px]"><span className="font-mono text-xs text-slate-500">{c.code}</span><div className="text-xs text-slate-600 truncate">{c.description}</div></td>
                                        <td className="text-right tabular-nums text-slate-500">{c.recent_12m || 0}</td>
                                        <td className="text-right tabular-nums text-slate-500">{c.has_value ? money(c.unit_value) : '—'}</td>
                                        <td className="text-right px-3">
                                          <input type="number" min="0" data-testid={`dp-wiz-bom-qty-${ref}-${c.code}`} className="w-16 text-right rounded border border-slate-200 px-2 py-1 text-sm tabular-nums"
                                            value={manualQtyOf(ref, c.code) || ''} placeholder="0" onChange={(e) => setManualQty(ref, c, e.target.value)} />
                                        </td>
                                      </tr>
                                    ))}
                                    {comps.length === 0 && <tr><td colSpan={4} className="py-4 text-center text-xs text-slate-400">No parts match your filter.</td></tr>}
                                  </tbody>
                                </table>
                              </div>
                            </>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            );
          })()}


          {consolidatedParts().length > 0 && (
            <div className="rounded-xl border border-slate-200 bg-white overflow-hidden" data-testid="dp-wiz-consolidated">
              <div className="px-4 py-2.5 bg-[var(--gx-brand-from)]/5 border-b border-slate-100 flex items-center gap-2">
                <PackageCheck size={15} className="text-[var(--gx-brand-from)]" />
                <span className="text-sm font-bold text-slate-900">Recommended parts</span>
                <span className="text-xs text-slate-500">{consolidatedParts().length} unique · {consolidatedParts().reduce((s, p) => s + p.qty, 0)} total qty</span>
                <span className="ml-auto text-sm font-bold text-slate-900">{money(liveTotal())}</span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="text-left text-xs text-slate-400 border-b border-slate-100">
                    <th className="py-2 px-4">Part</th><th>Priority</th><th>For machines</th><th className="text-right">Qty</th><th className="text-right">Unit</th><th className="text-right px-4">Value</th>
                  </tr></thead>
                  <tbody>
                    {consolidatedParts().map((p) => (
                      <tr key={p.sku} className="border-b border-slate-50" data-testid={`dp-wiz-cons-${p.sku}`}>
                        <td className="py-2 px-4 max-w-[260px]"><span className="font-mono text-xs text-slate-500">{p.sku}</span><div className="text-xs text-slate-600 truncate">{p.name}</div></td>
                        <td><span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border capitalize ${PRIORITY_TONE[p.priority] || PRIORITY_TONE.low}`}>{p.priority}</span></td>
                        <td className="text-xs text-slate-500 font-mono">{[...p.machines].slice(0, 3).join(', ')}{p.machines.size > 3 ? ` +${p.machines.size - 3}` : ''}</td>
                        <td className="text-right tabular-nums font-semibold">{p.qty}</td>
                        <td className="text-right tabular-nums text-slate-500">{money(p.unit)}</td>
                        <td className="text-right tabular-nums px-4">{money(p.value)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {rec.duplicates_avoided > 0 && (
            <div className="rounded-lg bg-indigo-50 border border-indigo-100 p-3 text-xs text-indigo-800 flex items-start gap-2" data-testid="dp-wiz-dedup-banner">
              <PackageCheck size={15} className="mt-0.5 shrink-0 text-indigo-600" />
              <div><b>{rec.duplicates_avoided} part{rec.duplicates_avoided > 1 ? 's' : ''} auto-adjusted</b> to avoid duplicating stock this dealer already holds or has on order. Lines tagged <span className="font-semibold">“Already sent”</span> were skipped or reduced — they’re only re-sent if the dealer has run out.</div>
            </div>
          )}

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
