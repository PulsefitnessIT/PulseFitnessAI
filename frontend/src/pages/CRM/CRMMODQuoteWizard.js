import React, { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';
import {
  X, ShieldCheck, Loader2, Sparkles, Plus, Trash2, ChevronRight, ChevronLeft,
  CheckCircle2, AlertTriangle, Settings2, FileText, MapPin, Upload, FileSpreadsheet,
} from 'lucide-react';
import { notify } from '@/components/notifications';

const fmt = (n) => `£${(Number(n) || 0).toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const CONTRACTS = [
  { id: 'A', title: 'Type A', sub: 'All-Inclusive Annual Service (UK)', desc: 'Fixed 12-month service, repair & maintenance per item. Generates a service contract.' },
  { id: 'B', title: 'Type B', sub: 'Ad-hoc Service & Repair (UK)', desc: 'Per-visit call-out. Add £80 UK call-out charges as needed.' },
  { id: 'C', title: 'Type C', sub: 'Overseas / Repairs / Refurb (POA)', desc: 'Priced case-by-case — enter a custom price per line.' },
];

/* ═══ RATE CARD EDITOR ═══ */
function RateCardEditor({ API, headers, c, isDark, rateCard, onSaved, onClose }) {
  const [rows, setRows] = useState(rateCard);
  const [savingId, setSavingId] = useState('');
  // Self-fetch fallback so the editor never flashes empty if opened before
  // the parent's rate-card fetch has resolved.
  useEffect(() => {
    if (rows && rows.length) return;
    axios.get(`${API}/crm/mod-quote/rate-card`, { headers: headers() })
      .then(r => setRows(r.data.items || []))
      .catch(() => {});
  }, [API, headers]); // eslint-disable-line react-hooks/exhaustive-deps
  const inputStyle = { background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text };

  const setField = (id, field, val) => setRows(rows.map(r => r.id === id ? { ...r, [field]: val } : r));

  const save = async (row) => {
    setSavingId(row.id);
    try {
      const payload = {};
      ['type_a_price', 'type_b_price', 'type_a_price_y2', 'type_a_price_y3', 'type_a_price_y4',
       'type_b_price_y2', 'type_b_price_y3', 'type_b_price_y4'].forEach(f => {
        payload[f] = (row[f] === '' || row[f] === null || row[f] === undefined) ? null : Number(row[f]);
      });
      const r = await axios.put(`${API}/crm/mod-quote/rate-card/${row.id}`, payload, { headers: headers() });
      setRows(rows.map(x => x.id === row.id ? r.data : x));
      notify.success('Rate updated');
      onSaved && onSaved();
    } catch (e) {
      notify.error(e.response?.data?.detail || 'Could not update rate (admin only)');
    }
    setSavingId('');
  };

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={onClose}>
      <div className="w-full max-w-4xl mx-4 rounded-xl p-6 shadow-2xl max-h-[90vh] overflow-y-auto"
        style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', border: `1px solid ${c.border}` }}
        onClick={e => e.stopPropagation()} data-testid="mod-rate-card-editor">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-lg font-semibold" style={{ color: c.text }}>SOR Rate Card</h3>
            <p className="text-xs" style={{ color: c.textDim }}>Contracted framework prices. Set Year 2–4 overrides at pricing anniversaries.</p>
          </div>
          <button onClick={onClose} style={{ color: c.textDim }} data-testid="mod-rate-card-close"><X size={18} /></button>
        </div>
        <table className="w-full text-xs">
          <thead>
            <tr style={{ color: c.textDim, borderBottom: `1px solid ${c.border}` }}>
              <th className="text-left py-2">Line</th><th>A Y1</th><th>A Y2</th><th>A Y3</th><th>A Y4</th>
              <th>B Y1</th><th>B Y2</th><th>B Y3</th><th>B Y4</th><th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map(r => (
              <tr key={r.id} style={{ borderBottom: `1px solid ${c.border}` }} data-testid={`mod-rate-row-${r.id}`}>
                <td className="py-1.5 pr-2" style={{ color: c.text }}>
                  <span className="font-medium">{r.label}</span>
                  {r.is_poa && <span className="ml-1 text-[9px] px-1 rounded" style={{ background: 'var(--color-warning)', color: '#000' }}>POA</span>}
                </td>
                {['type_a_price', 'type_a_price_y2', 'type_a_price_y3', 'type_a_price_y4',
                  'type_b_price', 'type_b_price_y2', 'type_b_price_y3', 'type_b_price_y4'].map(f => (
                  <td key={f} className="px-0.5">
                    <input type="number" step="0.01" value={r[f] ?? ''} disabled={r.is_poa}
                      onChange={e => setField(r.id, f, e.target.value)}
                      className="w-14 px-1 py-1 rounded text-right disabled:opacity-40" style={inputStyle} />
                  </td>
                ))}
                <td>
                  <button onClick={() => save(r)} disabled={r.is_poa || savingId === r.id}
                    className="px-2 py-1 rounded text-[10px] font-medium disabled:opacity-40"
                    style={{ background: 'var(--color-info-ios)', color: '#fff' }} data-testid={`mod-rate-save-${r.id}`}>
                    {savingId === r.id ? '…' : 'Save'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ═══ MOD AUTO QUOTE WIZARD ═══ */
export default function CRMMODQuoteWizard({ API, headers, c, isDark, onClose, onCreated }) {
  const [step, setStep] = useState(1);
  const [sites, setSites] = useState([]);
  const [rateCard, setRateCard] = useState([]);
  const [siteId, setSiteId] = useState('');
  const [contractType, setContractType] = useState('A');
  const [year, setYear] = useState(1);
  const [lines, setLines] = useState([]);
  const [loadingEq, setLoadingEq] = useState(false);
  const [callOutCount, setCallOutCount] = useState(0);
  const [notes, setNotes] = useState('');
  const [generating, setGenerating] = useState(false);
  const [showRateCard, setShowRateCard] = useState(false);
  const [importing, setImporting] = useState(false);
  const [pasteMode, setPasteMode] = useState(false);
  const [pastedText, setPastedText] = useState('');
  const [importNote, setImportNote] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const [aiBusyId, setAiBusyId] = useState('');

  const inputStyle = { background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text };
  const serviceCard = useMemo(() => rateCard.filter(r => r.kind === 'service'), [rateCard]);
  const poaCard = useMemo(() => rateCard.filter(r => r.is_poa), [rateCard]);
  const site = sites.find(s => s.id === siteId);

  const loadBase = useCallback(async () => {
    try {
      const [sr, rr] = await Promise.all([
        axios.get(`${API}/crm/mod-quote/mod-sites`, { headers: headers() }),
        axios.get(`${API}/crm/mod-quote/rate-card`, { headers: headers() }),
      ]);
      setSites(sr.data.sites || []);
      setRateCard(rr.data.items || []);
    } catch (e) { notify.error('Could not load MOD sites / rate card'); }
  }, [API, headers]);

  useEffect(() => { loadBase(); }, [loadBase]);

  const priceFor = useCallback((rcId) => {
    const rc = rateCard.find(r => r.id === rcId);
    if (!rc || rc.is_poa || contractType === 'C') return null;
    const base = contractType === 'A' ? 'type_a_price' : 'type_b_price';
    if (year > 1 && rc[`${base}_y${year}`] != null) return rc[`${base}_y${year}`];
    return rc[base];
  }, [rateCard, contractType, year]);

  const loadEquipment = useCallback(async () => {
    if (!siteId) { notify.error('Pick a MOD site first'); return; }
    setLoadingEq(true);
    try {
      const r = await axios.get(`${API}/crm/mod-quote/equipment`, {
        headers: headers(), params: { site_id: siteId, contract_type: contractType, year },
      });
      setLines((r.data.lines || []).map(l => ({ ...l, key: l.equipment_id || Math.random().toString(36).slice(2), included: true })));
      setStep(2);
    } catch (e) { notify.error('Could not load equipment'); }
    setLoadingEq(false);
  }, [API, headers, siteId, contractType, year]);

  const updateLine = (key, patch) => setLines(ls => ls.map(l => l.key === key ? { ...l, ...patch } : l));
  const removeLine = (key) => setLines(ls => ls.filter(l => l.key !== key));
  const addCustomLine = (poaId) => {
    const rc = rateCard.find(r => r.id === poaId);
    setLines(ls => [...ls, {
      key: Math.random().toString(36).slice(2), equipment_id: null,
      name: rc ? rc.label : 'Custom line', rate_card_id: poaId || null,
      rate_card_label: rc ? rc.label : 'Custom', matched: true, confidence: 1,
      unit_price: 0, quantity: 1, included: true, custom: true,
    }]);
  };

  const onSelectRateCard = (key, rcId) => {
    updateLine(key, { rate_card_id: rcId, rate_card_label: (rateCard.find(r => r.id === rcId) || {}).label, unit_price: priceFor(rcId) ?? 0, matched: true });
  };

  const aiSuggest = async (line) => {
    setAiBusyId(line.key);
    try {
      const r = await axios.post(`${API}/crm/mod-quote/ai-match`, {
        equipment: { name: line.name, equipment_type: line.equipment_type, model: line.model },
      }, { headers: headers() });
      if (r.data.rate_card_id) {
        onSelectRateCard(line.key, r.data.rate_card_id);
        notify.success(`AI matched → ${r.data.label}`);
      } else notify.info('AI could not find a confident match — please pick manually');
    } catch (e) { notify.error('AI matching unavailable'); }
    setAiBusyId('');
  };

  const activeLines = lines.filter(l => l.included);
  const priced = (l) => contractType === 'C' || (l.custom && !l.rate_card_id) ? (Number(l.unit_price) || 0) : (priceFor(l.rate_card_id) ?? 0);
  const subtotal = activeLines.reduce((s, l) => s + priced(l) * (Number(l.quantity) || 1), 0)
    + (contractType === 'B' ? callOutCount * 80 : 0);
  const vat = subtotal * 0.2;
  const total = subtotal + vat;
  const unmatchedCount = activeLines.filter(l => !l.rate_card_id).length;

  const applyImport = (data) => {
    const mapped = (data.lines || []).map((l, i) => ({
      key: `imp-${i}-${Math.random().toString(36).slice(2)}`,
      name: l.description,
      equipment_type: l.source_code ? `Code: ${l.source_code}` : (l.rate_card_label || ''),
      serial_number: '',
      rate_card_id: l.rate_card_id,
      matched: l.matched,
      confidence: l.confidence,
      needs_review: l.needs_review,
      quantity: l.quantity || 1,
      unit_price: l.unit_price || 0,
      custom: !l.rate_card_id,
      included: true,
      imported: true,
    }));
    setLines(mapped);
    setImportNote(data.note || '');
    notify.success(`Recognised ${data.recognised_count} item(s) — ${data.matched_count} matched, ${data.needs_review_count} to review`);
    setStep(2);
  };

  const importSpreadsheet = async (file) => {
    if (!file) return;
    if (!siteId) { notify.error('Pick a MOD site first, then drop your kit list'); return; }
    setImporting(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('contract_type', contractType);
      fd.append('year', String(year));
      const r = await axios.post(`${API}/crm/mod-quote/import-spreadsheet`, fd, { headers: headers() });
      applyImport(r.data);
    } catch (e) { notify.error(e.response?.data?.detail || 'Could not read that file'); }
    setImporting(false);
  };

  const importPaste = async () => {
    if (!siteId) { notify.error('Pick a MOD site first, then paste your kit list'); return; }
    if (!pastedText.trim()) { notify.error('Paste some rows first'); return; }
    setImporting(true);
    try {
      const fd = new FormData();
      fd.append('pasted_text', pastedText);
      fd.append('contract_type', contractType);
      fd.append('year', String(year));
      const r = await axios.post(`${API}/crm/mod-quote/import-spreadsheet`, fd, { headers: headers() });
      applyImport(r.data);
    } catch (e) { notify.error(e.response?.data?.detail || 'Could not read that text'); }
    setImporting(false);
  };

  const generate = async () => {
    setGenerating(true);
    try {
      const payload = {
        site_id: siteId, site_name: site?.name || '', contract_type: contractType, year,
        call_out_count: contractType === 'B' ? Number(callOutCount) || 0 : 0,
        notes,
        lines: activeLines.filter(l => l.rate_card_id || l.custom || l.needs_review).map(l => ({
          equipment_id: l.equipment_id, rate_card_id: l.rate_card_id,
          quantity: Number(l.quantity) || 1, serial_number: l.serial_number,
          unit_price: Number(l.unit_price) || 0,
          description: (l.custom || l.imported) ? l.name : undefined,
        })),
      };
      const r = await axios.post(`${API}/crm/mod-quote/generate`, payload, { headers: headers() });
      notify.success(`MOD quote ${r.data.quote.quote_number} created${r.data.contract ? ' + service contract' : ''}`);
      onCreated && onCreated(r.data.quote.id);
    } catch (e) { notify.error(e.response?.data?.detail || 'Could not generate quote'); }
    setGenerating(false);
  };

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={onClose}>
      <div className="w-full max-w-3xl mx-4 rounded-xl shadow-2xl max-h-[92vh] overflow-hidden flex flex-col"
        style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', border: `1px solid ${c.border}` }}
        onClick={e => e.stopPropagation()} data-testid="mod-quote-wizard">
        {/* Header */}
        <div className="px-6 pt-5 pb-4 flex items-center justify-between border-b" style={{ borderColor: c.border }}>
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'var(--color-info-ios)15' }}>
              <ShieldCheck size={18} style={{ color: 'var(--color-info-ios)' }} />
            </div>
            <div>
              <h2 className="text-base font-semibold" style={{ color: c.text }}>MOD Auto Quote Writer</h2>
              <p className="text-[11px]" style={{ color: c.textDim }}>PTE Service &amp; Repair · Schedule of Rates</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => setShowRateCard(true)} className="flex items-center gap-1 px-2.5 py-1.5 text-[11px] rounded-md border"
              style={{ borderColor: c.border, color: c.textMuted }} data-testid="mod-open-rate-card">
              <Settings2 size={13} /> Rate Card
            </button>
            <button onClick={onClose} style={{ color: c.textDim }} data-testid="mod-quote-close"><X size={18} /></button>
          </div>
        </div>

        {/* Stepper */}
        <div className="flex items-center gap-2 px-6 py-3 text-[11px]" style={{ color: c.textDim }}>
          {['Contract & Site', 'Equipment & Pricing', 'Review & Generate'].map((s, i) => (
            <React.Fragment key={s}>
              <span className={step === i + 1 ? 'font-semibold' : ''} style={{ color: step >= i + 1 ? 'var(--color-info-ios)' : c.textDim }}>{i + 1}. {s}</span>
              {i < 2 && <ChevronRight size={12} />}
            </React.Fragment>
          ))}
        </div>

        <div className="px-6 pb-4 overflow-y-auto flex-1">
          {/* STEP 1 */}
          {step === 1 && (
            <div data-testid="mod-step-1">
              <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Contract Type</label>
              <div className="grid grid-cols-3 gap-2 mt-1 mb-4">
                {CONTRACTS.map(ct => (
                  <button key={ct.id} onClick={() => setContractType(ct.id)} data-testid={`mod-contract-${ct.id}`}
                    className="text-left p-3 rounded-lg border transition-all"
                    style={{ borderColor: contractType === ct.id ? 'var(--color-info-ios)' : c.border, background: contractType === ct.id ? 'var(--color-info-ios)10' : 'transparent' }}>
                    <p className="text-sm font-bold" style={{ color: c.text }}>{ct.title}</p>
                    <p className="text-[11px] font-medium" style={{ color: 'var(--color-info-ios)' }}>{ct.sub}</p>
                    <p className="text-[10px] mt-1" style={{ color: c.textDim }}>{ct.desc}</p>
                  </button>
                ))}
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>MOD Site / Estate</label>
                  <select value={siteId} onChange={e => setSiteId(e.target.value)} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={inputStyle} data-testid="mod-site-select">
                    <option value="">Select site…</option>
                    {sites.map(s => <option key={s.id} value={s.id}>{`${s.name} (${s.equipment_count} items)`}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Contract Year (pricing)</label>
                  <select value={year} onChange={e => setYear(Number(e.target.value))} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={inputStyle} data-testid="mod-year-select">
                    {[1, 2, 3, 4].map(y => <option key={y} value={y}>{`Year ${y}`}</option>)}
                  </select>
                </div>
              </div>
              {site && site.equipment_count === 0 && (
                <p className="mt-3 text-[11px] flex items-center gap-1" style={{ color: 'var(--color-warning)' }}>
                  <AlertTriangle size={12} /> This site has no equipment on record — you can still add POA/custom lines in the next step.
                </p>
              )}

              {/* Drag & drop spreadsheet import */}
              <div className="mt-5 pt-4 border-t" style={{ borderColor: c.border }}>
                <div className="flex items-center gap-2 mb-2">
                  <FileSpreadsheet size={14} style={{ color: 'var(--color-info-ios)' }} />
                  <p className="text-[11px] font-semibold" style={{ color: c.text }}>Or import from a spreadsheet</p>
                  <span className="text-[10px]" style={{ color: c.textDim }}>· MOD asset registers have no fixed layout — AI reads it for you</span>
                </div>
                {!siteId && (
                  <div className="mb-2 flex items-center gap-1.5 text-[10px] px-2 py-1.5 rounded-md" style={{ color: 'var(--color-warning)', background: 'var(--color-warning)12' }} data-testid="mod-import-site-required">
                    <AlertTriangle size={12} /> Choose a MOD site above before importing a kit list.
                  </div>
                )}
                <div
                  className="rounded-lg border-2 border-dashed p-5 text-center transition-all"
                  style={{ borderColor: dragOver && siteId ? 'var(--color-info-ios)' : c.border, background: dragOver && siteId ? 'var(--color-info-ios)10' : 'transparent', opacity: siteId ? 1 : 0.5, pointerEvents: siteId ? 'auto' : 'none' }}
                  aria-disabled={!siteId}
                  onDragOver={e => { e.preventDefault(); if (siteId) setDragOver(true); }}
                  onDragLeave={() => setDragOver(false)}
                  onDrop={e => { e.preventDefault(); setDragOver(false); if (!siteId) { notify.error('Pick a MOD site first, then drop your kit list'); return; } const f = e.dataTransfer.files?.[0]; if (f) importSpreadsheet(f); }}
                  data-testid="mod-import-dropzone">
                  {importing ? (
                    <div className="flex items-center justify-center gap-2 py-2" style={{ color: c.textMuted }}>
                      <Loader2 size={16} className="animate-spin" /> <span className="text-xs">Recognising machines, codes &amp; quantities…</span>
                    </div>
                  ) : (
                    <>
                      <Upload size={20} className="mx-auto mb-1.5" style={{ color: 'var(--color-info-ios)' }} />
                      <p className="text-xs font-medium" style={{ color: c.text }}>Drag &amp; drop your asset spreadsheet here</p>
                      <p className="text-[10px] mt-0.5" style={{ color: c.textDim }}>.xlsx, .xls or .csv · will be read as Contract Type {contractType}, Year {year}</p>
                      <div className="flex items-center justify-center gap-3 mt-2.5">
                        <label className="cursor-pointer px-3 py-1.5 text-[11px] rounded-md border inline-flex items-center gap-1"
                          style={{ borderColor: c.border, color: c.textMuted }} data-testid="mod-import-browse">
                          <input type="file" accept=".xlsx,.xls,.csv" className="hidden"
                            onChange={e => { const f = e.target.files?.[0]; if (f) importSpreadsheet(f); e.target.value = ''; }} />
                          Browse…
                        </label>
                        <button type="button" onClick={() => setPasteMode(v => !v)} className="text-[11px] underline" style={{ color: 'var(--color-info-ios)' }} data-testid="mod-import-paste-toggle">
                          or paste from Excel
                        </button>
                      </div>
                      {pasteMode && (
                        <div className="mt-3 text-left">
                          <textarea value={pastedText} onChange={e => setPastedText(e.target.value)} rows={4}
                            placeholder="Paste rows copied from Excel (Tab or comma separated)…"
                            className="w-full px-2 py-1.5 text-[11px] rounded-md" style={inputStyle} data-testid="mod-import-paste-text" />
                          <button type="button" onClick={importPaste} className="mt-2 btn-primary text-[11px]" data-testid="mod-import-paste-go">
                            <Sparkles size={12} /> Recognise &amp; Review
                          </button>
                        </div>
                      )}
                    </>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* STEP 2 */}
          {step === 2 && (
            <div data-testid="mod-step-2">
              {importNote && (
                <div className="mb-2 px-2.5 py-1.5 rounded-md text-[10px] flex items-start gap-1.5" style={{ background: 'var(--color-info-ios)10', color: c.textMuted }}>
                  <Sparkles size={11} className="mt-0.5 shrink-0" style={{ color: 'var(--color-info-ios)' }} />
                  <span><span className="font-semibold" style={{ color: c.text }}>AI import:</span> {importNote}</span>
                </div>
              )}
              <div className="flex items-center justify-between mb-2">
                <p className="text-xs" style={{ color: c.textDim }}>
                  <MapPin size={11} className="inline mr-0.5" />{site?.name} · Type {contractType} · Year {year}
                  {unmatchedCount > 0 && <span className="ml-2" style={{ color: 'var(--color-warning)' }}>{unmatchedCount} need mapping</span>}
                </p>
                <div className="flex gap-1.5">
                  {poaCard.map(p => (
                    <button key={p.id} onClick={() => addCustomLine(p.id)} className="flex items-center gap-1 px-2 py-1 text-[10px] rounded border" style={{ borderColor: c.border, color: c.textMuted }} data-testid={`mod-add-poa-${p.id}`}>
                      <Plus size={11} /> {p.equipment_type.split(' (')[0]}
                    </button>
                  ))}
                </div>
              </div>
              <div className="rounded-lg border overflow-hidden" style={{ borderColor: c.border }}>
                <table className="w-full text-xs">
                  <thead><tr style={{ color: c.textDim, background: isDark ? 'var(--color-neutral-950)' : 'var(--color-neutral-50)' }}>
                    <th className="text-left py-2 px-2">Equipment</th><th className="text-left">SOR Line</th><th className="w-14">Qty</th><th className="w-20 text-right">Unit £</th><th className="w-8"></th>
                  </tr></thead>
                  <tbody>
                    {lines.map(l => (
                      <tr key={l.key} style={{ borderTop: `1px solid ${c.border}`, opacity: l.included ? 1 : 0.4 }} data-testid={`mod-line-${l.key}`}>
                        <td className="py-1.5 px-2">
                          <div className="font-medium" style={{ color: c.text }}>{l.name}</div>
                          <div className="text-[10px]" style={{ color: c.textDim }}>
                            {l.equipment_type}{l.serial_number ? ` · ${l.serial_number}` : ''}
                            {l.matched
                              ? <span className="ml-1"><CheckCircle2 size={10} className="inline" style={{ color: 'var(--color-success-alt)' }} />{l.imported && l.confidence ? ` ${Math.round(l.confidence * 100)}% match` : ''}</span>
                              : <span className="ml-1" style={{ color: 'var(--color-warning)' }}>{l.imported ? 'needs review' : 'unmatched'}</span>}
                          </div>
                        </td>
                        <td>
                          <div className="flex items-center gap-1">
                            <select value={l.rate_card_id || ''} onChange={e => onSelectRateCard(l.key, e.target.value)}
                              className="w-full px-1.5 py-1 rounded text-[11px]" style={inputStyle} data-testid={`mod-line-select-${l.key}`}>
                              <option value="">— pick SOR line —</option>
                              {serviceCard.map(rc => <option key={rc.id} value={rc.id}>{rc.label}</option>)}
                            </select>
                            {!l.rate_card_id && (
                              <button onClick={() => aiSuggest(l)} disabled={aiBusyId === l.key} title="AI suggest"
                                className="p-1 rounded shrink-0" style={{ background: 'var(--color-accent-violet)15', color: 'var(--color-accent-violet)' }} data-testid={`mod-ai-${l.key}`}>
                                {aiBusyId === l.key ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
                              </button>
                            )}
                          </div>
                        </td>
                        <td className="text-center">
                          <input type="number" min="1" value={l.quantity} onChange={e => updateLine(l.key, { quantity: Number(e.target.value) || 1 })}
                            className="w-12 px-1 py-1 rounded text-center" style={inputStyle} />
                        </td>
                        <td className="text-right pr-2">
                          {(contractType === 'C' || (l.custom && !l.rate_card_id)) ? (
                            <input type="number" step="0.01" value={l.unit_price} onChange={e => updateLine(l.key, { unit_price: Number(e.target.value) || 0 })}
                              className="w-16 px-1 py-1 rounded text-right" style={inputStyle} data-testid={`mod-line-price-${l.key}`} />
                          ) : (
                            <span style={{ color: c.text }}>{l.rate_card_id ? fmt(priceFor(l.rate_card_id)) : '—'}</span>
                          )}
                        </td>
                        <td className="text-center">
                          <button onClick={() => removeLine(l.key)} style={{ color: c.textDim }} data-testid={`mod-line-remove-${l.key}`}><Trash2 size={13} /></button>
                        </td>
                      </tr>
                    ))}
                    {lines.length === 0 && <tr><td colSpan={5} className="text-center py-6" style={{ color: c.textDim }}>No lines — add a POA/custom line above.</td></tr>}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* STEP 3 */}
          {step === 3 && (
            <div data-testid="mod-step-3">
              <div className="p-3 rounded-lg mb-3" style={{ background: 'var(--color-info-ios)10', border: `1px solid var(--color-info-ios)30` }}>
                <p className="text-sm font-semibold" style={{ color: c.text }}>
                  MOD Contract Type {contractType} — {CONTRACTS.find(x => x.id === contractType).sub}
                </p>
                <p className="text-[11px]" style={{ color: c.textDim }}>{site?.name} · Year {year} · {activeLines.length} line(s)
                  {contractType === 'A' && <span className="ml-1" style={{ color: 'var(--color-success-alt)' }}>· will create a service contract → MOD Service Ops</span>}
                </p>
              </div>
              {contractType === 'B' && (
                <div className="mb-3">
                  <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>UK Call-Out Charges (£80 each)</label>
                  <input type="number" min="0" value={callOutCount} onChange={e => setCallOutCount(Number(e.target.value) || 0)}
                    className="w-24 mt-1 px-3 py-2 text-sm rounded-md block" style={inputStyle} data-testid="mod-callout-count" />
                </div>
              )}
              <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Notes (optional)</label>
              <textarea value={notes} onChange={e => setNotes(e.target.value)} rows={2}
                className="w-full mt-1 mb-3 px-3 py-2 text-sm rounded-md" style={inputStyle} data-testid="mod-notes" />
              <div className="p-3 rounded-lg" style={{ background: isDark ? 'var(--color-neutral-950)' : 'var(--color-neutral-50)' }}>
                <div className="flex justify-between text-sm" style={{ color: c.textMuted }}><span>Net</span><span>{fmt(subtotal)}</span></div>
                <div className="flex justify-between text-sm" style={{ color: c.textMuted }}><span>VAT (20%)</span><span>{fmt(vat)}</span></div>
                <div className="flex justify-between text-base font-bold mt-1 pt-1 border-t" style={{ color: c.text, borderColor: c.border }}><span>Total</span><span style={{ color: 'var(--color-success-alt)' }}>{fmt(total)}</span></div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t flex items-center justify-between" style={{ borderColor: c.border }}>
          <button onClick={() => step > 1 ? setStep(step - 1) : onClose()} className="flex items-center gap-1 px-3 py-2 text-xs rounded-md" style={{ color: c.textMuted }} data-testid="mod-back-btn">
            <ChevronLeft size={14} /> {step > 1 ? 'Back' : 'Cancel'}
          </button>
          {step === 1 && (
            <button onClick={loadEquipment} disabled={!siteId || loadingEq} className="btn-primary" data-testid="mod-next-1">
              {loadingEq ? <Loader2 size={14} className="animate-spin" /> : <ChevronRight size={14} />} Load Equipment
            </button>
          )}
          {step === 2 && (
            <button onClick={() => setStep(3)} disabled={activeLines.length === 0} className="btn-primary" data-testid="mod-next-2">
              Review <ChevronRight size={14} />
            </button>
          )}
          {step === 3 && (
            <button onClick={generate} disabled={generating} className="btn-primary" data-testid="mod-generate-btn">
              {generating ? <Loader2 size={14} className="animate-spin" /> : <FileText size={14} />} Generate Quote
            </button>
          )}
        </div>
      </div>

      {showRateCard && (
        <RateCardEditor API={API} headers={headers} c={c} isDark={isDark} rateCard={rateCard}
          onSaved={loadBase} onClose={() => setShowRateCard(false)} />
      )}
    </div>
  );
}
