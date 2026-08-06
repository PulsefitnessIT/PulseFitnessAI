/**
 * AI Kit-List Import modal (Iter 216h240).
 *
 * Reads ANY equipment spreadsheet, AI-cleans it (derives a proper Name,
 * title-cases ALL-CAPS text, treats tabs as sub-locations, skips summary/pivot
 * tabs), lets the operator review/override, then imports via the SAME MOD
 * equipment bulk-import engine (one import path, serial de-dupe).
 */
import { useState, useCallback } from 'react';
import axios from 'axios';
import { Upload, Loader2, X, CheckCircle2, AlertTriangle, Sparkles, FileSpreadsheet } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL + '/api';

export default function AIKitImportModal({ site, headers, onClose, onImported }) {
  const [step, setStep] = useState('upload'); // upload | review | done
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState(null);
  const [skipDuplicates, setSkipDuplicates] = useState(true);
  const [result, setResult] = useState(null);
  const [filteredDupes, setFilteredDupes] = useState(0);
  const [error, setError] = useState('');

  const analyse = useCallback(async (f) => {
    if (!f) return;
    setBusy(true); setError('');
    try {
      const fd = new FormData();
      fd.append('file', f);
      const { data } = await axios.post(
        `${API}/master-admin/mod-estate/ai-kit-import/analyse?site_id=${encodeURIComponent(site.id)}`,
        fd,
        { headers: { ...headers, 'Content-Type': 'multipart/form-data' } },
      );
      // seed per-tab include (skip summaries) + per-row keep flags
      data.sheets = (data.sheets || []).map((sh) => ({
        ...sh,
        include: !sh.is_summary,
        rows: (sh.rows || []).map((r) => ({ ...r, keep: true })),
      }));
      setPreview(data);
      setStep('review');
    } catch (e) {
      setError(e?.response?.data?.detail || 'Could not analyse that spreadsheet.');
    }
    setBusy(false);
  }, [site.id, headers]);

  const onPick = (e) => {
    const f = e.target.files?.[0];
    e.target.value = '';
    if (f) { setFile(f); analyse(f); }
  };

  const setSheet = (ti, patch) =>
    setPreview((p) => ({ ...p, sheets: p.sheets.map((s, i) => i === ti ? { ...s, ...patch } : s) }));
  const setRow = (ti, ri, patch) =>
    setPreview((p) => ({
      ...p,
      sheets: p.sheets.map((s, i) => i !== ti ? s
        : { ...s, rows: s.rows.map((r, j) => j === ri ? { ...r, ...patch } : r) }),
    }));

  const buildRows = () => {
    const out = [];
    (preview?.sheets || []).forEach((sh) => {
      if (!sh.include) return;
      const subloc = (sh.suggested_sub_location || sh.tab || '').trim();
      sh.rows.forEach((r) => {
        if (!r.keep) return;
        if (skipDuplicates && r.duplicate) return;
        out.push({ ...r, sub_location: subloc });
      });
    });
    return out;
  };

  const commit = async () => {
    const rows = buildRows();
    if (!rows.length) { notify.error('Nothing to import', 'All rows are excluded or duplicates.'); return; }
    const dropped = skipDuplicates
      ? (preview?.sheets || []).reduce((n, sh) => n + (sh.include ? sh.rows.filter((r) => r.keep && r.duplicate).length : 0), 0)
      : 0;
    setFilteredDupes(dropped);
    setBusy(true); setError('');
    try {
      const { data } = await axios.post(
        `${API}/master-admin/mod-estate/ai-kit-import/commit`,
        { site_id: site.id, rows, skip_duplicates: skipDuplicates },
        { headers },
      );
      setResult(data);
      setStep('done');
      notify.success(`Imported ${data.imported} items into ${site.name}`,
        data.skipped ? `${data.skipped} skipped (duplicates / blanks).` : 'All rows accepted.');
      onImported?.();
    } catch (e) {
      setError(e?.response?.data?.detail || 'Import failed.');
    }
    setBusy(false);
  };

  const willImport = buildRows().length;

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.55)' }} data-testid="ai-kit-import-modal">
      <div className="w-full max-w-5xl max-h-[90vh] bg-white rounded-xl shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-200">
          <div className="flex items-center gap-2">
            <Sparkles size={18} className="text-cyan-600" />
            <div>
              <h3 className="text-sm font-extrabold text-zinc-900">AI Import — any kit list</h3>
              <p className="text-[11px] text-zinc-500">{site.name}</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-md text-zinc-400 hover:text-zinc-700" data-testid="ai-kit-close"><X size={16} /></button>
        </div>

        <div className="flex-1 overflow-y-auto p-5">
          {error && <div className="mb-4 px-3 py-2 rounded-md text-xs bg-red-50 text-red-700 border border-red-200" data-testid="ai-kit-error">{error}</div>}

          {/* Upload */}
          {step === 'upload' && (
            <div className="text-center py-10">
              <div className="mx-auto w-14 h-14 rounded-full bg-cyan-50 flex items-center justify-center mb-4"><FileSpreadsheet size={26} className="text-cyan-600" /></div>
              <p className="text-sm font-semibold text-zinc-800 mb-1">Upload any equipment / kit list</p>
              <p className="text-xs text-zinc-500 max-w-md mx-auto mb-5">
                Excel or CSV — messy is fine. AI derives a proper equipment name, tidies ALL-CAPS text, treats each
                worksheet tab as a room / sub-location and skips summary tabs. You review everything before it imports.
              </p>
              <label className="inline-flex">
                <input type="file" accept=".xlsx,.xls,.csv" className="hidden" onChange={onPick} data-testid="ai-kit-file-input" />
                <span className={`inline-flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-semibold cursor-pointer ${busy ? 'bg-zinc-300 text-zinc-500' : 'bg-cyan-600 text-white hover:bg-cyan-700'}`}>
                  {busy ? <Loader2 size={15} className="animate-spin" /> : <Upload size={15} />} {busy ? 'Analysing…' : 'Choose file'}
                </span>
              </label>
              {file && busy && <p className="text-[11px] text-zinc-500 mt-3">Reading “{file.name}” and cleaning with AI — this can take a few seconds…</p>}
            </div>
          )}

          {/* Review */}
          {step === 'review' && preview && (
            <div className="space-y-4" data-testid="ai-kit-review">
              <div className="flex items-center flex-wrap gap-3 justify-between">
                <div className="flex items-center gap-4 text-xs text-zinc-600">
                  <span><b className="text-zinc-900">{preview.importable_rows}</b> items across <b className="text-zinc-900">{preview.sheets.filter((s) => !s.is_summary).length}</b> tabs</span>
                  <span><b className="text-zinc-900">{preview.distinct_items}</b> distinct products</span>
                  {preview.duplicate_serials > 0 && <span className="text-amber-700 flex items-center gap-1"><AlertTriangle size={13} />{preview.duplicate_serials} duplicate serial(s)</span>}
                </div>
                <label className="flex items-center gap-1.5 text-xs text-zinc-700 cursor-pointer" data-testid="ai-kit-skip-dupes">
                  <input type="checkbox" checked={skipDuplicates} onChange={(e) => setSkipDuplicates(e.target.checked)} /> Skip duplicate serials
                </label>
              </div>

              {preview.sheets.map((sh, ti) => (
                <div key={ti} className={`rounded-lg border ${sh.include ? 'border-zinc-200' : 'border-zinc-100 bg-zinc-50/60'}`} data-testid={`ai-kit-tab-${ti}`}>
                  <div className="flex items-center flex-wrap gap-3 px-3 py-2.5 border-b border-zinc-100">
                    <label className="flex items-center gap-1.5 text-sm font-bold text-zinc-800 cursor-pointer">
                      <input type="checkbox" checked={sh.include} onChange={(e) => setSheet(ti, { include: e.target.checked })} data-testid={`ai-kit-tab-include-${ti}`} />
                      {sh.tab}
                    </label>
                    {sh.is_summary && <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-700 font-semibold">summary tab — skipped by default</span>}
                    <span className="text-[11px] text-zinc-500">{sh.rows.length} rows</span>
                    {sh.include && (
                      <div className="flex items-center gap-1.5 ml-auto">
                        <span className="text-[11px] text-zinc-500">Sub-location:</span>
                        <input
                          value={sh.suggested_sub_location || ''}
                          onChange={(e) => setSheet(ti, { suggested_sub_location: e.target.value })}
                          className="text-xs px-2 py-1 border border-zinc-300 rounded-md w-44"
                          data-testid={`ai-kit-subloc-${ti}`}
                        />
                      </div>
                    )}
                  </div>
                  {sh.include && (
                    <div className="overflow-x-auto max-h-64 overflow-y-auto">
                      <table className="w-full text-[11px]">
                        <thead className="sticky top-0 bg-zinc-50 text-zinc-500">
                          <tr>
                            <th className="text-left px-2 py-1.5 w-8"></th>
                            <th className="text-left px-2 py-1.5">Name</th>
                            <th className="text-left px-2 py-1.5">Type</th>
                            <th className="text-left px-2 py-1.5">Manufacturer</th>
                            <th className="text-left px-2 py-1.5">Serial</th>
                            <th className="text-left px-2 py-1.5">Asset #</th>
                            <th className="text-left px-2 py-1.5 w-10">Qty</th>
                          </tr>
                        </thead>
                        <tbody>
                          {sh.rows.map((r, ri) => (
                            <tr key={ri} className={`border-t border-zinc-100 ${r.duplicate ? 'bg-amber-50' : ''} ${!r.keep ? 'opacity-40' : ''}`} data-testid={`ai-kit-row-${ti}-${ri}`}>
                              <td className="px-2 py-1"><input type="checkbox" checked={r.keep} onChange={(e) => setRow(ti, ri, { keep: e.target.checked })} /></td>
                              <td className="px-2 py-1">
                                <input value={r.name} onChange={(e) => setRow(ti, ri, { name: e.target.value })} className="w-full min-w-[160px] px-1.5 py-0.5 border border-transparent hover:border-zinc-200 focus:border-cyan-400 rounded" data-testid={`ai-kit-name-${ti}-${ri}`} />
                                {r.duplicate && <span className="ml-1 text-[9px] text-amber-700 font-semibold">DUP</span>}
                              </td>
                              <td className="px-2 py-1 text-zinc-600">{r.equipment_type}</td>
                              <td className="px-2 py-1 text-zinc-600">{r.manufacturer}</td>
                              <td className="px-2 py-1 text-zinc-500 font-mono">{r.serial_number}</td>
                              <td className="px-2 py-1 text-zinc-500 font-mono">{r.asset_number}</td>
                              <td className="px-2 py-1 text-zinc-600">{r.quantity}</td>
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

          {/* Done */}
          {step === 'done' && result && (
            <div className="text-center py-10" data-testid="ai-kit-done">
              <div className="mx-auto w-14 h-14 rounded-full bg-green-50 flex items-center justify-center mb-4"><CheckCircle2 size={28} className="text-green-600" /></div>
              <p className="text-sm font-bold text-zinc-900 mb-1">Imported {result.imported} items into {site.name}</p>
              <p className="text-xs text-zinc-500">{result.skipped || 0} skipped{result.errors?.length ? ` · ${result.errors.length} error(s)` : ''}.</p>
              {filteredDupes > 0 && <p className="text-[11px] text-amber-700 mt-1">{filteredDupes} duplicate serial(s) filtered out before import.</p>}
              {result.errors?.length > 0 && (
                <div className="mt-4 mx-auto max-w-lg text-left text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded-md p-3 max-h-40 overflow-y-auto">
                  {result.errors.slice(0, 30).map((e, i) => <div key={i}>{e}</div>)}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-5 py-4 border-t border-zinc-200">
          {step === 'review' && (
            <>
              <span className="text-xs text-zinc-500 mr-auto">{willImport} item(s) will be imported</span>
              <Button variant="outline" onClick={() => { setStep('upload'); setPreview(null); }} data-testid="ai-kit-back">Choose another file</Button>
              <Button onClick={commit} disabled={busy || !willImport} data-testid="ai-kit-commit">
                {busy ? <Loader2 size={14} className="animate-spin mr-1.5" /> : <CheckCircle2 size={14} className="mr-1.5" />} Import {willImport} item(s)
              </Button>
            </>
          )}
          {step !== 'review' && <Button variant="outline" onClick={onClose} data-testid="ai-kit-done-close">{step === 'done' ? 'Done' : 'Cancel'}</Button>}
        </div>
      </div>
    </div>
  );
}
