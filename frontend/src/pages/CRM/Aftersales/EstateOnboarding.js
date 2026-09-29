/**
 * Aftersales Estate Onboarding — turn a messy inherited customer workbook
 * (e.g. Wiltshire Council: 707 assets, 17 sites, mixed makes, dirty serials)
 * into a clean Pulse estate + grouped draft contracts.
 *
 * Wizard: upload → map columns → review (dual pricing + exception queue) → commit.
 */
import { useState, useEffect } from 'react';
import axios from 'axios';
import {
  UploadCloud, FileSpreadsheet, RotateCw, AlertTriangle, CheckCircle2,
  ArrowRight, Building2, Wrench, X, CalendarClock, Loader2,
} from 'lucide-react';

const gbp = (v) => '£' + Number(v || 0).toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const CANON = [
  { id: 'site_code', label: 'Site code' },
  { id: 'site_name', label: 'Site name' },
  { id: 'description', label: 'Equipment description' },
  { id: 'make', label: 'Make' },
  { id: 'model', label: 'Model' },
  { id: 'serial', label: 'Serial number' },
  { id: 'install_date', label: 'Install date' },
  { id: 'warranty_end', label: 'Warranty end' },
  { id: 'warranty_status', label: 'Warranty status' },
  { id: 'contract_start', label: 'Contract start' },
  { id: 'annual_cost', label: 'Annual cost' },
  { id: 'monthly_cost', label: 'Monthly cost' },
  { id: 'notes', label: 'Notes' },
];

