import { useEffect, useState, useCallback, useRef } from 'react';
import { UploadCloud, FileSpreadsheet, Layers, RotateCcw, Play, CheckCircle2, AlertTriangle, Database, PoundSterling } from 'lucide-react';
import { notify } from '@/components/notifications';
import { dpApi } from './api';
import { Spinner, StatCard } from './shared';

function UploadCard({ kind, title, subtitle, sheet, icon: Icon, onDone }) {
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [summary, setSummary] = useState(null);
  const inputRef = useRef(null);

  const upload = async (file) => {
    if (!file) return;
    setBusy(true); setProgress(0); setSummary(null);
    try {
      const res = await dpApi.uploadSpreadsheet(file, kind, setProgress);
      setSummary(res);
      notify.success(`${title} imported — ${res.rows_imported?.toLocaleString()} rows`);
      onDone && onDone();
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Import failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5" data-testid={`dp-import-card-${kind}`}>
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-xl bg-[var(--gx-brand-from)]/10 flex items-center justify-center">
          <Icon size={20} className="text-[var(--gx-brand-from)]" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="font-semibold text-slate-900">{title}</div>
          <div className="text-xs text-slate-500 mt-0.5">{subtitle}</div>
          <div className="text-[11px] text-slate-400 mt-1">Reads sheet <span className="font-mono">{sheet}</span></div>
        </div>
      </div>

      <input ref={inputRef} type="file" accept=".xlsx,.xls,.csv" className="hidden"
        data-testid={`dp-import-input-${kind}`}
        onChange={(e) => upload(e.target.files?.[0])} />

      {busy ? (
        <div className="mt-4">
          <div className="h-2 rounded-full bg-slate-100 overflow-hidden">
            <div className="h-full bg-[var(--gx-brand-from)] transition-all" style={{ width: `${progress}%` }} />
          </div>
          <div className="text-xs text-slate-500 mt-1.5">{progress < 100 ? `Uploading… ${progress}%` : 'Parsing & analysing…'}</div>
        </div>
      ) : (
        <button data-testid={`dp-import-btn-${kind}`} onClick={() => inputRef.current?.click()}
          className="mt-4 w-full inline-flex items-center justify-center gap-2 bg-[var(--gx-brand-from)] text-white text-sm font-semibold px-4 py-2.5 rounded-lg hover:opacity-90">
          <UploadCloud size={16} /> Upload {title}
        </button>
      )}

      {summary && (
        <div className="mt-4 rounded-lg bg-emerald-50 border border-emerald-100 p-3 text-xs text-emerald-800 space-y-0.5" data-testid={`dp-import-summary-${kind}`}>
          <div className="flex items-center gap-1.5 font-semibold"><CheckCircle2 size={14} /> Import complete</div>
          <div>Rows imported: <b>{summary.rows_imported?.toLocaleString()}</b> · skipped: {summary.rows_skipped}</div>
          {kind === 'parts_used' && <div>Unique parts: <b>{summary.unique_parts?.toLocaleString()}</b> · high-usage: {summary.analysis?.high_usage_parts}</div>}
          {kind === 'bom' && <div>Machines: <b>{summary.machines?.toLocaleString()}</b> · unique components: {summary.unique_components?.toLocaleString()}</div>}
          {kind === 'pricelist' && <div>Parts priced: <b>{summary.with_sales_price?.toLocaleString()}</b> of {summary.rows_imported?.toLocaleString()}</div>}
        </div>
      )}
    </div>
  );
}

function WarrantyPlanCard() {
  const inputRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const [plan, setPlan] = useState(null);
  useEffect(() => { dpApi.getWarrantyPlan().then(setPlan).catch(() => {}); }, []);
  const upload = async (file) => {
    if (!file) return;
    setBusy(true);
    try {
      const res = await dpApi.importWarrantyPlan(file);
      notify.success(`Warranty plan loaded — ${res.parts} parts across ${res.machine_groups?.length || 0} machine groups`);
      setPlan(await dpApi.getWarrantyPlan());
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Could not load the warranty plan');
    } finally { setBusy(false); if (inputRef.current) inputRef.current.value = ''; }
  };
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5" data-testid="dp-warranty-plan-card">
      <div className="flex items-center gap-3">
        <FileSpreadsheet size={18} className="text-[var(--gx-brand-from)]" />
        <div className="flex-1">
          <div className="font-semibold text-slate-900">5-Year Warranty Failure Plan</div>
          <div className="text-xs text-slate-500">Pulse's planned parts per machine over 5 years (the “Warranty” sheet). Drives the Allocation Wizard’s recommended pack; extra proven-usage parts top up any remaining allowance.</div>
        </div>
        <input ref={inputRef} type="file" accept=".xlsx,.xls" className="hidden" data-testid="dp-warranty-plan-input"
          onChange={(e) => upload(e.target.files?.[0])} />
        <button data-testid="dp-warranty-plan-btn" onClick={() => inputRef.current?.click()} disabled={busy}
          className="inline-flex items-center gap-2 bg-slate-900 text-white text-sm font-semibold px-4 py-2 rounded-lg hover:opacity-90 disabled:opacity-50">
          <UploadCloud size={15} /> {busy ? 'Loading…' : (plan?.loaded ? 'Re-upload plan' : 'Upload plan')}
        </button>
      </div>
      {plan?.loaded && (
        <div className="mt-4" data-testid="dp-warranty-plan-summary">
          <div className="text-xs text-slate-500 mb-2">{plan.part_count} planned parts · {plan.machine_groups?.length || 0} machine groups</div>
          <div className="flex flex-wrap gap-1.5">
            {(plan.machine_groups || []).map((g) => (
              <span key={g.machine_group} className="text-xs bg-slate-100 text-slate-700 rounded-full px-2.5 py-1">
                {g.machine_group} · {g.part_count} parts
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}


export default function DataImportsTab() {
  const [batches, setBatches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [matching, setMatching] = useState(false);
  const [matchResult, setMatchResult] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    dpApi.listImports().then((d) => setBatches(d.batches || [])).finally(() => setLoading(false));
  }, []);
  useEffect(() => { load(); }, [load]);

  const runMatch = async () => {
    setMatching(true); setMatchResult(null);
    try {
      const r = await dpApi.runMatching();
      setMatchResult(r);
      notify.success(`Matching complete — ${r.matched} matched, ${r.unmatched} unmatched`);
    } catch { notify.error('Matching failed'); } finally { setMatching(false); }
  };

  const reverse = async (id) => {
    if (!window.confirm('Reverse this import? Data from this batch will be removed and analysis recomputed.')) return;
    try { await dpApi.reverseImport(id); notify.success('Import reversed'); load(); }
    catch { notify.error('Reverse failed'); }
  };

  return (
    <div className="space-y-6" data-testid="dp-data-imports-tab">
      <div className="grid md:grid-cols-3 gap-4">
        <UploadCard kind="parts_used" title="Parts Used" subtitle="Historical engineer parts usage since 2022 → Most-Used analysis"
          sheet="SageReportData1" icon={FileSpreadsheet} onDone={load} />
        <UploadCard kind="bom" title="Pulse Fitness BOM" subtitle="Machine bills of materials → versioned BOM machines + components"
          sheet="BOMData" icon={Layers} onDone={load} />
        <UploadCard kind="pricelist" title="Parts Price List" subtitle="Sales price per part code → values recommendation packs & the allowance"
          sheet="ExportData" icon={PoundSterling} onDone={load} />
      </div>

      <WarrantyPlanCard />

      <div className="rounded-2xl border border-slate-200 bg-white p-5">
        <div className="flex items-center gap-3">
          <Database size={18} className="text-[var(--gx-brand-from)]" />
          <div className="flex-1">
            <div className="font-semibold text-slate-900">Match usage to BOM</div>
            <div className="text-xs text-slate-500">Run the multi-stage matching engine (exact → normalised → description/fuzzy → alias).</div>
          </div>
          <button data-testid="dp-run-match-btn" onClick={runMatch} disabled={matching}
            className="inline-flex items-center gap-2 bg-slate-900 text-white text-sm font-semibold px-4 py-2 rounded-lg hover:opacity-90 disabled:opacity-50">
            <Play size={15} /> {matching ? 'Matching…' : 'Run matching'}
          </button>
        </div>
        {matchResult && (
          <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-3" data-testid="dp-match-result">
            <StatCard label="Matched" value={matchResult.matched} tone="emerald" />
            <StatCard label="Unmatched" value={matchResult.unmatched} tone="amber" />
            <StatCard label="Exact code" value={matchResult.stats?.exact_code || 0} tone="brand" />
            <StatCard label="Fuzzy (review)" value={matchResult.stats?.fuzzy_description || 0} tone="slate" />
          </div>
        )}
      </div>

      <div>
        <h3 className="text-sm font-semibold text-slate-500 mb-3">Import history &amp; audit</h3>
        {loading ? <Spinner /> : batches.length === 0 ? (
          <div className="text-center py-12 text-slate-400 text-sm">No imports yet. Upload a spreadsheet to get started.</div>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-xs text-slate-400 border-b border-slate-100 bg-slate-50/50">
                <th className="py-2.5 px-4">File</th><th>Type</th><th>Rows</th><th>Warnings</th><th>Status</th><th>By</th><th></th>
              </tr></thead>
              <tbody>
                {batches.map((b) => {
                  const warns = Object.entries(b.warnings || {}).filter(([, v]) => v > 0);
                  return (
                    <tr key={b.id} data-testid={`dp-batch-row-${b.id}`} className="border-b border-slate-50">
                      <td className="py-2.5 px-4 font-medium text-slate-700">{b.filename}</td>
                      <td>{b.kind === 'bom' ? 'BOM' : 'Parts Used'}</td>
                      <td className="tabular-nums">{(b.rows_imported || 0).toLocaleString()}</td>
                      <td className="text-xs text-amber-600">{warns.length ? <span className="inline-flex items-center gap-1"><AlertTriangle size={12} />{warns.reduce((s, [, v]) => s + v, 0)}</span> : '—'}</td>
                      <td><span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border ${b.status === 'reversed' ? 'bg-red-50 text-red-600 border-red-200' : 'bg-emerald-50 text-emerald-700 border-emerald-200'}`}>{b.status}</span></td>
                      <td className="text-xs text-slate-500">{b.created_by}</td>
                      <td className="text-right pr-3">
                        {b.status !== 'reversed' && (
                          <button onClick={() => reverse(b.id)} data-testid={`dp-reverse-${b.id}`} className="text-slate-400 hover:text-red-500 inline-flex items-center gap-1 text-xs"><RotateCcw size={13} /> Reverse</button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
