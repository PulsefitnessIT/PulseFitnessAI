/**
 * CRM · Master Price List — spreadsheet migration wizard (Phase 1).
 *
 * Zero-data-loss import: Upload → Worksheets & Mapping → Preview →
 * Commit → Summary. Every unmapped column is preserved against the
 * product; every product is traceable to its source sheet + row.
 *
 * Backend: routes/crm_price_list.py (prefix /api/crm/price-list).
 */
import { useCallback, useMemo, useState } from 'react';
import axios from 'axios';
import {
  Upload, Loader2, X, Check, ChevronRight, ChevronLeft, Sparkles, Wand2,
  FileSpreadsheet, AlertTriangle, CheckCircle2, Database,
} from 'lucide-react';

const STEPS = ['Upload', 'Worksheets & mapping', 'Preview', 'Done'];

export default function CRMPriceListImportWizard({ API, headers, c, isDark, onClose, onDone }) {
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [imp, setImp] = useState(null);            // import doc
  const [fields, setFields] = useState([]);         // canonical fields
  const [selected, setSelected] = useState({});     // { sheetName: bool }
  const [mappings, setMappings] = useState({});     // { sheetName: { colIdx: fieldKey } }
  const [aiBusy, setAiBusy] = useState('');         // sheet name being suggested
  const [preview, setPreview] = useState(null);
  const [options, setOptions] = useState({ mode: 'live', version_label: '', create: true, update: true });
  const [result, setResult] = useState(null);
  const [aiSummary, setAiSummary] = useState(null);
  const [aiSummaryBusy, setAiSummaryBusy] = useState(false);
  const [uploadPct, setUploadPct] = useState(0);

  const CHUNK_SIZE = 512 * 1024;          // 512 KB slices
  const SINGLE_MAX = 1.2 * 1024 * 1024;   // files under this go in one request

  const surface = isDark ? 'var(--color-surface-dark-1)' : '#fff';
  const surface2 = isDark ? 'var(--color-surface-dark-2)' : '#fff';
  const border = isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)';

  const applyUploadResult = (data) => {
    const im = data.import;
    setImp(im);
    setFields(data.canonical_fields || []);
    const sel = {}; const maps = {};
    (im.sheets || []).forEach(s => {
      sel[s.name] = true;
      maps[s.name] = { ...(s.auto_mapping || {}) };
    });
    setSelected(sel); setMappings(maps);
    setStep(1);
  };

  const uploadChunked = async (file) => {
    const uploadId = (crypto.randomUUID && crypto.randomUUID()) || `${Date.now()}-${Math.random()}`;
    const total = Math.ceil(file.size / CHUNK_SIZE);
    for (let i = 0; i < total; i++) {
      const fd = new FormData();
      fd.append('upload_id', uploadId);
      fd.append('chunk_index', String(i));
      fd.append('total_chunks', String(total));
      fd.append('filename', file.name);
      fd.append('chunk', file.slice(i * CHUNK_SIZE, (i + 1) * CHUNK_SIZE), file.name);
      await axios.post(`${API}/crm/price-list/import/upload-chunk`, fd, {
        headers: { ...headers(), 'Content-Type': 'multipart/form-data' },
      });
      setUploadPct(Math.round(((i + 1) / total) * 100));
    }
    const r = await axios.post(`${API}/crm/price-list/import/upload-finalize`, { upload_id: uploadId }, { headers: headers() });
    return r.data;
  };

  const onUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true); setError(''); setUploadPct(0);
    try {
      let data;
      if (file.size > SINGLE_MAX) {
        data = await uploadChunked(file);
      } else {
        const fd = new FormData();
        fd.append('file', file);
        const r = await axios.post(`${API}/crm/price-list/import/upload`, fd, {
          headers: { ...headers(), 'Content-Type': 'multipart/form-data' },
        });
        data = r.data;
      }
      applyUploadResult(data);
    } catch (err) {
      setError(err?.response?.data?.detail || 'Upload failed');
    }
    setBusy(false); setUploadPct(0);
    e.target.value = '';
  };

  const setMap = (sheet, colIdx, field) => {
    setMappings(m => ({ ...m, [sheet]: { ...(m[sheet] || {}), [colIdx]: field || undefined } }));
  };

  const aiSuggest = async (sheet) => {
    setAiBusy(sheet); setError('');
    try {
      const r = await axios.post(`${API}/crm/price-list/import/${imp.id}/suggest-mapping`, { sheet }, { headers: headers() });
      setMappings(m => ({ ...m, [sheet]: { ...(r.data.mapping || {}) } }));
    } catch (err) {
      setError('AI suggestion unavailable — heuristic mapping kept.');
    }
    setAiBusy('');
  };

  const aiAnalyze = async (sheet) => {
    setAiBusy(`layout:${sheet}`); setError('');
    try {
      const r = await axios.post(`${API}/crm/price-list/import/${imp.id}/ai-analyze`, { sheet }, { headers: headers() });
      const updated = r.data.sheet;
      setImp(prev => ({ ...prev, sheets: (prev.sheets || []).map(s => s.name === sheet ? updated : s) }));
      setMappings(m => ({ ...m, [sheet]: { ...(r.data.mapping || {}) } }));
    } catch (err) {
      setError(err?.response?.data?.detail || 'AI layout detection unavailable — adjust the header row manually.');
    }
    setAiBusy('');
  };

  const buildSheetCfgs = useCallback(() => (imp?.sheets || [])
    .filter(s => selected[s.name])
    .map(s => ({
      name: s.name, header_row: s.header_row, header_band: s.header_band,
      code_col: s.code_col, name_col: s.name_col,
      mappings: Object.fromEntries(Object.entries(mappings[s.name] || {}).filter(([, v]) => v)),
      selected: true,
    })), [imp, selected, mappings]);

  const runPreview = async () => {
    setBusy(true); setError(''); setAiSummary(null);
    try {
      const r = await axios.post(`${API}/crm/price-list/import/${imp.id}/preview`, { sheets: buildSheetCfgs() }, { headers: headers() });
      setPreview(r.data.preview);
      setStep(2);
    } catch (err) {
      setError(err?.response?.data?.detail || 'Preview failed');
    }
    setBusy(false);
  };

  const runAiSummary = async () => {
    setAiSummaryBusy(true);
    try {
      const r = await axios.post(`${API}/crm/price-list/import/ai-error-summary`, { preview }, { headers: headers() });
      setAiSummary(r.data);
    } catch (err) {
      setAiSummary({ summary: err?.response?.data?.detail || 'AI summary is unavailable — please review the rows below manually.', flagged: [], next_steps: [], severity: 'info' });
    }
    setAiSummaryBusy(false);
  };

  const [commitJob, setCommitJob] = useState(null);   // background commit progress

  const runCommit = async () => {
    setBusy(true); setError(''); setCommitJob(null);
    const sheets = buildSheetCfgs();
    try {
      if (selectedCount > 2000) {
        await runCommitAsync(sheets);
      } else {
        const r = await axios.post(`${API}/crm/price-list/import/${imp.id}/commit`, { sheets, options }, { headers: headers() });
        setResult(r.data);
        setStep(3);
        setBusy(false);
      }
    } catch (err) {
      setError(err?.response?.data?.detail || 'Import failed');
      setBusy(false);
    }
  };

  const runCommitAsync = async (sheets) => {
    const start = await axios.post(`${API}/crm/price-list/import/${imp.id}/commit-async`, { sheets, options }, { headers: headers() });
    const jobId = start.data.job_id;
    setCommitJob({ status: 'running', processed: 0, total: start.data.total });
    const poll = async () => {
      try {
        const r = await axios.get(`${API}/crm/price-list/import/commit-jobs/${jobId}`, { headers: headers() });
        const job = r.data;
        setCommitJob(job);
        if (job.status === 'done') {
          setResult({ version: { label: job.version_label, status: job.version_status }, summary: { created: job.created, updated: job.updated, skipped: job.skipped } });
          setStep(3); setBusy(false); return;
        }
        if (job.status === 'error') {
          setError(job.message || 'Background import failed'); setBusy(false); return;
        }
        setTimeout(poll, 1500);
      } catch (err) {
        setError('Lost contact with the import job — check Import history.'); setBusy(false);
      }
    };
    setTimeout(poll, 1200);
  };

  const selectedCount = useMemo(() => (imp?.sheets || []).filter(s => selected[s.name]).reduce((a, s) => a + s.product_count, 0), [imp, selected]);

  const fieldSelect = (sheet, col) => (
    <select
      value={(mappings[sheet] || {})[col.index] || ''}
      onChange={e => setMap(sheet, col.index, e.target.value)}
      className="w-full px-2 py-1 text-xs rounded border"
      style={{ background: surface2, borderColor: border, color: c.text }}
      data-testid={`plw-map-${sheet.replace(/\s+/g, '-')}-${col.index}`}
    >
      <option value="">— keep as imported data —</option>
      {fields.map(f => <option key={f.key} value={f.key}>{f.label}</option>)}
    </select>
  );

  return (
    <div className="fixed inset-0 z-[260] flex items-center justify-center bg-black/50 backdrop-blur-sm p-3" data-testid="price-list-import-wizard">
      <div className="w-full max-w-4xl max-h-[92vh] flex flex-col rounded-2xl shadow-2xl border" style={{ background: surface, borderColor: border }}>
        {/* Header + stepper */}
        <div className="flex items-center justify-between px-5 py-3 border-b" style={{ borderColor: border }}>
          <h3 className="text-sm font-semibold flex items-center gap-2" style={{ color: c.text }}>
            <FileSpreadsheet size={15} /> Import master price list
          </h3>
          <button type="button" onClick={onClose} className="opacity-60 hover:opacity-100" data-testid="plw-close"><X size={16} /></button>
        </div>
        <div className="flex items-center gap-1 px-5 py-2 border-b text-[11px]" style={{ borderColor: border }}>
          {STEPS.map((s, i) => (
            <div key={s} className="flex items-center gap-1">
              <span className="inline-flex items-center justify-center w-5 h-5 rounded-full font-semibold"
                style={{ background: i <= step ? 'var(--color-info-ios)' : surface2, color: i <= step ? '#fff' : c.textDim, border: `1px solid ${border}` }}>
                {i < step ? <Check size={11} /> : i + 1}
              </span>
              <span style={{ color: i === step ? c.text : c.textDim, fontWeight: i === step ? 600 : 400 }}>{s}</span>
              {i < STEPS.length - 1 && <ChevronRight size={12} className="opacity-40 mx-1" />}
            </div>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {error && (
            <div className="mb-3 px-3 py-2 rounded-md text-xs flex items-center gap-2" style={{ background: 'rgba(239,68,68,0.08)', color: 'var(--color-danger-alt)' }} data-testid="plw-error">
              <AlertTriangle size={13} /> {error}
            </div>
          )}

          {/* STEP 0 — Upload */}
          {step === 0 && (
            <div className="text-center py-8">
              <input type="file" accept=".xlsx,.xls,.csv" onChange={onUpload} className="hidden" id="plw-file" data-testid="plw-file-input" />
              <label htmlFor="plw-file" className="cursor-pointer inline-flex flex-col items-center gap-3 px-8 py-10 rounded-xl border-2 border-dashed" style={{ borderColor: border, color: c.textMuted }}>
                {busy ? <Loader2 size={28} className="animate-spin" /> : <Upload size={28} />}
                <span className="text-sm font-semibold" style={{ color: c.text }} data-testid="plw-upload-status">{busy ? (uploadPct > 0 ? `Uploading… ${uploadPct}%` : 'Reading spreadsheet…') : 'Choose an XLSX or CSV file'}</span>
                <span className="text-xs">Every worksheet, row and cell is preserved — nothing is lost. Large files are uploaded in chunks.</span>
              </label>
            </div>
          )}

          {/* STEP 1 — Worksheets & mapping */}
          {step === 1 && imp && (
            <div className="space-y-4" data-testid="plw-mapping-step">
              <p className="text-xs" style={{ color: c.textDim }}>
                <strong style={{ color: c.text }}>{imp.filename}</strong> · {imp.total_detected_rows} product rows across {imp.sheets.length} worksheet(s).
                Map columns to CRM fields — anything left as <em>imported data</em> is still saved against each product.
              </p>
              {imp.sheets.map(s => (
                <div key={s.name} className="rounded-lg border" style={{ borderColor: border }}>
                  <div className="flex items-center justify-between px-3 py-2 border-b" style={{ borderColor: border, background: surface2 }}>
                    <label className="flex items-center gap-2 text-xs font-semibold cursor-pointer" style={{ color: c.text }}>
                      <input type="checkbox" checked={!!selected[s.name]} onChange={e => setSelected(v => ({ ...v, [s.name]: e.target.checked }))} data-testid={`plw-sheet-select-${s.name.replace(/\s+/g, '-')}`} />
                      {s.name} <span className="font-normal" style={{ color: c.textDim }}>· {s.product_count} rows · {s.max_col} cols · hdr row {s.header_row}{s.has_code ? '' : ' · name-keyed'}</span>
                      {typeof s.confidence === 'number' && (
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-bold" data-testid={`plw-confidence-${s.name.replace(/\s+/g, '-')}`}
                          style={{ background: s.confidence >= 70 ? 'rgba(34,197,94,0.15)' : s.confidence >= 40 ? 'rgba(245,158,11,0.15)' : 'rgba(239,68,68,0.15)', color: s.confidence >= 70 ? 'var(--color-success-alt)' : s.confidence >= 40 ? 'var(--color-accent-amber)' : 'var(--color-danger-alt)' }}>
                          {s.confidence}% match
                        </span>
                      )}
                    </label>
                    <div className="flex items-center gap-1.5">
                      <button type="button" onClick={() => aiAnalyze(s.name)} disabled={!!aiBusy} className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-1 rounded border disabled:opacity-50" style={{ borderColor: border, color: 'var(--color-accent-amber)' }} data-testid={`plw-ai-analyze-${s.name.replace(/\s+/g, '-')}`}>
                        {aiBusy === `layout:${s.name}` ? <Loader2 size={11} className="animate-spin" /> : <Wand2 size={11} />} AI auto-detect layout
                      </button>
                      <button type="button" onClick={() => aiSuggest(s.name)} disabled={!!aiBusy} className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-1 rounded border disabled:opacity-50" style={{ borderColor: border, color: 'var(--color-info-ios)' }} data-testid={`plw-ai-suggest-${s.name.replace(/\s+/g, '-')}`}>
                        {aiBusy === s.name ? <Loader2 size={11} className="animate-spin" /> : <Sparkles size={11} />} AI suggest fields
                      </button>
                    </div>
                  </div>
                  {(s.warnings || []).length > 0 && (
                    <div className="px-3 py-1.5 text-[11px] border-b" style={{ borderColor: border, color: 'var(--color-accent-amber)' }} data-testid={`plw-warnings-${s.name.replace(/\s+/g, '-')}`}>
                      {s.warnings.map((w, i) => <div key={i}>⚠ {w}</div>)}
                      {s.ai_note ? <div style={{ color: c.textDim }}>AI: {s.ai_note}</div> : null}
                    </div>
                  )}
                  {selected[s.name] && (
                    <div className="max-h-56 overflow-y-auto">
                      <table className="w-full text-xs">
                        <thead style={{ background: surface2 }}>
                          <tr style={{ color: c.textDim }}>
                            <th className="text-left px-3 py-1.5 font-semibold w-16">Col</th>
                            <th className="text-left px-3 py-1.5 font-semibold">Spreadsheet column</th>
                            <th className="text-left px-3 py-1.5 font-semibold w-40">Example</th>
                            <th className="text-left px-3 py-1.5 font-semibold w-56">Map to CRM field</th>
                          </tr>
                        </thead>
                        <tbody>
                          {s.columns.map(col => (
                            <tr key={col.index} className="border-t" style={{ borderColor: border }}>
                              <td className="px-3 py-1.5 font-mono" style={{ color: c.textDim }}>{col.letter}</td>
                              <td className="px-3 py-1.5" style={{ color: c.text }}>{col.label}</td>
                              <td className="px-3 py-1.5 truncate" style={{ color: c.textDim, maxWidth: 160 }}>{(s.sample[0]?.cells || {})[col.label] || '—'}</td>
                              <td className="px-3 py-1.5">{fieldSelect(s.name, col)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* STEP 2 — Preview */}
          {step === 2 && preview && (
            <div className="space-y-4" data-testid="plw-preview-step">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                {[
                  ['Total rows', preview.total, c.text],
                  ['Ready', preview.ready, 'var(--color-success-alt)'],
                  ['Warnings', preview.warnings, 'var(--color-accent-amber)'],
                  ['Errors', preview.errors, 'var(--color-danger-alt)'],
                  ['New products', preview.new, c.text],
                  ['Will update', preview.updates, c.text],
                  ['Preserved cells', preview.unmapped_columns_total, 'var(--color-info-ios)'],
                  ['Missing Sage code', preview.missing_sage, c.textMuted],
                ].map(([label, val, col]) => (
                  <div key={label} className="rounded-lg border px-3 py-2" style={{ borderColor: border, background: surface2 }}>
                    <div className="text-lg font-bold" style={{ color: col }} data-testid={`plw-stat-${label.replace(/\s+/g, '-').toLowerCase()}`}>{val}</div>
                    <div className="text-[10px] uppercase tracking-wide" style={{ color: c.textDim }}>{label}</div>
                  </div>
                ))}
              </div>

              {/* Import options */}
              <div className="rounded-lg border p-3 space-y-2" style={{ borderColor: border }}>
                <div className="text-xs font-semibold" style={{ color: c.text }}>Import options</div>
                <div className="flex flex-wrap items-center gap-3 text-xs" style={{ color: c.textMuted }}>
                  <label className="flex items-center gap-1.5">Version
                    <select value={options.mode} onChange={e => setOptions(o => ({ ...o, mode: e.target.value }))} className="px-2 py-1 rounded border" style={{ background: surface2, borderColor: border, color: c.text }} data-testid="plw-mode">
                      <option value="live">Publish as LIVE</option>
                      <option value="draft">Save as draft</option>
                    </select>
                  </label>
                  <input value={options.version_label} onChange={e => setOptions(o => ({ ...o, version_label: e.target.value }))} placeholder="Version label (optional)" className="flex-1 min-w-[160px] px-2 py-1 rounded border" style={{ background: surface2, borderColor: border, color: c.text }} data-testid="plw-version-label" />
                  <label className="flex items-center gap-1.5"><input type="checkbox" checked={options.create} onChange={e => setOptions(o => ({ ...o, create: e.target.checked }))} /> Create new</label>
                  <label className="flex items-center gap-1.5"><input type="checkbox" checked={options.update} onChange={e => setOptions(o => ({ ...o, update: e.target.checked }))} /> Update existing</label>
                </div>
              </div>

              {/* AI error summary */}
              {(preview.warnings > 0 || preview.errors > 0) && (
                <div className="rounded-lg border" style={{ borderColor: border }} data-testid="plw-ai-summary-block">
                  <div className="flex items-center justify-between px-3 py-1.5 border-b" style={{ borderColor: border }}>
                    <span className="text-xs font-semibold flex items-center gap-1.5" style={{ color: c.text }}><Sparkles size={12} style={{ color: 'var(--color-info-ios)' }} /> AI explain issues</span>
                    {!aiSummary && (
                      <button type="button" onClick={runAiSummary} disabled={aiSummaryBusy}
                        className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-1 rounded border disabled:opacity-50"
                        style={{ borderColor: border, color: 'var(--color-info-ios)' }} data-testid="plw-ai-summary-btn">
                        {aiSummaryBusy ? <Loader2 size={11} className="animate-spin" /> : <Sparkles size={11} />} Summarise
                      </button>
                    )}
                  </div>
                  {aiSummary && (
                    <div className="px-3 py-2 space-y-2 text-xs" data-testid="plw-ai-summary-result">
                      <p style={{ color: c.text }}>{aiSummary.summary}</p>
                      {(aiSummary.flagged || []).length > 0 && (
                        <div>
                          <div className="text-[10px] uppercase tracking-wide mb-1" style={{ color: c.textDim }}>Worst rows</div>
                          {aiSummary.flagged.map((f, i) => (
                            <div key={i} className="flex items-center gap-2 py-0.5">
                              <span style={{ color: c.textDim }}>{f.sheet} · row {f.row}{f.code ? ` · ${f.code}` : ''}</span>
                              <span style={{ color: 'var(--color-accent-amber)' }}>— {f.reason}</span>
                            </div>
                          ))}
                        </div>
                      )}
                      {(aiSummary.next_steps || []).length > 0 && (
                        <ul className="list-disc pl-4" style={{ color: c.textMuted }}>
                          {aiSummary.next_steps.map((s, i) => <li key={i}>{s}</li>)}
                        </ul>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* Issues */}
              {preview.issues?.length > 0 && (
                <div className="rounded-lg border" style={{ borderColor: border }}>
                  <div className="px-3 py-1.5 text-xs font-semibold border-b" style={{ color: c.text, borderColor: border }}>Rows to review ({preview.issues.length})</div>
                  <div className="max-h-44 overflow-y-auto text-xs">
                    {preview.issues.map((iss, i) => (
                      <div key={i} className="flex items-center gap-2 px-3 py-1 border-t" style={{ borderColor: border }}>
                        <span style={{ color: iss.level === 'error' ? 'var(--color-danger-alt)' : 'var(--color-accent-amber)' }}>{iss.level}</span>
                        <span style={{ color: c.textDim }}>{iss.sheet} · row {iss.row} {iss.code ? `· ${iss.code}` : ''}</span>
                        <span style={{ color: c.textMuted }}>— {iss.msg}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {/* Background commit progress */}
              {commitJob && commitJob.status === 'running' && (
                <div className="rounded-lg border p-3" style={{ borderColor: 'var(--color-info-ios)' }} data-testid="plw-commit-progress">
                  <div className="flex items-center justify-between text-xs font-semibold mb-2" style={{ color: c.text }}>
                    <span className="flex items-center gap-1.5"><Loader2 size={12} className="animate-spin" style={{ color: 'var(--color-info-ios)' }} /> Importing in the background…</span>
                    <span data-testid="plw-commit-progress-count">{commitJob.processed || 0} / {commitJob.total || selectedCount}</span>
                  </div>
                  <div className="h-2 rounded-full overflow-hidden" style={{ background: surface2 }}>
                    <div className="h-full rounded-full transition-all" style={{ width: `${Math.min(100, Math.round(((commitJob.processed || 0) / Math.max(1, commitJob.total || selectedCount)) * 100))}%`, background: 'var(--color-info-ios)' }} />
                  </div>
                  <div className="text-[11px] mt-2" style={{ color: c.textDim }}>You'll get an email when it's done — it's safe to keep this open.</div>
                </div>
              )}
            </div>
          )}
          {step === 3 && result && (
            <div className="text-center py-10" data-testid="plw-done-step">
              <CheckCircle2 size={40} className="mx-auto mb-3" style={{ color: 'var(--color-success-alt)' }} />
              <div className="text-base font-semibold" style={{ color: c.text }}>Price list imported</div>
              <div className="text-xs mt-1" style={{ color: c.textDim }}>Version <strong>{result.version?.label}</strong> · {result.version?.status}</div>
              <div className="flex items-center justify-center gap-4 mt-5 text-sm">
                <div><div className="text-2xl font-bold" style={{ color: 'var(--color-success-alt)' }}>{result.summary?.created}</div><div className="text-[10px] uppercase" style={{ color: c.textDim }}>created</div></div>
                <div><div className="text-2xl font-bold" style={{ color: c.text }}>{result.summary?.updated}</div><div className="text-[10px] uppercase" style={{ color: c.textDim }}>updated</div></div>
                <div><div className="text-2xl font-bold" style={{ color: c.textMuted }}>{result.summary?.skipped}</div><div className="text-[10px] uppercase" style={{ color: c.textDim }}>skipped</div></div>
              </div>
              <p className="text-xs mt-5 inline-flex items-center gap-1.5" style={{ color: c.textDim }}><Database size={12} /> Every column was preserved — manage everything in CRM from now on.</p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-5 py-3 border-t" style={{ borderColor: border }}>
          <button type="button" onClick={() => step > 0 && step < 3 ? setStep(step - 1) : onClose()} className="inline-flex items-center gap-1 text-xs font-semibold px-3 py-1.5 rounded-md" style={{ color: c.textMuted }} data-testid="plw-back">
            {step > 0 && step < 3 ? <><ChevronLeft size={13} /> Back</> : 'Close'}
          </button>
          <div className="flex items-center gap-2">
            {step === 1 && <span className="text-[11px]" style={{ color: c.textDim }}>{selectedCount} rows selected</span>}
            {step === 1 && (
              <button type="button" onClick={runPreview} disabled={busy || selectedCount === 0} className="inline-flex items-center gap-1.5 text-xs font-semibold px-4 py-1.5 rounded-md text-white disabled:opacity-50" style={{ background: 'var(--color-info-ios)' }} data-testid="plw-to-preview">
                {busy ? <Loader2 size={13} className="animate-spin" /> : <>Preview <ChevronRight size={13} /></>}
              </button>
            )}
            {step === 2 && (
              <button type="button" onClick={runCommit} disabled={busy} className="inline-flex items-center gap-1.5 text-xs font-semibold px-4 py-1.5 rounded-md text-white disabled:opacity-50" style={{ background: 'var(--color-success-alt)' }} data-testid="plw-commit">
                {busy ? <Loader2 size={13} className="animate-spin" /> : <><Check size={13} /> Import {preview?.total} products</>}
              </button>
            )}
            {step === 3 && (
              <button type="button" onClick={() => { onDone?.(); onClose(); }} className="inline-flex items-center gap-1.5 text-xs font-semibold px-4 py-1.5 rounded-md text-white" style={{ background: 'var(--color-info-ios)' }} data-testid="plw-finish">
                Done
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
