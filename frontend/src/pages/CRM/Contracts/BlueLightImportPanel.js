import { useState, useRef } from 'react';
import axios from 'axios';
import {
  UploadCloud, Download, AlertTriangle, CheckCircle2, FileSpreadsheet,
  ClipboardPaste, Loader2, MapPin, Gauge, Copy, XCircle, Save, Wand2, Sparkles,
} from 'lucide-react';
import Button from '@/components/shared/Button';

function Tile({ label, value, color, testId }) {
  return (
    <div data-testid={testId} className="text-center px-3 py-2 rounded-lg min-w-[84px]" style={{ background: 'var(--color-bg)' }}>
      <div className="text-xl font-bold" style={{ color: color || 'var(--color-text)' }}>{value}</div>
      <div className="text-[10px] leading-tight mt-0.5" style={{ color: 'var(--color-text-muted)' }}>{label}</div>
    </div>
  );
}

export default function BlueLightImportPanel({ API, headers, contractId, c, onImported }) {
  const [mode, setMode] = useState('upload');
  const [file, setFile] = useState(null);
  const [pasteText, setPasteText] = useState('');
  const [defaultStation, setDefaultStation] = useState('');
  const [skipDuplicates, setSkipDuplicates] = useState(true);
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [columnMap, setColumnMap] = useState({});
  const [saveName, setSaveName] = useState('');
  const [savingLayout, setSavingLayout] = useState(false);
  const [savedName, setSavedName] = useState('');
  const fileRef = useRef(null);

  const base = `${API}/crm/v2/contracts/${contractId}/blue-light/import`;

  const downloadTemplate = async () => {
    try {
      const res = await axios.get(`${API}/crm/v2/blue-light/import/template.csv`,
        { headers: headers(), responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a');
      a.href = url; a.download = 'blue-light-import-template.csv';
      document.body.appendChild(a); a.click(); a.remove();
      window.URL.revokeObjectURL(url);
    } catch { setError('Could not download the template. Please try again.'); }
  };

  const runPreview = async (overrideMap = null) => {
    setError(''); setResult(null);
    if (mode === 'upload' && !file) { setError('Choose a CSV or Excel file first.'); return; }
    if (mode === 'paste' && !pasteText.trim()) { setError('Paste some rows first.'); return; }
    setLoading(true);
    try {
      const fd = new FormData();
      if (mode === 'upload') fd.append('file', file);
      else fd.append('text', pasteText);
      if (defaultStation.trim()) fd.append('default_station', defaultStation.trim());
      if (overrideMap) fd.append('mapping', JSON.stringify(overrideMap));
      const res = await axios.post(`${base}/preview`, fd, { headers: headers() });
      setPreview(res.data);
      const cm = {};
      (res.data.meta?.columns || []).forEach(col => { cm[col.header] = col.field || ''; });
      setColumnMap(cm);
      setSavedName(res.data.meta?.saved?.name || '');
      setSaveName('');
    } catch (e) {
      setError(e?.response?.data?.detail || 'Could not read that spreadsheet. Check the columns and try again.');
    } finally { setLoading(false); }
  };

  const saveLayout = async () => {
    if (!saveName.trim() || !preview?.meta?.signature) return;
    setSavingLayout(true); setError('');
    try {
      await axios.post(`${API}/crm/v2/blue-light/import/mappings`,
        { name: saveName.trim(), signature: preview.meta.signature, columns: columnMap },
        { headers: headers() });
      setSavedName(saveName.trim()); setSaveName('');
    } catch (e) {
      setError(e?.response?.data?.detail || 'Could not save the layout.');
    } finally { setSavingLayout(false); }
  };

  const runCommit = async () => {
    if (!preview) return;
    setCommitting(true); setError('');
    try {
      const res = await axios.post(`${base}/commit`,
        { rows: preview.rows, skip_duplicates: skipDuplicates }, { headers: headers() });
      setResult(res.data);
      setPreview(null); setFile(null); setPasteText('');
      if (fileRef.current) fileRef.current.value = '';
      onImported && onImported();
    } catch (e) {
      setError(e?.response?.data?.detail || 'Import failed. Please try again.');
    } finally { setCommitting(false); }
  };

  const reset = () => { setPreview(null); setResult(null); setError(''); };

  const counts = preview?.counts;
  const willCreate = counts ? counts.assets_valid - (skipDuplicates ? counts.assets_duplicate : 0) : 0;

  return (
    <div className="rounded-xl border p-4 space-y-4" style={{ borderColor: c.border, background: 'var(--color-surface)' }} data-testid="bl-import-panel">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2 text-sm font-bold" style={{ color: c.text }}>
          <FileSpreadsheet size={15} style={{ color: 'var(--color-info-ios)' }} /> Import Stations &amp; Assets
        </div>
        <Button variant="ghost" size="sm" icon={Download} onClick={downloadTemplate} data-testid="bl-import-template">
          Download template
        </Button>
      </div>
      <p className="text-[12px]" style={{ color: c.textMuted }}>
        Upload your equipment spreadsheet (CSV or Excel) — each machine on a row, with a
        <span className="font-semibold"> location</span> column (or one worksheet tab per station).
        You&apos;ll see a full validation summary and any duplicate warnings before anything is created.
      </p>

      {/* Result banner */}
      {result && (
        <div className="rounded-lg border p-3 flex items-start gap-2" data-testid="bl-import-result"
          style={{ borderColor: 'var(--color-success-alt)', background: 'var(--color-success-alt)11' }}>
          <CheckCircle2 size={18} style={{ color: 'var(--color-success-alt)' }} className="mt-0.5" />
          <div className="text-sm" style={{ color: c.text }}>
            Imported <b>{result.assets_created}</b> assets across <b>{result.stations_created}</b> new
            station{result.stations_created === 1 ? '' : 's'}
            {result.stations_matched ? <> (plus <b>{result.stations_matched}</b> matched existing)</> : null}.
            {result.assets_skipped ? <> <b>{result.assets_skipped}</b> duplicate{result.assets_skipped === 1 ? '' : 's'} skipped.</> : null}
            {' '}<b>{result.treadmills}</b> treadmills detected for calibration.
            <button className="ml-2 underline" onClick={reset} data-testid="bl-import-again">Import another</button>
          </div>
        </div>
      )}

      {error && (
        <div className="rounded-lg border p-2.5 flex items-center gap-2 text-sm" data-testid="bl-import-error"
          style={{ borderColor: 'var(--color-danger)', color: 'var(--color-danger)', background: 'var(--color-danger)11' }}>
          <XCircle size={15} /> {error}
        </div>
      )}

      {/* Input area — hidden once a preview is showing */}
      {!preview && !result && (
        <div className="space-y-3">
          <div className="flex gap-2">
            <Button variant={mode === 'upload' ? 'primary' : 'ghost'} size="sm" icon={UploadCloud}
              onClick={() => setMode('upload')} data-testid="bl-import-mode-upload">Upload file</Button>
            <Button variant={mode === 'paste' ? 'primary' : 'ghost'} size="sm" icon={ClipboardPaste}
              onClick={() => setMode('paste')} data-testid="bl-import-mode-paste">Paste rows</Button>
          </div>

          {mode === 'upload' ? (
            <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls" data-testid="bl-import-file"
              onChange={e => { setFile(e.target.files?.[0] || null); setError(''); }}
              className="block w-full text-sm rounded-lg border px-3 py-2"
              style={{ borderColor: c.border, color: c.text, background: 'var(--color-bg)' }} />
          ) : (
            <textarea data-testid="bl-import-paste" rows={6} value={pasteText}
              onChange={e => setPasteText(e.target.value)}
              placeholder="Paste rows copied from Excel or Sheets (include the header row)…"
              className="block w-full text-sm rounded-lg border px-3 py-2 font-mono"
              style={{ borderColor: c.border, color: c.text, background: 'var(--color-bg)' }} />
          )}

          <div className="flex items-center gap-2">
            <label className="text-[12px] whitespace-nowrap" style={{ color: c.textMuted }}>Default station (optional):</label>
            <input data-testid="bl-import-default-station" value={defaultStation}
              onChange={e => setDefaultStation(e.target.value)} placeholder="Used when a row has no location"
              className="flex-1 text-sm rounded-lg border px-3 py-1.5"
              style={{ borderColor: c.border, color: c.text, background: 'var(--color-bg)' }} />
          </div>

          <Button onClick={() => runPreview()} disabled={loading} icon={loading ? Loader2 : FileSpreadsheet} data-testid="bl-import-preview-btn">
            {loading ? 'Reading…' : 'Preview import'}
          </Button>
        </div>
      )}

      {/* Preview / validation summary */}
      {preview && counts && (
        <div className="space-y-3" data-testid="bl-import-preview">
          {preview.meta?.columns?.length > 0 && (
            <div className="rounded-lg border p-3 space-y-2" data-testid="bl-import-mapping"
              style={{ borderColor: c.border, background: 'var(--color-bg)' }}>
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <div className="flex items-center gap-1.5 text-[12px] font-semibold" style={{ color: c.text }}>
                  <Wand2 size={13} style={{ color: 'var(--color-info-ios)' }} /> Column mapping
                </div>
                {(savedName || preview.meta?.saved) && (
                  <span className="flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full" data-testid="bl-import-saved-badge"
                    style={{ background: 'var(--color-info-ios)22', color: 'var(--color-info-ios)' }}>
                    <Sparkles size={11} /> Using saved layout: {savedName || preview.meta.saved.name}
                  </span>
                )}
              </div>
              <div className="grid gap-1.5" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))' }}>
                {preview.meta.columns.map((col, i) => {
                  const cur = columnMap[col.header] ?? '';
                  const labels = preview.meta.field_labels || {};
                  const autoOnly = cur && !labels[cur];
                  const AUTO = { mod_code: 'MOD code', quantity: 'Quantity', category: 'Category', console_serial: 'Console serial' };
                  return (
                    <div key={col.header} className="flex items-center gap-2 text-[12px] rounded-md border px-2 py-1"
                      style={{ borderColor: c.border, background: 'var(--color-surface)' }}>
                      <span className="truncate flex-1 font-mono" title={col.header} style={{ color: c.textMuted }}>{col.header}</span>
                      <span style={{ color: 'var(--color-text-faint-alt)' }}>→</span>
                      <select data-testid={`bl-import-map-${i}`} value={cur}
                        onChange={e => setColumnMap(m => ({ ...m, [col.header]: e.target.value }))}
                        className="text-[12px] rounded-md border px-1.5 py-1 flex-1 min-w-0"
                        style={{ borderColor: c.border, color: c.text, background: 'var(--color-bg)' }}>
                        <option value="">— Ignore —</option>
                        {autoOnly && <option value={cur}>{(AUTO[cur] || cur)} (auto)</option>}
                        {Object.entries(labels).map(([f, l]) => (
                          <option key={f} value={f}>{l}</option>
                        ))}
                      </select>
                    </div>
                  );
                })}
              </div>
              <div className="flex items-center gap-2 flex-wrap pt-1">
                <Button size="sm" variant="secondary" icon={Wand2} onClick={() => runPreview(columnMap)} disabled={loading} data-testid="bl-import-remap-btn">
                  Re-check with these columns
                </Button>
                <div className="flex items-center gap-1.5">
                  <input data-testid="bl-import-layout-name" value={saveName} onChange={e => setSaveName(e.target.value)}
                    placeholder="Name this layout" className="text-[12px] rounded-md border px-2 py-1"
                    style={{ borderColor: c.border, color: c.text, background: 'var(--color-surface)' }} />
                  <Button size="sm" variant="ghost" icon={savingLayout ? Loader2 : Save} onClick={saveLayout}
                    disabled={savingLayout || !saveName.trim()} data-testid="bl-import-save-layout">
                    Save layout
                  </Button>
                </div>
              </div>
              {preview.meta?.missing_required?.length > 0 && (
                <div className="text-[11px]" data-testid="bl-import-missing" style={{ color: 'var(--color-accent-amber)' }}>
                  Map a column for: {preview.meta.missing_required.map(x => x === 'station_name' ? 'Station / Location' : 'Equipment details').join(', ')}
                </div>
              )}
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            <Tile label="Stations (new)" value={counts.stations_new} color="var(--color-success-alt-2)" testId="bl-import-count-stations-new" />
            <Tile label="Stations (existing)" value={counts.stations_existing} testId="bl-import-count-stations-existing" />
            <Tile label="Assets" value={counts.assets_valid} color="var(--color-info-ios)" testId="bl-import-count-assets" />
            <Tile label="Treadmills" value={counts.treadmills} color="var(--color-accent-violet)" testId="bl-import-count-treadmills" />
            <Tile label="Duplicates" value={counts.assets_duplicate} color={counts.assets_duplicate ? 'var(--color-accent-amber)' : undefined} testId="bl-import-count-duplicates" />
            <Tile label="No serial" value={counts.assets_blank_serial} color={counts.assets_blank_serial ? 'var(--color-accent-amber)' : undefined} testId="bl-import-count-blank" />
          </div>

          {/* Per-station breakdown */}
          <div className="rounded-lg border divide-y" style={{ borderColor: c.border }} data-testid="bl-import-stations">
            {preview.stations.map((s, i) => (
              <div key={i} className="flex items-center justify-between px-3 py-1.5 text-sm" data-testid={`bl-import-station-${i}`}>
                <span className="flex items-center gap-1.5 min-w-0" style={{ color: c.text }}>
                  <MapPin size={13} style={{ color: 'var(--color-info-ios)' }} />
                  <span className="truncate">{s.name}</span>
                  {s.exists
                    ? <span className="text-[10px] px-1.5 rounded-full" style={{ background: 'var(--color-text-faint-alt)22', color: 'var(--color-text-muted)' }}>existing</span>
                    : <span className="text-[10px] px-1.5 rounded-full" style={{ background: 'var(--color-success-alt-2)22', color: 'var(--color-success-alt-2)' }}>new</span>}
                </span>
                <span className="text-[12px] flex items-center gap-3 flex-shrink-0" style={{ color: c.textMuted }}>
                  <span>{s.asset_count} assets</span>
                  {s.treadmill_count > 0 && <span className="flex items-center gap-1"><Gauge size={12} />{s.treadmill_count}</span>}
                </span>
              </div>
            ))}
          </div>

          {/* Errors (blocking rows) */}
          {preview.errors?.length > 0 && (
            <div className="rounded-lg border p-2.5 text-[12px]" data-testid="bl-import-errors"
              style={{ borderColor: 'var(--color-danger)', background: 'var(--color-danger)0d' }}>
              <div className="font-semibold mb-1 flex items-center gap-1" style={{ color: 'var(--color-danger)' }}>
                <AlertTriangle size={13} /> {preview.errors.length} row(s) will be skipped
              </div>
              {preview.errors.slice(0, 5).map((er, i) => (
                <div key={i} style={{ color: c.textMuted }}>Row {er.row}{er.sheet ? ` (${er.sheet})` : ''}: {er.message}</div>
              ))}
              {preview.errors.length > 5 && <div style={{ color: c.textMuted }}>…and {preview.errors.length - 5} more</div>}
            </div>
          )}

          {/* Warnings */}
          {preview.warnings?.length > 0 && (
            <div className="rounded-lg border p-2.5 text-[12px]" data-testid="bl-import-warnings"
              style={{ borderColor: 'var(--color-accent-amber)', background: 'var(--color-accent-amber)0d' }}>
              <div className="font-semibold mb-1 flex items-center gap-1" style={{ color: 'var(--color-accent-amber)' }}>
                <AlertTriangle size={13} /> {preview.warnings.length} warning(s)
              </div>
              <div className="max-h-32 overflow-auto space-y-0.5">
                {preview.warnings.slice(0, 30).map((w, i) => (
                  <div key={i} className="flex items-center gap-1.5" style={{ color: c.textMuted }} data-testid={`bl-import-warning-${i}`}>
                    {w.type?.startsWith('duplicate') ? <Copy size={11} /> : <AlertTriangle size={11} />}
                    <span>Row {w.row}: {w.message}</span>
                  </div>
                ))}
                {preview.warnings.length > 30 && <div style={{ color: c.textMuted }}>…and {preview.warnings.length - 30} more</div>}
              </div>
            </div>
          )}

          <label className="flex items-center gap-2 text-[12px] cursor-pointer" style={{ color: c.text }}>
            <input type="checkbox" checked={skipDuplicates} data-testid="bl-import-skip-dupes"
              onChange={e => setSkipDuplicates(e.target.checked)} />
            Skip duplicate serials ({counts.assets_duplicate} found — import the rest)
          </label>

          <div className="flex items-center gap-2">
            <Button onClick={runCommit} disabled={committing || willCreate <= 0}
              icon={committing ? Loader2 : CheckCircle2} data-testid="bl-import-commit-btn">
              {committing ? 'Importing…' : `Import ${willCreate} asset${willCreate === 1 ? '' : 's'} into ${counts.stations_total} station${counts.stations_total === 1 ? '' : 's'}`}
            </Button>
            <Button variant="ghost" size="sm" onClick={reset} data-testid="bl-import-cancel">Cancel</Button>
          </div>
        </div>
      )}
    </div>
  );
}
