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
 CheckCircle2, AlertCircle, Building2, Loader2, MapPin,
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
  const r = await axios.get(`${API_BASE}/master-admin/bulk-import/templates/${kind}`, {
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
  a.download = `${kind}-template.csv`;
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
 const [busy, setBusy] = useState({ equipment: false, customers: false, sites: false });
 const [results, setResults] = useState({ equipment: null, customers: null, sites: null });
 const equipmentInput = useRef(null);
 const customersInput = useRef(null);
 const sitesInput = useRef(null);
 const { banner, show, clear } = useInlineBanner();

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
 data.skipped ? `${data.skipped} skipped` : null,
 data.error_count ? `${data.error_count} row issue${data.error_count === 1 ? '' : 's'} — see details below` : null,
 tenants > 1 ? `routed across ${tenants} tenants` : null,
 ].filter(Boolean).join(' · ');
 show({
 tone: data.imported > 0 ? (data.error_count ? 'warning' : 'success') : 'warning',
 title: `Imported ${data.imported} ${kind}`,
 detail: detail || undefined,
 });
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
 <p className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold mb-1.5">Required CSV columns</p>
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
 accept=".csv,text/csv,application/vnd.ms-excel"
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
 </div>

 {result && (
 <div className={`mt-3 rounded-lg p-3 text-xs ${result._failed ? 'bg-red-50 border border-red-200' : result.imported > 0 ? 'bg-emerald-50 border border-emerald-200' : 'bg-amber-50 border border-amber-200'}`} data-testid={`bulk-result-${kind}`}>
 <p className={`font-semibold flex items-center gap-1.5 ${result._failed ? 'text-red-800' : result.imported > 0 ? 'text-emerald-800' : 'text-amber-800'}`}>
 {result._failed ? <AlertCircle size={13} /> : result.imported > 0 ? <CheckCircle2 size={13} /> : <AlertCircle size={13} />}
 {result._failed
   ? `Import failed${result._detail ? ` — ${result._detail}` : ''}`
   : `${result.imported} imported · ${result.skipped || 0} skipped${result.error_count ? ` · ${result.error_count} error${result.error_count === 1 ? '' : 's'}` : ''}`}
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
        <p className="text-xs text-zinc-500 mb-3">Fast bulk loaders for sites, equipment and CRM customers with account-number auto-routing.</p>
      </div>

 <div className="grid md:grid-cols-3 gap-4">
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
 description="Upload a CSV of every machine across one or many customer floors. Equipment auto-links to sites by site_name; supplier resolves to a row in the suppliers directory so fault emails route correctly. Duplicates by serial_number are skipped."
 headers={['site_name', 'customer_account_number', 'supplier', 'name', 'equipment_type', 'manufacturer', 'model', 'serial_number', 'purchase_date', 'warranty_expiry', 'service_provider', 'unit_price', 'length', 'width', 'height', 'location', 'notes']}
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
 </div>
 );
};

export default AdminBulkImports;
