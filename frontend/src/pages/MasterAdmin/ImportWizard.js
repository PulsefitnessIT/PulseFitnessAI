import { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import {
  Upload, FileSpreadsheet, CheckCircle2, AlertTriangle, Copy, Loader2,
  Download, ArrowRight, ArrowLeft, RotateCcw, Database, Sparkles,
} from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';

const API = process.env.REACT_APP_BACKEND_URL + '/api';

const STEPS = ['Setup', 'Upload & map', 'Review', 'Done'];

const ImportWizard = ({ presetOrgId = null, projectId = null, projectStepKey = null }) => {
  const [step, setStep] = useState(0);
  const [types, setTypes] = useState([]);
  const [orgs, setOrgs] = useState([]);
  const [importType, setImportType] = useState('');
  const [orgId, setOrgId] = useState(presetOrgId || '');
  const [analysis, setAnalysis] = useState(null);     // {columns, fields, rows, suggested_mapping, dedupe_keys}
  const [mapping, setMapping] = useState({});
  const [validation, setValidation] = useState(null);
  const [dedupeAction, setDedupeAction] = useState('skip');
  const [report, setReport] = useState(null);
  const [busy, setBusy] = useState(false);
  const [aiBusy, setAiBusy] = useState(false);
  const [aiIssues, setAiIssues] = useState(null);
  const fileRef = useRef(null);

  useEffect(() => {
    axios.get(`${API}/onboarding/import/types`).then((r) => setTypes(r.data.types || [])).catch(() => {});
    if (!presetOrgId) {
      axios.get(`${API}/master-admin/pulse-organizations`)
        .then((r) => { const d = r.data; setOrgs(Array.isArray(d) ? d : (d.organizations || d.orgs || [])); })
        .catch(() => {});
    }
  }, [presetOrgId]);

  const reset = () => {
    setStep(0); setAnalysis(null); setMapping({}); setValidation(null); setReport(null); setDedupeAction('skip');
  };

  const downloadTemplate = async () => {
    try {
      const r = await axios.get(`${API}/onboarding/import/template/${importType}`, { responseType: 'blob' });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement('a'); a.href = url; a.download = `${importType}-template.csv`;
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
      notify.success('Template downloaded');
    } catch (e) { notifyApiError(notify, e, 'Template download failed'); }
  };

  const onFile = async (file) => {
    if (!file) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append('import_type', importType);
      fd.append('file', file);
      const { data } = await axios.post(`${API}/onboarding/import/analyze`, fd);
      setAnalysis(data);
      setMapping(data.suggested_mapping || {});
      setStep(1);
      notify.success('File analysed', `${data.row_count} rows · ${data.columns.length} columns. Columns auto-mapped.`);
    } catch (e) { notifyApiError(notify, e, 'Could not read file'); }
    finally { setBusy(false); }
  };

  const askAi = async () => {
    setAiBusy(true);
    try {
      const { data } = await axios.post(`${API}/onboarding/import/ai-analyze`, {
        columns: analysis.columns, sample_rows: analysis.sample_rows,
      });
      if (data.mapping && Object.keys(data.mapping).length) {
        setMapping((m) => ({ ...m, ...data.mapping }));
      }
      setAiIssues(data);
      notify.success('AI suggestions applied', `${Object.keys(data.mapping || {}).length} columns mapped · ${(data.issues || []).length} issue(s) flagged.`);
    } catch (e) { notifyApiError(notify, e, 'AI suggestion failed'); }
    finally { setAiBusy(false); }
  };

  const runValidate = async () => {
    setBusy(true);
    try {
      const { data } = await axios.post(`${API}/onboarding/import/validate`, {
        import_type: importType, mapping, rows: analysis.rows, organization_id: orgId,
      });
      setValidation(data);
      setStep(2);
    } catch (e) { notifyApiError(notify, e, 'Validation failed'); }
    finally { setBusy(false); }
  };

  const runCommit = async () => {
    setBusy(true);
    try {
      const { data } = await axios.post(`${API}/onboarding/import/commit`, {
        import_type: importType, mapping, rows: analysis.rows, organization_id: orgId,
        dedupe_action: dedupeAction, project_id: projectId, project_step_key: projectStepKey,
      });
      setReport(data.report);
      setStep(3);
      notify.success('Import complete', `${data.report.created} created · ${data.report.updated} updated · ${data.report.skipped} skipped`);
    } catch (e) { notifyApiError(notify, e, 'Import failed'); }
    finally { setBusy(false); }
  };

  const typeSpec = types.find((t) => t.id === importType);
  const creatingTenant = !!typeSpec?.creates_tenant;
  const requiredOk = typeSpec ? typeSpec.fields.filter((f) => f.required).every((f) => mapping[f.key]) : false;

  return (
    <Card className="p-5" data-testid="import-wizard">
      {/* Stepper */}
      <div className="flex items-center gap-2 mb-5">
        {STEPS.map((s, i) => (
          <div key={s} className="flex items-center gap-2">
            <div className={`h-6 w-6 rounded-full flex items-center justify-center text-[11px] font-semibold ${
              i < step ? 'bg-emerald-500 text-white' : i === step ? 'bg-blue-600 text-white' : 'bg-zinc-200 text-zinc-500'
            }`}>{i < step ? '✓' : i + 1}</div>
            <span className={`text-xs ${i === step ? 'text-zinc-900 font-medium' : 'text-zinc-400'}`}>{s}</span>
            {i < STEPS.length - 1 && <div className="w-6 h-px bg-zinc-200" />}
          </div>
        ))}
      </div>

      {/* Step 0 — Setup */}
      {step === 0 && (
        <div className="space-y-4" data-testid="iw-setup">
          <div>
            <Label className="text-xs">Import type</Label>
            <Select value={importType} onValueChange={setImportType}>
              <SelectTrigger data-testid="iw-type"><SelectValue placeholder="Choose what to import" /></SelectTrigger>
              <SelectContent>
                {types.map((t) => <SelectItem key={t.id} value={t.id}>{t.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          {!presetOrgId && !creatingTenant && (
            <div>
              <Label className="text-xs">Target customer</Label>
              <Select value={orgId} onValueChange={setOrgId}>
                <SelectTrigger data-testid="iw-org"><SelectValue placeholder="Which organisation receives these records?" /></SelectTrigger>
                <SelectContent>
                  {orgs.map((o) => <SelectItem key={o.id} value={o.id}>{o.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          )}
          {creatingTenant && (
            <div className="rounded-lg bg-blue-50 border border-blue-200 p-3 text-xs text-blue-800" data-testid="iw-tenant-note">
              Each row creates a new <strong>Lite</strong> customer organisation (base modules: Operations, Memberships, CRM, Marketing) <strong>and</strong> a matching, linked company in the Pulse&nbsp;Fitness&nbsp;Ltd CRM. Existing customers (matched by name) are skipped, not duplicated.
            </div>
          )}
          {importType && (
            <div className="flex items-center justify-between rounded-lg bg-zinc-50 border border-zinc-200 p-3">
              <span className="text-xs text-zinc-600">Get the CSV template with the right columns.</span>
              <Button size="sm" variant="outline" onClick={downloadTemplate} data-testid="iw-template">
                <Download size={13} className="mr-1.5" /> Download template
              </Button>
            </div>
          )}
          <input ref={fileRef} type="file" accept=".csv" className="hidden"
                 onChange={(e) => onFile(e.target.files?.[0])} data-testid="iw-file-input" />
          <Button
            disabled={!importType || (!orgId && !creatingTenant) || busy}
            onClick={() => fileRef.current?.click()}
            data-testid="iw-upload-btn"
          >
            {busy ? <Loader2 size={15} className="mr-1.5 animate-spin" /> : <Upload size={15} className="mr-1.5" />} Upload CSV
          </Button>
        </div>
      )}

      {/* Step 1 — Map */}
      {step === 1 && analysis && (
        <div className="space-y-4" data-testid="iw-map">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs text-zinc-500">{analysis.row_count} rows detected. Confirm how your columns map — required fields are marked.</p>
            <Button size="sm" variant="outline" onClick={askAi} disabled={aiBusy} data-testid="iw-ai-suggest"
                    className="border-violet-300 text-violet-700 hover:bg-violet-50">
              {aiBusy ? <Loader2 size={13} className="mr-1.5 animate-spin" /> : <Sparkles size={13} className="mr-1.5" />} Ask AI to map
            </Button>
          </div>
          {aiIssues && (
            <div className="rounded-lg border border-violet-200 bg-violet-50 p-3 text-xs space-y-1" data-testid="iw-ai-issues">
              <p className="font-medium text-violet-800">AI suggestion ({aiIssues.confidence || 'n/a'} confidence) — advisory only</p>
              {aiIssues.suggested_type && <p className="text-violet-700">Looks like: <b>{aiIssues.suggested_type}</b></p>}
              {(aiIssues.issues || []).map((i, idx) => (
                <p key={idx} className={i.severity === 'error' ? 'text-red-600' : 'text-amber-700'}>• {i.message}</p>
              ))}
              {(aiIssues.cleanup_suggestions || []).map((s, idx) => <p key={`c${idx}`} className="text-violet-600">✦ {s}</p>)}
            </div>
          )}
          <div className="space-y-2">
            {analysis.fields.map((f) => (
              <div key={f.key} className="flex items-center gap-3" data-testid={`iw-map-${f.key}`}>
                <div className="w-40 text-sm text-zinc-700">
                  {f.label}{f.required && <span className="text-red-500 ml-0.5">*</span>}
                </div>
                <Select value={mapping[f.key] || '__none__'} onValueChange={(v) => setMapping((m) => ({ ...m, [f.key]: v === '__none__' ? undefined : v }))}>
                  <SelectTrigger className="flex-1 h-9"><SelectValue placeholder="— not mapped —" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__">— not mapped —</SelectItem>
                    {analysis.columns.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            ))}
          </div>
          <div className="flex justify-between">
            <Button variant="outline" onClick={() => setStep(0)}><ArrowLeft size={14} className="mr-1.5" /> Back</Button>
            <Button disabled={!requiredOk || busy} onClick={runValidate} data-testid="iw-validate-btn">
              {busy ? <Loader2 size={15} className="mr-1.5 animate-spin" /> : null} Validate <ArrowRight size={14} className="ml-1.5" />
            </Button>
          </div>
        </div>
      )}

      {/* Step 2 — Review */}
      {step === 2 && validation && (
        <div className="space-y-4" data-testid="iw-review">
          <div className="grid grid-cols-4 gap-2">
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-center" data-testid="iw-count-valid">
              <div className="text-xl font-bold text-emerald-600">{validation.counts.valid}</div>
              <div className="text-[10px] text-emerald-700">Valid</div>
            </div>
            <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-center" data-testid="iw-count-errors">
              <div className="text-xl font-bold text-red-600">{validation.counts.errors}</div>
              <div className="text-[10px] text-red-700">Errors</div>
            </div>
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-center" data-testid="iw-count-dupe-existing">
              <div className="text-xl font-bold text-amber-600">{validation.counts.dupes_existing}</div>
              <div className="text-[10px] text-amber-700">Existing dupes</div>
            </div>
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-center" data-testid="iw-count-dupe-file">
              <div className="text-xl font-bold text-amber-600">{validation.counts.dupes_in_file}</div>
              <div className="text-[10px] text-amber-700">In-file dupes</div>
            </div>
          </div>

          <div className="max-h-64 overflow-y-auto rounded-lg border border-zinc-200">
            <table className="w-full text-xs">
              <thead className="bg-zinc-50 sticky top-0"><tr>
                <th className="text-left p-2 font-medium text-zinc-500">#</th>
                <th className="text-left p-2 font-medium text-zinc-500">Record</th>
                <th className="text-left p-2 font-medium text-zinc-500">Status</th>
              </tr></thead>
              <tbody>
                {validation.rows.slice(0, 200).map((r) => (
                  <tr key={r.row} className="border-t border-zinc-100">
                    <td className="p-2 text-zinc-400">{r.row}</td>
                    <td className="p-2 text-zinc-700">{Object.values(r.doc).filter(Boolean).slice(0, 3).join(' · ')}</td>
                    <td className="p-2">
                      {r.errors.length > 0 ? (
                        <span className="text-red-600 flex items-center gap-1"><AlertTriangle size={11} /> {r.errors.join('; ')}</span>
                      ) : r.flags.includes('duplicate_existing') ? (
                        <span className="text-amber-600 flex items-center gap-1"><Database size={11} /> Exists already</span>
                      ) : r.flags.includes('duplicate_in_file') ? (
                        <span className="text-amber-600 flex items-center gap-1"><Copy size={11} /> Duplicate in file</span>
                      ) : (
                        <span className="text-emerald-600 flex items-center gap-1"><CheckCircle2 size={11} /> Ready</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div>
            <Label className="text-xs">When a matching record already exists</Label>
            <Select value={dedupeAction} onValueChange={setDedupeAction}>
              <SelectTrigger className="w-full" data-testid="iw-dedupe-action"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="skip">Skip — keep existing record</SelectItem>
                <SelectItem value="update">Update — merge new values into existing</SelectItem>
                <SelectItem value="create">Create anyway — add as new record</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="flex justify-between">
            <Button variant="outline" onClick={() => setStep(1)}><ArrowLeft size={14} className="mr-1.5" /> Back</Button>
            <Button disabled={busy} onClick={runCommit} data-testid="iw-commit-btn">
              {busy ? <Loader2 size={15} className="mr-1.5 animate-spin" /> : null} Import {validation.total} rows
            </Button>
          </div>
        </div>
      )}

      {/* Step 3 — Done */}
      {step === 3 && report && (
        <div className="space-y-4 text-center py-4" data-testid="iw-done">
          <CheckCircle2 size={40} className="mx-auto text-emerald-500" />
          <h3 className="text-lg font-semibold">Import complete</h3>
          <div className="grid grid-cols-4 gap-2 max-w-md mx-auto">
            <div><div className="text-xl font-bold text-emerald-600">{report.created}</div><div className="text-[10px] text-zinc-500">Created</div></div>
            <div><div className="text-xl font-bold text-blue-600">{report.updated}</div><div className="text-[10px] text-zinc-500">Updated</div></div>
            <div><div className="text-xl font-bold text-zinc-500">{report.skipped}</div><div className="text-[10px] text-zinc-500">Skipped</div></div>
            <div><div className="text-xl font-bold text-red-600">{report.failed}</div><div className="text-[10px] text-zinc-500">Failed</div></div>
          </div>
          {report.errors?.length > 0 && (
            <div className="max-w-md mx-auto text-left text-xs text-red-600 bg-red-50 rounded-lg p-3 max-h-32 overflow-y-auto">
              {report.errors.slice(0, 20).map((e, i) => <div key={i}>Row {e.row}: {e.errors.join('; ')}</div>)}
            </div>
          )}
          <Button variant="outline" onClick={reset} data-testid="iw-restart"><RotateCcw size={14} className="mr-1.5" /> Import more</Button>
        </div>
      )}
    </Card>
  );
};

export default ImportWizard;