function Card({ children, c, isDark, className = '', testId }) {
  return (
    <div data-testid={testId} className={`p-4 rounded-xl border ${className}`}
      style={{ background: isDark ? '#111' : 'var(--color-neutral-50)', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
      {children}
    </div>
  );
}

export default function EstateOnboarding({ API, headers, c, isDark }) {
  const [step, setStep] = useState('upload'); // upload | map | review | done
  const [sourceType, setSourceType] = useState('spreadsheet'); // spreadsheet | pdf
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [file, setFile] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [importId, setImportId] = useState('');
  const [sheetName, setSheetName] = useState('');
  const [headerRow, setHeaderRow] = useState(2);
  const [colMap, setColMap] = useState({});
  const [customer, setCustomer] = useState('');
  const [tier, setTier] = useState('gold');
  const [grouping, setGrouping] = useState('per_site');
  const [review, setReview] = useState(null);
  const [exceptionsOnly, setExceptionsOnly] = useState(true);
  const [done, setDone] = useState(null);
  const [ppm, setPpm] = useState(null);

  // multi-file merge
  const [mergeSummary, setMergeSummary] = useState(null);
  const [mergeSources, setMergeSources] = useState([]);
  const [mergeScratch, setMergeScratch] = useState(null); // {import_id, sheets, column_map, ...}
  const [mergeSheet, setMergeSheet] = useState('');
  const [mergeHeaderRow, setMergeHeaderRow] = useState(2);
  const [mergeMap, setMergeMap] = useState({});

  const sheetMeta = analysis?.sheets?.find(s => s.name === sheetName);

  const doAnalyze = async () => {
    if (!file) return;
    setBusy(true); setErr('');
    try {
      const fd = new FormData();
      fd.append('file', file);
      const r = await axios.post(`${API}/crm/v2/aftersales/onboarding/analyze`, fd, { headers: headers() });
      setAnalysis(r.data);
      setImportId(r.data.import_id);
      setSheetName(r.data.suggested_sheet);
      setHeaderRow(r.data.suggested_header_row);
      setColMap(r.data.column_map || {});
      setStep('map');
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Could not read that file. Please upload an .xlsx workbook.');
    } finally { setBusy(false); }
  };

  const onSheetChange = (name) => {
    setSheetName(name);
    const m = analysis?.sheets?.find(s => s.name === name);
    if (m) setHeaderRow(m.header_row);
  };

  const doBuild = async () => {
    if (!customer.trim()) { setErr('Enter the customer name.'); return; }
    setBusy(true); setErr('');
    try {
      const r = await axios.post(`${API}/crm/v2/aftersales/onboarding/${importId}/build`, {
        sheet_name: sheetName, header_row: Number(headerRow),
        column_map: Object.fromEntries(Object.entries(colMap).map(([k, v]) => [k, Number(v)])),
        customer_name: customer.trim(), contract_type: tier, pricing_level: 'standard', grouping,
      }, { headers: headers() });
      setReview(r.data);
      setStep('review');
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Build failed. Check your column mapping.');
    } finally { setBusy(false); }
  };

  const patchRow = async (index, patch) => {
    try {
      const r = await axios.patch(`${API}/crm/v2/aftersales/onboarding/${importId}/rows`,
        { updates: [{ index, ...patch }] }, { headers: headers() });
      setReview(rv => ({ ...rv, summary: r.data.summary, rows: r.data.rows }));
    } catch { /* noop */ }
  };

  const doCommit = async () => {
    setBusy(true); setErr('');
    try {
      const r = await axios.post(`${API}/crm/v2/aftersales/onboarding/${importId}/commit`, {}, { headers: headers() });
      setDone(r.data.committed);
      setPpm(null);
      setStep('done');
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Commit failed.');
    } finally { setBusy(false); }
  };

  // Poll PPM backfill progress once the estate is committed (sites go live).
  useEffect(() => {
    if (step !== 'done' || !importId) return;
    let active = true;
    const poll = async () => {
      try {
        const r = await axios.get(`${API}/crm/v2/aftersales/onboarding/${importId}/ppm-status`, { headers: headers() });
        if (!active) return;
        setPpm(r.data);
        if (!r.data.all_done) setTimeout(poll, 2500);
      } catch { if (active) setTimeout(poll, 4000); }
    };
    poll();
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, importId]);

  const doAnalyzePdf = async () => {
    if (!file) return;
    if (!customer.trim()) { setErr('Enter the customer name for this invoice.'); return; }
    setBusy(true); setErr('');
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('customer_name', customer.trim());
      fd.append('contract_type', tier);
      fd.append('grouping', grouping);
      const r = await axios.post(`${API}/crm/v2/aftersales/onboarding/analyze-pdf`, fd, { headers: headers() });
      setImportId(r.data.import_id);
      setReview(r.data);
      setStep('review');
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Could not read that invoice. Try a clearer PDF or use the spreadsheet route.');
    } finally { setBusy(false); }
  };

  const reset = () => {
    setStep('upload'); setFile(null); setAnalysis(null); setImportId(''); setReview(null);
    setDone(null); setCustomer(''); setErr('');
    setMergeSummary(null); setMergeSources([]); setMergeScratch(null); setMergeMap({});
  };

  const startSession = async () => {
    if (!customer.trim()) { setErr('Enter the customer name.'); return; }
    setBusy(true); setErr('');
    try {
      const r = await axios.post(`${API}/crm/v2/aftersales/onboarding/session`,
        { customer_name: customer.trim(), contract_type: tier, grouping }, { headers: headers() });
      setImportId(r.data.import_id); setMergeSummary(r.data.summary); setMergeSources(r.data.sources || []);
    } catch (e) { setErr(e?.response?.data?.detail || 'Could not start the merge session.'); }
    finally { setBusy(false); }
  };

  const mergeAnalyzeSheet = async () => {
    if (!file) return;
    setBusy(true); setErr('');
    try {
      const fd = new FormData(); fd.append('file', file);
      const r = await axios.post(`${API}/crm/v2/aftersales/onboarding/analyze`, fd, { headers: headers() });
      setMergeScratch(r.data); setMergeSheet(r.data.suggested_sheet);
      setMergeHeaderRow(r.data.suggested_header_row); setMergeMap(r.data.column_map || {});
    } catch (e) { setErr(e?.response?.data?.detail || 'Could not read that spreadsheet.'); }
    finally { setBusy(false); }
  };

  const mergeAddSpreadsheet = async () => {
    setBusy(true); setErr('');
    try {
      const r = await axios.post(`${API}/crm/v2/aftersales/onboarding/${importId}/append-spreadsheet`, {
        source_import_id: mergeScratch.import_id, sheet_name: mergeSheet, header_row: Number(mergeHeaderRow),
        column_map: Object.fromEntries(Object.entries(mergeMap).map(([k, v]) => [k, Number(v)])),
      }, { headers: headers() });
      setMergeSummary(r.data.summary); setMergeSources(r.data.sources);
      setMergeScratch(null); setFile(null);
    } catch (e) { setErr(e?.response?.data?.detail || 'Could not add that spreadsheet.'); }
    finally { setBusy(false); }
  };

  const mergeAddPdf = async () => {
    if (!file) return;
    setBusy(true); setErr('');
    try {
      const fd = new FormData(); fd.append('file', file);
      const r = await axios.post(`${API}/crm/v2/aftersales/onboarding/${importId}/append-pdf`, fd, { headers: headers() });
      setMergeSummary(r.data.summary); setMergeSources(r.data.sources); setFile(null);
    } catch (e) { setErr(e?.response?.data?.detail || 'Could not read that invoice.'); }
    finally { setBusy(false); }
  };

  const removeMergeSource = async (sourceId) => {
    setBusy(true); setErr('');
    try {
      const r = await axios.delete(`${API}/crm/v2/aftersales/onboarding/${importId}/sources/${sourceId}`, { headers: headers() });
      setMergeSummary(r.data.summary); setMergeSources(r.data.sources);
    } catch (e) { setErr(e?.response?.data?.detail || 'Could not remove that file.'); }
    finally { setBusy(false); }
  };

  const goToMergeReview = async () => {
    setBusy(true); setErr('');
    try {
      const r = await axios.get(`${API}/crm/v2/aftersales/onboarding/${importId}`, { headers: headers() });
      setReview({ rows: r.data.rows || [], summary: r.data.summary, source: 'merged' });
      setStep('review');
    } catch (e) { setErr(e?.response?.data?.detail || 'Could not load the estate.'); }
    finally { setBusy(false); }
  };

  const stat = (label, val, testId, color) => (
    <div className="p-3 rounded-xl border" data-testid={testId}
      style={{ background: isDark ? '#0d0d0d' : '#fff', borderColor: c.border }}>
      <div className="text-xl font-extrabold" style={{ color: color || c.text }}>{val}</div>
      <div className="text-[11px] font-medium mt-0.5" style={{ color: c.textDim }}>{label}</div>
    </div>
  );

  return (
    <div data-testid="afs-onb">
      <div className="mb-3">
        <h2 className="text-lg font-bold flex items-center gap-2" style={{ color: c.text }}>
          <FileSpreadsheet size={18} style={{ color: 'var(--color-brand-cyan)' }} /> New-customer estate onboarding
        </h2>
        <p className="text-xs" style={{ color: c.textDim }}>
          Upload a messy inherited inventory or invoice. We map the columns, match equipment to the Pulse catalogue,
          show inherited cost vs Pulse price side-by-side, queue anything dirty for review, then build the customer,
          sites, equipment register and draft contracts. Nothing is created until you commit.
        </p>
      </div>

      {/* Stepper */}
      <div className="flex items-center gap-2 mb-4 text-xs" data-testid="afs-onb-steps">
        {['upload', 'map', 'review', 'done'].map((s, i) => (
          <div key={s} className="flex items-center gap-2">
            <span className="px-2.5 py-1 rounded-full font-semibold capitalize"
              style={step === s ? { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }
                : { background: 'transparent', color: c.textDim, border: `1px solid ${c.border}` }}>{i + 1}. {s}</span>
            {i < 3 && <ArrowRight size={12} style={{ color: c.textDim }} />}
          </div>
        ))}
      </div>

      {err && (
        <div data-testid="afs-onb-error" className="mb-4 p-3 rounded-lg text-sm flex items-center gap-2"
          style={{ background: 'rgba(239,68,68,0.1)', color: 'var(--color-danger, #EF4444)' }}>
          <AlertTriangle size={15} /> {err}
        </div>
      )}

      {/* STEP 1 — UPLOAD */}
      {step === 'upload' && (
        <Card c={c} isDark={isDark}>
          <div className="flex flex-wrap gap-2 mb-4" data-testid="afs-onb-source">
            {[['spreadsheet', 'Inventory spreadsheet', FileSpreadsheet], ['pdf', 'Invoice / agreement (PDF)', UploadCloud], ['merge', 'Merge multiple files', Building2]].map(([id, label, Icon]) => (
              <button key={id} data-testid={`afs-onb-source-${id}`}
                onClick={() => { setSourceType(id); setFile(null); setErr(''); }}
                className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium"
                style={sourceType === id
                  ? { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }
                  : { background: 'transparent', color: c.textDim, border: `1px solid ${c.border}` }}>
                <Icon size={14} /> {label}
              </button>
            ))}
          </div>

          {(sourceType === 'spreadsheet' || sourceType === 'pdf') && (
            <>
              {sourceType === 'pdf' && (
                <div className="grid md:grid-cols-3 gap-3 mb-4">
                  <div>
                    <label className="text-xs font-semibold block mb-1" style={{ color: c.textDim }}>Customer name</label>
                    <input data-testid="afs-onb-pdf-customer" value={customer} onChange={e => setCustomer(e.target.value)}
                      placeholder="e.g. Riverside Leisure Trust"
                      className="w-full px-3 py-2 rounded-lg text-sm" style={{ background: isDark ? '#0d0d0d' : '#fff', color: c.text, border: `1px solid ${c.border}` }} />
                  </div>
                  <div>
                    <label className="text-xs font-semibold block mb-1" style={{ color: c.textDim }}>Package tier</label>
                    <select data-testid="afs-onb-pdf-tier" value={tier} onChange={e => setTier(e.target.value)}
                      className="w-full px-3 py-2 rounded-lg text-sm" style={{ background: isDark ? '#0d0d0d' : '#fff', color: c.text, border: `1px solid ${c.border}` }}>
                      <option value="silver">Silver</option><option value="gold">Gold</option><option value="platinum">Platinum</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-xs font-semibold block mb-1" style={{ color: c.textDim }}>Group contracts by</label>
                    <select data-testid="afs-onb-pdf-grouping" value={grouping} onChange={e => setGrouping(e.target.value)}
                      className="w-full px-3 py-2 rounded-lg text-sm" style={{ background: isDark ? '#0d0d0d' : '#fff', color: c.text, border: `1px solid ${c.border}` }}>
                      <option value="master">One master contract</option>
                      <option value="per_site">One contract per site</option>
                      <option value="per_status">Split by Contract vs Warranty</option>
                    </select>
                  </div>
                </div>
              )}

              <label className="block p-8 rounded-xl border-2 border-dashed text-center cursor-pointer"
                style={{ borderColor: c.border }} data-testid="afs-onb-dropzone">
                <input type="file" accept={sourceType === 'pdf' ? '.pdf' : '.xlsx,.xls'} className="hidden" data-testid="afs-onb-file"
                  onChange={e => setFile(e.target.files?.[0] || null)} />
                <UploadCloud size={30} className="mx-auto mb-2" style={{ color: 'var(--color-brand-cyan)' }} />
                <p className="text-sm font-semibold" style={{ color: c.text }}>
                  {file ? file.name : (sourceType === 'pdf' ? 'Choose a prior invoice / agreement (.pdf)' : 'Choose an .xlsx inventory')}
                </p>
                <p className="text-xs mt-1" style={{ color: c.textDim }}>
                  {sourceType === 'pdf' ? 'AI reads what they currently pay — you review before anything is created' : 'Any layout — we detect the sheet and columns for you'}
                </p>
              </label>

              {sourceType === 'spreadsheet' ? (
                <button data-testid="afs-onb-analyze" onClick={doAnalyze} disabled={!file || busy}
                  className="mt-4 inline-flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold"
                  style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)', opacity: (!file || busy) ? 0.5 : 1 }}>
                  {busy ? <RotateCw size={15} className="animate-spin" /> : <ArrowRight size={15} />} Analyse file
                </button>
              ) : (
                <button data-testid="afs-onb-extract" onClick={doAnalyzePdf} disabled={!file || busy}
                  className="mt-4 inline-flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold"
                  style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)', opacity: (!file || busy) ? 0.5 : 1 }}>
                  {busy ? <RotateCw size={15} className="animate-spin" /> : <ArrowRight size={15} />} {busy ? 'Reading invoice…' : 'Extract invoice'}
                </button>
              )}
            </>
          )}

          {sourceType === 'merge' && (
            <div data-testid="afs-onb-merge">
              {!importId ? (
                <div className="grid md:grid-cols-3 gap-3">
                  <div>
                    <label className="text-xs font-semibold block mb-1" style={{ color: c.textDim }}>Customer name</label>
                    <input data-testid="afs-onb-merge-customer" value={customer} onChange={e => setCustomer(e.target.value)}
                      placeholder="e.g. Wiltshire Council"
                      className="w-full px-3 py-2 rounded-lg text-sm" style={{ background: isDark ? '#0d0d0d' : '#fff', color: c.text, border: `1px solid ${c.border}` }} />
                  </div>
                  <div>
                    <label className="text-xs font-semibold block mb-1" style={{ color: c.textDim }}>Package tier</label>
                    <select data-testid="afs-onb-merge-tier" value={tier} onChange={e => setTier(e.target.value)}
                      className="w-full px-3 py-2 rounded-lg text-sm" style={{ background: isDark ? '#0d0d0d' : '#fff', color: c.text, border: `1px solid ${c.border}` }}>
                      <option value="silver">Silver</option><option value="gold">Gold</option><option value="platinum">Platinum</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-xs font-semibold block mb-1" style={{ color: c.textDim }}>Group contracts by</label>
                    <select data-testid="afs-onb-merge-grouping" value={grouping} onChange={e => setGrouping(e.target.value)}
                      className="w-full px-3 py-2 rounded-lg text-sm" style={{ background: isDark ? '#0d0d0d' : '#fff', color: c.text, border: `1px solid ${c.border}` }}>
                      <option value="per_site">One contract per site</option>
                      <option value="master">One master contract</option>
                      <option value="per_status">Split by Contract vs Warranty</option>
                    </select>
                  </div>
                  <div className="md:col-span-3">
                    <button data-testid="afs-onb-merge-start" onClick={startSession} disabled={busy || !customer.trim()}
                      className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold"
                      style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)', opacity: (busy || !customer.trim()) ? 0.5 : 1 }}>
                      {busy ? <RotateCw size={15} className="animate-spin" /> : <ArrowRight size={15} />} Start merge for {customer.trim() || 'customer'}
                    </button>
                    <p className="text-xs mt-2" style={{ color: c.textDim }}>
                      Add several spreadsheets and/or invoices for one customer, then review and commit them as a single estate.
                      Big file? Split it and add the parts here.
                    </p>
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  {/* running totals */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    {stat('Assets so far', mergeSummary?.included || 0, 'afs-onb-merge-assets')}
                    {stat('Sites', mergeSummary?.sites || 0, 'afs-onb-merge-sites')}
                    {stat('Matched to Pulse', mergeSummary?.matched || 0, 'afs-onb-merge-matched', 'var(--color-success-alt)')}
                    {stat('Chosen annual', gbp(mergeSummary?.chosen_annual || 0), 'afs-onb-merge-annual', 'var(--color-brand-cyan)')}
                  </div>

                  {/* sources added */}
                  <div data-testid="afs-onb-merge-sources">
                    <p className="text-xs font-bold mb-1" style={{ color: c.textDim }}>Files added ({mergeSources.length})</p>
                    {mergeSources.length === 0
                      ? <p className="text-xs" style={{ color: c.textDim }}>No files added yet — add a spreadsheet or invoice below.</p>
                      : mergeSources.map((s, i) => (
                        <div key={i} className="flex justify-between items-center gap-2 text-xs py-0.5" style={{ color: c.text }} data-testid={`afs-onb-merge-source-${i}`}>
                          <span className="truncate">{s.type === 'invoice_pdf' ? '📄' : '📊'} {s.filename || 'file'}</span>
                          <span className="flex items-center gap-2 shrink-0">
                            <span style={{ color: c.textDim }}>{s.rows} assets</span>
                            <button data-testid={`afs-onb-merge-remove-${i}`} onClick={() => removeMergeSource(s.source_id)} disabled={busy}
                              title="Remove this file" aria-label="Remove this file"
                              className="p-1 rounded hover:bg-black/10 disabled:opacity-40" style={{ color: 'var(--color-danger, #EF4444)' }}>
                              <X size={13} />
                            </button>
                          </span>
                        </div>
                      ))}
                  </div>

                  {/* add another file */}
                  <div className="p-3 rounded-lg border" style={{ borderColor: c.border }}>
                    <label className="block p-4 rounded-lg border-2 border-dashed text-center cursor-pointer mb-2"
                      style={{ borderColor: c.border }}>
                      <input type="file" accept=".xlsx,.xls,.pdf" className="hidden" data-testid="afs-onb-merge-file"
                        onChange={e => { setFile(e.target.files?.[0] || null); setMergeScratch(null); }} />
                      <p className="text-xs font-semibold" style={{ color: c.text }}>{file ? file.name : 'Add a spreadsheet or invoice (.xlsx / .pdf)'}</p>
                    </label>
                    {file && /\.pdf$/i.test(file.name) && (
                      <button data-testid="afs-onb-merge-add-pdf" onClick={mergeAddPdf} disabled={busy}
                        className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-semibold"
                        style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)', opacity: busy ? 0.5 : 1 }}>
                        {busy ? <RotateCw size={14} className="animate-spin" /> : <ArrowRight size={14} />} {busy ? 'Reading invoice…' : 'Add invoice to estate'}
                      </button>
                    )}
                    {file && !/\.pdf$/i.test(file.name) && !mergeScratch && (
                      <button data-testid="afs-onb-merge-analyze" onClick={mergeAnalyzeSheet} disabled={busy}
                        className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-semibold"
                        style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)', opacity: busy ? 0.5 : 1 }}>
                        {busy ? <RotateCw size={14} className="animate-spin" /> : <ArrowRight size={14} />} Analyse &amp; map
                      </button>
                    )}
                    {mergeScratch && (
                      <div className="mt-2">
                        <div className="flex items-center gap-2 mb-2">
                          <span className="text-xs" style={{ color: c.textDim }}>Sheet</span>
                          <select data-testid="afs-onb-merge-sheet" value={mergeSheet}
                            onChange={e => { setMergeSheet(e.target.value); const m = mergeScratch.sheets?.find(s => s.name === e.target.value); if (m) setMergeHeaderRow(m.header_row); }}
                            className="px-2 py-1 rounded text-xs" style={{ background: isDark ? '#0d0d0d' : '#fff', color: c.text, border: `1px solid ${c.border}` }}>
                            {mergeScratch.sheets.map(s => <option key={s.name} value={s.name}>{s.name} ({s.n_rows})</option>)}
                          </select>
                        </div>
                        <div className="grid sm:grid-cols-2 gap-1.5 mb-2">
                          {CANON.map(f => (
                            <div key={f.id} className="flex items-center gap-2">
                              <span className="text-[11px] w-28 shrink-0" style={{ color: c.textDim }}>{f.label}</span>
                              <select data-testid={`afs-onb-merge-map-${f.id}`} value={mergeMap[f.id] ?? ''}
                                onChange={e => setMergeMap(m => { const n = { ...m }; if (e.target.value === '') delete n[f.id]; else n[f.id] = Number(e.target.value); return n; })}
                                className="flex-1 px-2 py-1 rounded text-[11px]" style={{ background: isDark ? '#0d0d0d' : '#fff', color: c.text, border: `1px solid ${c.border}` }}>
                                <option value="">— not in file —</option>
                                {((mergeScratch.sheets.find(s => s.name === mergeSheet) || {}).headers || []).map((h, i) => <option key={i} value={i}>{h || `Column ${i + 1}`}</option>)}
                              </select>
                            </div>
                          ))}
                        </div>
                        <button data-testid="afs-onb-merge-add-sheet" onClick={mergeAddSpreadsheet} disabled={busy}
                          className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-semibold"
                          style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)', opacity: busy ? 0.5 : 1 }}>
                          {busy ? <RotateCw size={14} className="animate-spin" /> : <ArrowRight size={14} />} Add to estate
                        </button>
                      </div>
                    )}
                  </div>

                  <button data-testid="afs-onb-merge-review" onClick={goToMergeReview} disabled={busy || (mergeSummary?.included || 0) === 0}
                    className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-semibold"
                    style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)', opacity: (busy || (mergeSummary?.included || 0) === 0) ? 0.5 : 1 }}>
                    <ArrowRight size={15} /> Review estate ({mergeSummary?.included || 0} assets)
                  </button>
                </div>
              )}
            </div>
          )}
        </Card>
      )}

      {/* STEP 2 — MAP */}
      {step === 'map' && analysis && (
        <div className="space-y-4">
          <Card c={c} isDark={isDark}>
            <div className="grid md:grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-semibold block mb-1" style={{ color: c.textDim }}>Customer name</label>
                <input data-testid="afs-onb-customer" value={customer} onChange={e => setCustomer(e.target.value)}
                  placeholder="e.g. Wiltshire Council"
                  className="w-full px-3 py-2 rounded-lg text-sm" style={{ background: isDark ? '#0d0d0d' : '#fff', color: c.text, border: `1px solid ${c.border}` }} />
              </div>
              <div>
                <label className="text-xs font-semibold block mb-1" style={{ color: c.textDim }}>Sheet</label>
                <select data-testid="afs-onb-sheet" value={sheetName} onChange={e => onSheetChange(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg text-sm" style={{ background: isDark ? '#0d0d0d' : '#fff', color: c.text, border: `1px solid ${c.border}` }}>
                  {analysis.sheets.map(s => <option key={s.name} value={s.name}>{s.name} ({s.n_rows} rows)</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs font-semibold block mb-1" style={{ color: c.textDim }}>Package tier</label>
                <select data-testid="afs-onb-tier" value={tier} onChange={e => setTier(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg text-sm" style={{ background: isDark ? '#0d0d0d' : '#fff', color: c.text, border: `1px solid ${c.border}` }}>
                  <option value="silver">Silver</option><option value="gold">Gold</option><option value="platinum">Platinum</option>
                </select>
              </div>
              <div>
                <label className="text-xs font-semibold block mb-1" style={{ color: c.textDim }}>Group contracts by</label>
                <select data-testid="afs-onb-grouping" value={grouping} onChange={e => setGrouping(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg text-sm" style={{ background: isDark ? '#0d0d0d' : '#fff', color: c.text, border: `1px solid ${c.border}` }}>
                  <option value="per_site">One contract per site</option>
                  <option value="master">One master contract</option>
                  <option value="per_status">Split by Contract vs Warranty</option>
                </select>
              </div>
            </div>
          </Card>

          <Card c={c} isDark={isDark}>
            <p className="text-sm font-bold mb-1" style={{ color: c.text }}>Column mapping</p>
            <p className="text-xs mb-3" style={{ color: c.textDim }}>Auto-detected from your headers — adjust any that look wrong. Header row: {headerRow}.</p>
            <div className="grid sm:grid-cols-2 gap-2">
              {CANON.map(f => (
                <div key={f.id} className="flex items-center gap-2">
                  <span className="text-xs w-32 shrink-0" style={{ color: c.textDim }}>{f.label}</span>
                  <select data-testid={`afs-onb-map-${f.id}`} value={colMap[f.id] ?? ''}
                    onChange={e => setColMap(m => { const n = { ...m }; if (e.target.value === '') delete n[f.id]; else n[f.id] = Number(e.target.value); return n; })}
                    className="flex-1 px-2 py-1.5 rounded-lg text-xs" style={{ background: isDark ? '#0d0d0d' : '#fff', color: c.text, border: `1px solid ${c.border}` }}>
                    <option value="">— not in file —</option>
                    {(sheetMeta?.headers || []).map((h, i) => <option key={i} value={i}>{h || `Column ${i + 1}`}</option>)}
                  </select>
                </div>
              ))}
            </div>
            <button data-testid="afs-onb-build" onClick={doBuild} disabled={busy}
              className="mt-4 inline-flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold"
              style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)', opacity: busy ? 0.5 : 1 }}>
              {busy ? <RotateCw size={15} className="animate-spin" /> : <ArrowRight size={15} />} Match &amp; price
            </button>
          </Card>
        </div>
      )}

      {/* STEP 3 — REVIEW */}
      {step === 'review' && review && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3" data-testid="afs-onb-summary">
            {stat('Assets', review.summary.included, 'afs-onb-s-assets')}
            {stat('Sites', review.summary.sites, 'afs-onb-s-sites')}
            {stat('Matched to Pulse', review.summary.matched, 'afs-onb-s-matched', 'var(--color-success-alt)')}
            {stat('Needs review', review.summary.exceptions_total, 'afs-onb-s-exceptions', review.summary.exceptions_total ? 'var(--color-warning-alt, #F59E0B)' : c.text)}
            {stat('Inherited annual', gbp(review.summary.inherited_annual), 'afs-onb-s-inherited')}
            {stat('Pulse annual', gbp(review.summary.pulse_annual), 'afs-onb-s-pulse', 'var(--color-brand-cyan)')}
            {stat('Chosen annual', gbp(review.summary.chosen_annual), 'afs-onb-s-chosen', 'var(--color-success-alt)')}
            {stat('On contract / Warranty', `${review.summary.on_contract} / ${review.summary.under_warranty}`, 'afs-onb-s-status')}
          </div>

          <Card c={c} isDark={isDark} testId="afs-onb-exceptions">
            <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
              <p className="text-sm font-bold" style={{ color: c.text }}>Review queue</p>
              <label className="flex items-center gap-2 text-xs" style={{ color: c.textDim }}>
                <input type="checkbox" data-testid="afs-onb-exc-toggle" checked={exceptionsOnly} onChange={e => setExceptionsOnly(e.target.checked)} />
                Exceptions only
              </label>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr style={{ color: c.textDim }} className="text-left">
                    <th className="py-1 pr-2">Incl</th><th className="pr-2">Site</th><th className="pr-2">Equipment</th>
                    <th className="pr-2">Match</th><th className="pr-2">Serial</th>
                    <th className="pr-2 text-right">Inherited</th><th className="pr-2 text-right">Pulse</th>
                    <th className="pr-2">Use</th><th>Flags</th>
                  </tr>
                </thead>
                <tbody>
                  {(review.rows || []).filter(r => !exceptionsOnly || r.exceptions.length).slice(0, 200).map(r => (
                    <tr key={r.index} data-testid={`afs-onb-row-${r.index}`} className="border-t" style={{ borderColor: c.border, color: c.text }}>
                      <td className="py-1 pr-2">
                        <input type="checkbox" data-testid={`afs-onb-incl-${r.index}`} checked={r.include}
                          onChange={e => patchRow(r.index, { include: e.target.checked })} />
                      </td>
                      <td className="pr-2">{r.clean.site_name}</td>
                      <td className="pr-2">{r.clean.description || r.clean.model}</td>
                      <td className="pr-2">
                        {r.match.pricing_status === 'MATCHED'
                          ? <span style={{ color: 'var(--color-success-alt)' }}>{r.match.matched_code}</span>
                          : <span style={{ color: 'var(--color-warning-alt, #F59E0B)' }}>{r.match.pricing_status === 'RRP_REQUIRED' ? 'no price' : 'unmatched'}</span>}
                      </td>
                      <td className="pr-2">
                        {r.exceptions.includes('missing_serial')
                          ? <input data-testid={`afs-onb-serial-${r.index}`} defaultValue="" placeholder="add serial"
                              onBlur={e => e.target.value.trim() && patchRow(r.index, { serial: e.target.value.trim() })}
                              className="w-24 px-1.5 py-0.5 rounded" style={{ background: isDark ? '#0d0d0d' : '#fff', color: c.text, border: `1px solid ${c.border}` }} />
                          : r.clean.serial}
                      </td>
                      <td className="pr-2 text-right">
                        {r.inherited.annual != null ? gbp(r.inherited.annual)
                          : <input data-testid={`afs-onb-cost-${r.index}`} type="number" placeholder="cost"
                              onBlur={e => e.target.value && patchRow(r.index, { annual_cost: Number(e.target.value) })}
                              className="w-20 px-1.5 py-0.5 rounded text-right" style={{ background: isDark ? '#0d0d0d' : '#fff', color: c.text, border: `1px solid ${c.border}` }} />}
                      </td>
                      <td className="pr-2 text-right">{r.pulse.annual > 0 ? gbp(r.pulse.annual) : '—'}</td>
                      <td className="pr-2">
                        <select data-testid={`afs-onb-use-${r.index}`} value={r.chosen_price}
                          onChange={e => patchRow(r.index, { chosen_price: e.target.value })}
                          className="px-1.5 py-0.5 rounded" style={{ background: isDark ? '#0d0d0d' : '#fff', color: c.text, border: `1px solid ${c.border}` }}>
                          <option value="inherited">Inherited</option>
                          <option value="pulse" disabled={r.pulse.annual <= 0}>Pulse</option>
                        </select>
                      </td>
                      <td>
                        {r.exceptions.map(x => (
                          <span key={x} className="inline-block px-1.5 py-0.5 rounded mr-1 mb-1 text-[10px]"
                            style={{ background: 'rgba(245,158,11,0.15)', color: 'var(--color-warning-alt, #F59E0B)' }}>{x.replace(/_/g, ' ')}</span>
                        ))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {(review.rows || []).filter(r => !exceptionsOnly || r.exceptions.length).length > 200 && (
                <p className="text-xs mt-2" style={{ color: c.textDim }}>Showing first 200 rows. Commit imports every included row.</p>
              )}
            </div>
          </Card>

          <div className="flex items-center gap-3">
            <button data-testid="afs-onb-commit" onClick={doCommit} disabled={busy}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-semibold"
              style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)', opacity: busy ? 0.5 : 1 }}>
              {busy ? <RotateCw size={15} className="animate-spin" /> : <CheckCircle2 size={15} />}
              Create estate &amp; draft contracts
            </button>
            <button onClick={() => setStep(review.source === 'invoice_pdf' ? 'upload' : 'map')} className="text-xs font-medium" style={{ color: c.textDim }}>
              {review.source === 'invoice_pdf' ? 'Start over' : 'Back to mapping'}
            </button>
          </div>
        </div>
      )}

      {/* STEP 4 — DONE */}
      {step === 'done' && done && (
        <Card c={c} isDark={isDark} testId="afs-onb-done">
          <div className="flex items-center gap-2 mb-3">
            <CheckCircle2 size={20} style={{ color: 'var(--color-success-alt)' }} />
            <p className="text-base font-bold" style={{ color: c.text }}>Estate imported</p>
          </div>
          <div className="grid grid-cols-3 gap-3 mb-4">
            {stat('Sites', done.sites, 'afs-onb-done-sites')}
            {stat('Equipment', done.equipment, 'afs-onb-done-equipment')}
            {stat('Draft contracts', done.contracts.length, 'afs-onb-done-contracts', 'var(--color-brand-cyan)')}
          </div>
          <p className="text-xs font-bold mb-1.5" style={{ color: c.textDim }}>Draft contracts created</p>
          <div className="space-y-1 mb-4">
            {done.contracts.map(ct => (
              <div key={ct.id} className="flex justify-between text-xs" style={{ color: c.text }}>
                <span>{ct.contract_number} · {ct.title}</span>
                <span style={{ color: c.textDim }}>{ct.assets} assets · {gbp(ct.annual_value)}/yr</span>
              </div>
            ))}
          </div>
          {/* PPM auto-load progress — sites go live at commit, schedules build in the background */}
          {ppm && ppm.total_sites > 0 && (
            <div data-testid="afs-onb-ppm-progress" className="p-3 rounded-lg border mb-3"
              style={{ background: isDark ? '#0d0d0d' : 'var(--color-neutral-50)', borderColor: c.border }}>
              <div className="flex items-center gap-2 mb-1.5">
                {ppm.all_done
                  ? <CalendarClock size={16} style={{ color: 'var(--color-success-alt)' }} />
                  : <Loader2 size={16} className="animate-spin" style={{ color: 'var(--color-brand-cyan)' }} />}
                <p className="text-xs font-bold" style={{ color: c.text }}>
                  {ppm.all_done
                    ? `PPM schedules loaded — ${ppm.schedules_created} schedule${ppm.schedules_created === 1 ? '' : 's'} across ${ppm.total_sites} site${ppm.total_sites === 1 ? '' : 's'}`
                    : `Loading PPM schedules… ${ppm.finished_sites}/${ppm.total_sites} sites`}
                </p>
              </div>
              <div className="h-1.5 rounded-full overflow-hidden" style={{ background: c.border }}>
                <div className="h-full rounded-full transition-all"
                  style={{ width: `${ppm.total_sites ? Math.round((ppm.finished_sites / ppm.total_sites) * 100) : 0}%`,
                           background: ppm.all_done ? 'var(--color-success-alt)' : 'var(--color-brand-cyan)' }} />
              </div>
              {ppm.failed_sites > 0 && (
                <p className="text-xs mt-1.5" style={{ color: 'var(--color-danger-alt, #ef4444)' }}>
                  {ppm.failed_sites} site{ppm.failed_sites === 1 ? '' : 's'} failed to generate — retry from the PPM calendar.
                </p>
              )}
            </div>
          )}
          <p className="text-xs mb-3" style={{ color: c.textDim }}>
            Find these under <strong>Contracts &amp; Renewals</strong> as drafts, and the equipment under the new customer's register.
            Review and activate them to switch on service schedules, billing and compliance.
          </p>
          <button data-testid="afs-onb-restart" onClick={reset}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold"
            style={{ background: 'transparent', color: c.text, border: `1px solid ${c.border}` }}>
            <Building2 size={14} /> Import another customer
          </button>
        </Card>
      )}
    </div>
  );
}
