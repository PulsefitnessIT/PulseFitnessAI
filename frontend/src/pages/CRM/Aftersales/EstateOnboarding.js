/**
 * Aftersales Estate Onboarding — turn a messy inherited customer workbook
 * (e.g. Wiltshire Council: 707 assets, 17 sites, mixed makes, dirty serials)
 * into a clean Pulse estate + grouped draft contracts.
 *
 * Wizard: upload → map columns → review (dual pricing + exception queue) → commit.
 */
import { useState } from 'react';
import axios from 'axios';
import {
  UploadCloud, FileSpreadsheet, RotateCw, AlertTriangle, CheckCircle2,
  ArrowRight, Building2, Wrench,
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
      setStep('done');
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Commit failed.');
    } finally { setBusy(false); }
  };

  const reset = () => {
    setStep('upload'); setFile(null); setAnalysis(null); setImportId(''); setReview(null);
    setDone(null); setCustomer(''); setErr('');
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
          <label className="block p-8 rounded-xl border-2 border-dashed text-center cursor-pointer"
            style={{ borderColor: c.border }} data-testid="afs-onb-dropzone">
            <input type="file" accept=".xlsx,.xls" className="hidden" data-testid="afs-onb-file"
              onChange={e => setFile(e.target.files?.[0] || null)} />
            <UploadCloud size={30} className="mx-auto mb-2" style={{ color: 'var(--color-brand-cyan)' }} />
            <p className="text-sm font-semibold" style={{ color: c.text }}>{file ? file.name : 'Choose an .xlsx inventory / invoice'}</p>
            <p className="text-xs mt-1" style={{ color: c.textDim }}>Any layout — we detect the sheet and columns for you</p>
          </label>
          <button data-testid="afs-onb-analyze" onClick={doAnalyze} disabled={!file || busy}
            className="mt-4 inline-flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold"
            style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)', opacity: (!file || busy) ? 0.5 : 1 }}>
            {busy ? <RotateCw size={15} className="animate-spin" /> : <ArrowRight size={15} />} Analyse file
          </button>
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
            <button onClick={() => setStep('map')} className="text-xs font-medium" style={{ color: c.textDim }}>Back to mapping</button>
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
