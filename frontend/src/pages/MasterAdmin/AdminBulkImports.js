/**
 * Master Admin — Bulk Imports
 *
 * One-stop surface for downloading CSV templates and bulk-loading equipment
 * + customer rosters into a target Pulse customer's tenant.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import {
 Download, Upload, Wrench, Users, FileSpreadsheet, ChevronRight,
 CheckCircle2, AlertCircle, Building2, Loader2, MapPin, ScrollText,
 Eye, RotateCcw, History, Lightbulb, RefreshCw,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import ImportWizard from './ImportWizard';
import { Card } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useInlineBanner } from '@/components/notifications';

const API_BASE = process.env.REACT_APP_BACKEND_URL + '/api';

const downloadTemplate = async (kind) => {
  // Use axios (withCredentials) so the HttpOnly session cookie carries the
  // auth — the raw fetch previously relied on a localStorage token that is
  // absent/stale in production, causing a 401. responseType:'blob' lets the
  // browser trigger a real download dialog.
  const r = await axios.get(`${API_BASE}/master-admin/bulk-import/templates/${kind}${kind === 'equipment' ? '?format=xlsx' : ''}`, {
    responseType: 'blob',
  });
  // Surface JSON error responses instead of saving them as a broken .csv.
  const ctype = r.data?.type || r.headers?.['content-type'] || '';
  if (ctype.includes('application/json')) {
    const txt = await r.data.text();
    let msg = 'Template download failed';
    try { msg = JSON.parse(txt).detail || msg; } catch { /* keep default */ }
    throw new Error(msg);
  }
  const url = URL.createObjectURL(r.data);
  const a = document.createElement('a');
  a.href = url;
  a.download = kind === 'equipment' ? 'Equipment Import.xlsx' : `${kind}-template.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
};

const AdminBulkImports = ({ API }) => {
 const token = localStorage.getItem('token');
 const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);
 const [orgs, setOrgs] = useState([]);
 const [orgId, setOrgId] = useState('');
 const [busy, setBusy] = useState({ equipment: false, customers: false, sites: false, contracts: false });
 const [results, setResults] = useState({ equipment: null, customers: null, sites: null, contracts: null });
 const [previewBusy, setPreviewBusy] = useState(false);
 const [previewResult, setPreviewResult] = useState(null);
 const [batches, setBatches] = useState([]);
 const [undoBusy, setUndoBusy] = useState('');
 const equipmentInput = useRef(null);
 const customersInput = useRef(null);
 const sitesInput = useRef(null);
 const contractsInput = useRef(null);
 const previewInput = useRef(null);
 const { banner, show, clear } = useInlineBanner();

 const loadBatches = useMemo(() => async () => {
 try {
 const qs = orgId ? `?organization_id=${encodeURIComponent(orgId)}` : '';
 const { data } = await axios.get(`${API}/master-admin/bulk-import/batches${qs}`, { headers });
 setBatches(data?.batches || []);
 } catch { /* non-fatal */ }
 }, [API, headers, orgId]);

 useEffect(() => { loadBatches(); }, [loadBatches]);

 // Back-fill: ensure already-imported customers exist in the Pulse Fitness
 // Ltd CRM (idempotent — safe to run any time).
 const [syncing, setSyncing] = useState(false);
 const syncCrm = async (manual = false) => {
 if (manual) setSyncing(true);
 try {
 const { data } = await axios.post(`${API}/master-admin/bulk-import/backfill-crm`, {}, { headers });
 const n = data?.customers_linked || 0;
 if (manual) {
 show({ tone: 'success', title: n > 0 ? `Synced ${n} customer(s) into CRM` : 'CRM is up to date',
 detail: 'Imported estates appear in the Pulse Fitness Ltd CRM.' });
 } else if (n > 0) {
 show({ tone: 'success', title: `Synced ${n} customer(s) into CRM`,
 detail: 'Imported estates now appear in the Pulse Fitness Ltd CRM.' });
 }
 } catch {
 if (manual) show({ tone: 'error', title: 'Sync failed', detail: 'Could not sync imported estates into the CRM. Please try again.' });
 } finally {
 if (manual) setSyncing(false);
 }
 };
 useEffect(() => {
 syncCrm(false);
 // eslint-disable-next-line react-hooks/exhaustive-deps
 }, []);

 useEffect(() => {
 // Pull the list of Pulse-visible orgs so the admin can target the import.
 (async () => {
 try {
 const { data } = await axios.get(`${API}/master-admin/pulse-organizations`, { headers });
 setOrgs(data?.organizations || []);
 } catch {
 // Surface nothing — the user can paste an org id manually if needed.
 }
 })();
 }, [API, headers]);

 const runImport = async (kind, file) => {
 if (!file) return;
 // Iter 216h53 — sites must be scoped to a specific target org.
 if (kind === 'sites' && !orgId) {
 show({
 tone: 'warning',
 title: 'Pick a target organisation first',
 detail: 'Sites have no customer_account_number column — choose which customer this site list belongs to in the Target customer dropdown above.',
 });
 return;
 }
 clear();
 setBusy((b) => ({ ...b, [kind]: true }));
 setResults((r) => ({ ...r, [kind]: null }));
 try {
 const fd = new FormData();
 fd.append('file', file);
 // When orgId is blank, the backend resolves the target tenant per row
 // by reading the customer_account_number column.
 const qs = orgId ? `?organization_id=${encodeURIComponent(orgId)}` : '';
 const { data } = await axios.post(
 `${API}/master-admin/bulk-import/${kind}${qs}`,
 fd,
 { headers: { ...headers, 'Content-Type': 'multipart/form-data' } },
 );
 setResults((r) => ({ ...r, [kind]: data }));
 const tenants = Object.keys(data?.org_breakdown || {}).length;
 const detail = [
 data.updated ? `${data.updated} updated` : null,
 data.skipped ? `${data.skipped} skipped` : null,
 data.error_count ? `${data.error_count} row issue${data.error_count === 1 ? '' : 's'} — see details below` : null,
 tenants > 1 ? `routed across ${tenants} tenants` : null,
 ].filter(Boolean).join(' · ');
 show({
 tone: (data.imported > 0 || data.updated > 0) ? (data.error_count ? 'warning' : 'success') : 'warning',
 title: `Imported ${data.imported} ${kind}`,
 detail: detail || undefined,
 });
 loadBatches();
 } catch (err) {
 // Iter 216h54 — surface row-level failures that the backend returns
 // alongside the HTTPException detail. Lee specifically asked to see
 // WHY a CSV failed without having to ask support.
 const data = err.response?.data;
 const detail = typeof data === 'string' ? data : (data?.detail || err.message || 'Unknown error');
 const rowErrors = Array.isArray(data?.errors) ? data.errors : [];
 setResults((r) => ({
   ...r,
   [kind]: rowErrors.length
     ? { imported: 0, skipped: 0, errors: rowErrors, error_count: data?.error_count || rowErrors.length, _failed: true, _detail: detail }
     : { imported: 0, skipped: 0, errors: [detail], error_count: 1, _failed: true, _detail: detail },
 }));
 show({
   tone: 'error',
   title: `Couldn't import ${kind}`,
   detail: typeof detail === 'string' ? detail : 'See error details below',
 });
 }
 setBusy((b) => ({ ...b, [kind]: false }));
 };

 const runPreview = async (file) => {
 if (!file) return;
 clear();
 setPreviewBusy(true);
 setPreviewResult(null);
 try {
 const fd = new FormData();
 fd.append('file', file);
 const qs = orgId ? `?organization_id=${encodeURIComponent(orgId)}` : '';
 const { data } = await axios.post(
 `${API}/master-admin/bulk-import/equipment/preview${qs}`,
 fd,
 { headers: { ...headers, 'Content-Type': 'multipart/form-data' } },
 );
 setPreviewResult(data);
 show({
 tone: data.unmatched_rows > 0 ? 'warning' : 'success',
 title: `Preview: ${data.matched_rows} of ${data.total_rows} rows match a site`,
 detail: data.unmatched_rows
 ? `${data.unmatched_rows} row(s) across ${data.unmatched_site_count} site name(s) won't link — fix before importing`
 : 'All site names resolve — safe to import',
 });
 } catch (err) {
 const detail = err.response?.data?.detail || err.message || 'Preview failed';
 show({ tone: 'error', title: 'Preview failed', detail });
 }
 setPreviewBusy(false);
 };

 const undoBatch = async (batch) => {
 if (!window.confirm(`Undo this ${batch.kind} import? This removes the ${batch.inserted_count} row(s) it added.`)) return;
 setUndoBusy(batch.id);
 try {
 const { data } = await axios.post(`${API}/master-admin/bulk-import/undo/${batch.id}`, {}, { headers });
 show({
 tone: 'success',
 title: `Undone — removed ${data.removed} ${batch.kind} row(s)`,
 detail: data.note || undefined,
 });
 loadBatches();
 } catch (err) {
 const detail = err.response?.data?.detail || err.message || 'Undo failed';
 show({ tone: 'error', title: 'Undo failed', detail });
 }
 setUndoBusy('');
 };

 const ImportCard = ({ kind, icon: Icon, title, description, headers: csvHeaders, inputRef }) => {
 const isBusy = busy[kind];
 const result = results[kind];
 return (
 <Card className="p-5 rounded-xl border-zinc-200" data-testid={`bulk-import-${kind}`}>
 <div className="flex items-start gap-3 mb-3">
 <div className="w-10 h-10 rounded-lg bg-[rgb(var(--rgb-brand-blue)/0.1)] text-[var(--color-brand-blue)] grid place-items-center shrink-0">
 <Icon size={18} />
 </div>
 <div className="flex-1">
 <h3 className="text-sm font-semibold text-zinc-900">{title}</h3>
 <p className="text-xs text-zinc-500 mt-0.5 leading-relaxed">{description}</p>
 </div>
 </div>

 <div className="rounded-lg bg-zinc-50 border border-zinc-200 p-3 mb-3">
 <p className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold mb-1.5">{kind === 'equipment' ? 'Sicon template columns (essentials: Customer Ref, Location, Description, Make, Model, Serial Number)' : 'Required CSV columns'}</p>
 <p className="text-[11px] text-zinc-700 font-mono leading-relaxed">{csvHeaders.join(', ')}</p>
 </div>

 <div className="flex flex-wrap gap-2">
 <Button
 variant="outline"
 size="sm"
 onClick={async () => {
 try { await downloadTemplate(kind); show({ tone: 'success', title: 'Template downloaded' }); }
 catch (err) { show({ tone: 'error', title: 'Download failed', detail: err.message }); }
 }}
 data-testid={`bulk-template-${kind}`}
 >
 <Download size={13} className="mr-1.5" /> Download template
 </Button>
 <input
 ref={inputRef}
 type="file"
 accept=".csv,.xlsx,text/csv,application/vnd.ms-excel"
 className="hidden"
 data-testid={`bulk-file-${kind}`}
 onChange={(e) => {
 const f = e.target.files?.[0];
 if (f) runImport(kind, f);
 e.target.value = '';
 }}
 />
 <Button
 size="sm"
 disabled={isBusy}
 onClick={() => inputRef.current?.click()}
 className="bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white"
 data-testid={`bulk-upload-${kind}`}
 >
 {isBusy ? <Loader2 size={13} className="mr-1.5 animate-spin" /> : <Upload size={13} className="mr-1.5" />}
 {isBusy ? 'Importing…' : `Upload ${kind}`}
 </Button>
 {kind === 'equipment' && (
 <>
 <input
 ref={previewInput}
 type="file"
 accept=".csv,.xlsx,text/csv,application/vnd.ms-excel"
 className="hidden"
 data-testid="bulk-preview-file-equipment"
 onChange={(e) => {
 const f = e.target.files?.[0];
 if (f) runPreview(f);
 e.target.value = '';
 }}
 />
 <Button
 variant="outline"
 size="sm"
 disabled={previewBusy}
 onClick={() => previewInput.current?.click()}
 data-testid="bulk-preview-equipment"
 title="Dry-run: see which site names match before importing"
 >
 {previewBusy ? <Loader2 size={13} className="mr-1.5 animate-spin" /> : <Eye size={13} className="mr-1.5" />}
 {previewBusy ? 'Checking…' : 'Preview site matches'}
 </Button>
 </>
 )}
 </div>

 {kind === 'equipment' && previewResult && (
 <div className="mt-3 rounded-lg border border-zinc-200 bg-zinc-50 p-3 text-xs" data-testid="bulk-preview-result-equipment">
 <p className="font-semibold text-zinc-800 flex items-center gap-1.5">
 <Eye size={13} /> Site-match preview
 </p>
 <p className="mt-1 text-zinc-600">
 <span className="font-semibold text-emerald-700">{previewResult.matched_rows}</span> of {previewResult.total_rows} rows link to a site
 {previewResult.org_wide_rows ? ` · ${previewResult.org_wide_rows} org-wide (no site named)` : ''}
 {previewResult.unmatched_rows ? <> · <span className="font-semibold text-amber-700">{previewResult.unmatched_rows} won't link</span></> : ''}
 </p>
 {previewResult.unmatched_sites?.length > 0 && (
 <div className="mt-2">
 <p className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold mb-1">
 Site names with no match ({previewResult.unmatched_site_count}) — fix these first
 </p>
 <ul className="space-y-1 max-h-52 overflow-auto pr-1">
 {previewResult.unmatched_sites.map((u, i) => (
 <li key={i} className="flex items-start justify-between gap-2 bg-white rounded border border-zinc-200 px-2 py-1" data-testid={`bulk-preview-unmatched-${i}`}>
 <span className="font-mono text-[11px] text-zinc-800">"{u.site_name}" <span className="text-zinc-400">× {u.rows}</span></span>
 {u.suggestion ? (
 <span className="text-[10px] text-emerald-700 flex items-center gap-1 shrink-0">
 <Lightbulb size={11} /> did you mean "{u.suggestion}"?
 </span>
 ) : (
 <span className="text-[10px] text-zinc-400 shrink-0">no close match</span>
 )}
 </li>
 ))}
 </ul>
 </div>
 )}
 {previewResult.account_number_issues?.length > 0 && (
 <p className="mt-2 text-[11px] text-amber-700">
 {previewResult.account_number_issues.reduce((n, a) => n + a.rows, 0)} row(s) have an account number that doesn't match any customer or site.
 </p>
 )}
 {previewResult.unmatched_rows === 0 && (
 <p className="mt-2 text-[11px] text-emerald-700 font-medium">✓ Every site name resolves — safe to import.</p>
 )}
 </div>
 )}

 {result && (
 <div className={`mt-3 rounded-lg p-3 text-xs ${result._failed ? 'bg-red-50 border border-red-200' : (result.imported > 0 || result.updated > 0) ? 'bg-emerald-50 border border-emerald-200' : 'bg-amber-50 border border-amber-200'}`} data-testid={`bulk-result-${kind}`}>
 <p className={`font-semibold flex items-center gap-1.5 ${result._failed ? 'text-red-800' : (result.imported > 0 || result.updated > 0) ? 'text-emerald-800' : 'text-amber-800'}`}>
 {result._failed ? <AlertCircle size={13} /> : (result.imported > 0 || result.updated > 0) ? <CheckCircle2 size={13} /> : <AlertCircle size={13} />}
 {result._failed
   ? `Import failed${result._detail ? ` — ${result._detail}` : ''}`
   : `${result.imported} imported${result.updated ? ` · ${result.updated} updated` : ''} · ${result.skipped || 0} skipped${result.error_count ? ` · ${result.error_count} error${result.error_count === 1 ? '' : 's'}` : ''}`}
 </p>
 {result.errors?.length > 0 && (
 <details className="mt-2" open={(result.error_count || result.errors.length) > 0} data-testid={`bulk-errors-${kind}`}>
 <summary className="cursor-pointer text-zinc-700 hover:text-zinc-900 font-medium">
 {result.error_count && result.error_count > result.errors.length
   ? `Showing first ${result.errors.length} of ${result.error_count} row issue(s) — fix and re-upload`
   : `${result.errors.length} row issue(s) — fix and re-upload`}
 </summary>
 <ul className="mt-1.5 space-y-0.5 font-mono text-[10px] text-zinc-700 max-h-60 overflow-auto pr-1">
 {result.errors.map((e, i) => <li key={i} data-testid={`bulk-error-row-${kind}-${i}`}>· {e}</li>)}
 </ul>
 {result.error_count && result.error_count > result.errors.length && (
 <p className="mt-2 text-[10px] text-zinc-500 italic">
   {result.error_count - result.errors.length} more issue(s) hidden. Re-upload after fixing these first batch — remaining will surface on the next run.
 </p>
 )}
 </details>
 )}
 </div>
 )}
 </Card>
 );
 };

 return (
 <div className="space-y-5" data-testid="admin-bulk-imports">
 {banner}

      {/* Unified Import Centre — one consistent flow: template → upload →
          auto-map → validate → dedupe → preview → import → report. */}
      <div>
        <div className="flex items-center gap-2 mb-1">
          <FileSpreadsheet size={18} className="text-[var(--color-brand-blue)]" />
          <h2 className="text-base font-semibold">Import Centre</h2>
          <Button size="sm" variant="outline" onClick={() => syncCrm(true)} disabled={syncing}
            className="ml-auto" data-testid="bulk-sync-crm-btn"
            title="Push all imported estates into the Pulse Fitness Ltd CRM">
            {syncing ? <Loader2 size={14} className="mr-1.5 animate-spin" /> : <RefreshCw size={14} className="mr-1.5" />}
            Sync
          </Button>
        </div>
        <p className="text-xs text-zinc-500 mb-3">
          Guided import with column auto-mapping, validation, duplicate detection and a preview before anything is written.
        </p>
        <ImportWizard />
      </div>


 {/* Target picker */}
 <Card className="p-5 rounded-xl border-zinc-200" data-testid="bulk-import-target-card">
 <div className="flex items-center gap-2 mb-3">
 <Building2 size={18} className="text-[var(--color-brand-blue)]" />
 <h2 className="text-base font-semibold">Target customer</h2>
 </div>
 <p className="text-xs text-zinc-500 mb-3">
 Leave on <strong>All customers (auto-route)</strong> when your CSV has a
 <span className="font-mono mx-1">customer_account_number</span> column — every row will be routed to the matching
 tenant automatically. Pick a single customer below if your file is for one tenant only and has no account-number column.
 </p>
 <div className="max-w-md">
 <Label className="text-xs">Organisation</Label>
 <Select value={orgId || 'ALL'} onValueChange={(v) => setOrgId(v === 'ALL' ? '' : v)}>
 <SelectTrigger className="mt-1" data-testid="bulk-import-org-select">
 <SelectValue placeholder="All customers (auto-route)" />
 </SelectTrigger>
 <SelectContent>
 <SelectItem value="ALL" data-testid="bulk-import-org-opt-all">
 All customers (auto-route by account number)
 </SelectItem>
 {orgs.map((o) => (
 <SelectItem key={o.id} value={o.id} data-testid={`bulk-import-org-opt-${o.id}`}>
 {o.name} <span className="text-zinc-400 ml-2 text-[10px] uppercase">{o.account_type}</span>
 </SelectItem>
 ))}
 </SelectContent>
 </Select>
 </div>
 </Card>

      <div className="pt-2">
        <h2 className="text-base font-semibold mb-1">Core records (quick CSV)</h2>
        <p className="text-xs text-zinc-500 mb-3">Fast bulk loaders for sites, equipment, CRM customers and contracts with account-number auto-routing.</p>
      </div>

 <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-4">
 <ImportCard
 kind="sites"
 icon={MapPin}
 title="Bulk import sites"
 description="Upload a CSV of all customer sites in one shot — alphabetised, with Sicon Invoice Customer Ref support. Pick the Target customer above first; sites are always org-scoped."
 headers={['site_name', 'invoice_customer_ref', 'address_line1', 'address_line2', 'city', 'county', 'postcode', 'country', 'phone', 'email', 'site_manager_name', 'site_manager_email', 'is_head_office', 'default_location']}
 inputRef={sitesInput}
 />
 <ImportCard
 kind="equipment"
 icon={Wrench}
 title="Bulk import equipment"
 description="Upload the Sicon equipment template (Excel or CSV). Rows route by Sicon Customer Ref (the customer/site account number). Re-importing the same serial numbers fills gaps instead of creating duplicates. Older Pulse templates are still accepted."
 headers={['Sicon Customer Ref', 'Location Description', 'Sublocation Description', 'Supplier Reference', 'Supplier Name', 'Contract Number', 'Contract Line No', 'SLA Name', 'Stock Item Code', 'Description', 'Make', 'Model', 'Serial Number', 'Install Date', 'Manufacturer Warranty Expiry Date', 'Last Service Date', 'Service Interval', 'Service Period', 'Next Service Date', 'ID Number', 'Service Template', 'Equipment Group', 'service_provider', 'unit_price', 'replacement_cost', 'length', 'width', 'height', 'MOD-Force', 'MOD Code', 'Asset Tag', 'Condition', 'Equipment Type', 'Manufacture Date']}
 inputRef={equipmentInput}
 />
 <ImportCard
 kind="customers"
 icon={Users}
 title="Bulk import customers"
 description="Upload a CSV roster of CRM contacts (members, key accounts). When auto-routing, the customer_account_number column decides which tenant each contact lands in."
 headers={['customer_account_number', 'first_name', 'last_name', 'email', 'phone', 'company', 'title', 'tags', 'linkedin', 'address']}
 inputRef={customersInput}
 />
 <ImportCard
 kind="contracts"
 icon={ScrollText}
 title="Bulk import contracts"
 description="Upload a CSV of existing service contracts (the Sicon Contracts API is push-only, so there is no auto-pull). Links to a CRM company by company_name; captures sicon_contract_id for ongoing two-way sync. Duplicates by contract_number are skipped."
 headers={['customer_account_number', 'contract_number', 'title', 'company_name', 'type', 'tier', 'status', 'start_date', 'end_date', 'renewal_date', 'annual_value', 'total_value', 'billing_frequency', 'sla_response_hours', 'sla_resolution_hours', 'auto_renew', 'sicon_contract_id', 'sage_reference']}
 inputRef={contractsInput}
 />
 </div>

 <Card className="p-5 rounded-xl border-zinc-200 bg-zinc-50">
 <p className="text-xs text-zinc-600 leading-relaxed flex items-start gap-2">
 <FileSpreadsheet size={14} className="text-zinc-400 mt-0.5 shrink-0" />
 <span>
 <strong>Account-number aliases accepted:</strong> <span className="font-mono">customer_account_number</span>,
 <span className="font-mono mx-1">CustomerNumber</span>,
 <span className="font-mono mx-1">Account Number</span>,
 <span className="font-mono mx-1">Sage Customer Number</span>.
 Saved CSV exports from Sicon, Orbit 4, Sage 200, and Excel all work — column-name aliases handle the most common variants.
 Rows with an unknown account number are reported in the per-import error log so you can fix and re-upload.
 </span>
 <ChevronRight size={12} className="text-zinc-400" />
 </p>
 </Card>

 {/* Recent imports — one-click undo */}
 <Card className="p-5 rounded-xl border-zinc-200" data-testid="bulk-import-recent-card">
 <div className="flex items-center justify-between mb-3">
 <div className="flex items-center gap-2">
 <History size={18} className="text-[var(--color-brand-blue)]" />
 <h2 className="text-base font-semibold">Recent imports</h2>
 </div>
 <Button variant="ghost" size="sm" onClick={loadBatches} data-testid="bulk-refresh-batches">Refresh</Button>
 </div>
 {batches.length === 0 ? (
 <p className="text-xs text-zinc-500">No recent imports{orgId ? ' for this customer' : ''}. Runs you make here appear below so you can undo a wrong file in one click.</p>
 ) : (
 <ul className="space-y-2">
 {batches.map((b) => (
 <li key={b.id} className="flex items-center justify-between gap-3 rounded-lg border border-zinc-200 px-3 py-2" data-testid={`bulk-batch-${b.id}`}>
 <div className="min-w-0">
 <p className="text-xs font-semibold text-zinc-800 capitalize flex items-center gap-1.5">
 {b.kind === 'sites' ? <MapPin size={12} /> : <Wrench size={12} />}
 {b.kind}
 <span className="text-zinc-400 font-normal">· {b.inserted_count} added{b.updated_count ? ` · ${b.updated_count} updated` : ''}</span>
 </p>
 <p className="text-[10px] text-zinc-500 truncate">
 {b.filename ? `${b.filename} · ` : ''}{new Date(b.created_at).toLocaleString()} · {b.actor_email}
 </p>
 </div>
 <Button
 variant="outline"
 size="sm"
 disabled={undoBusy === b.id}
 onClick={() => undoBatch(b)}
 className="text-red-600 border-red-200 hover:bg-red-50 shrink-0"
 data-testid={`bulk-undo-${b.id}`}
 >
 {undoBusy === b.id ? <Loader2 size={13} className="mr-1.5 animate-spin" /> : <RotateCcw size={13} className="mr-1.5" />}
 Undo
 </Button>
 </li>
 ))}
 </ul>
 )}
 </Card>
 </div>
 );
};

export default AdminBulkImports;
