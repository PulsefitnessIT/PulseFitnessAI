import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { X, MapPin, Loader2, Crown, Plus, Upload, Download, ChevronRight } from 'lucide-react';
import SiteModulesOverride from '@/components/sites/SiteModulesOverride';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import SiteDetailDrawer from './SiteDetailDrawer';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const authHeaders = () => ({ Authorization: `Bearer ${localStorage.getItem('token')}` });

/**
 * Master-Admin "Sites" expand panel for an org row.
 *
 * Iter 216d — beyond listing existing sites and toggling the HQ flag,
 * this panel now lets the operator:
 *   • Add a single site inline (mirrors the wizard's site form).
 *   • Bulk-import sites from a CSV (uses the same template the wizard
 *     can download — keeps a single source of truth for site columns).
 * Head Office customers tend to have *zero* equipment of their own; the
 * machines live on the individual sites underneath. The wizard only
 * captures HQ details, so this panel is the other half of the loop.
 */
const OrgSitesPanel = ({ org, onClose }) => {
  const [sites, setSites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [hqBusyId, setHqBusyId] = useState(null);
  // Iter 216h53 — click a site row to open the detail drawer (Site
  // Details + Equipment inline-edit tabs).
  const [selectedSite, setSelectedSite] = useState(null);

  // Add-site / CSV-import workflow state.
  const [showAdd, setShowAdd] = useState(false);
  const [adding, setAdding] = useState(false);
  const [newSite, setNewSite] = useState({ name: '', address_line1: '', city: '', county: '', postcode: '', country: 'United Kingdom', phone: '', email: '', site_manager_email: '', is_head_office: false });
  const [csvBusy, setCsvBusy] = useState(false);
  const [csvPreview, setCsvPreview] = useState(null); // { sites: [], errors: [] }
  const fileRef = useRef(null);

  const loadSites = async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/master-admin/organizations/${org.id}/sites`, { headers: authHeaders() });
      setSites(r.data?.sites || []);
    } catch (e) {
      notifyApiError(notify, e, 'Failed to load sites');
    } finally {
      setLoading(false);
    }
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: the loader closure(s) re-read live state on every call; the effect re-fires on the listed trigger deps, so adding the function identity would just thrash without changing behaviour.
  useEffect(() => { loadSites();   }, [org.id]);

  const setHeadOffice = async (site) => {
    setHqBusyId(site.id);
    try {
      const r = await axios.patch(
        `${API}/master-admin/organizations/${org.id}/sites/${site.id}`,
        { is_head_office: !site.is_head_office },
        { headers: authHeaders() },
      );
      const updated = r.data;
      setSites((cur) => cur.map((s) => {
        if (s.id === updated.id) return { ...s, ...updated };
        if (updated.is_head_office) return { ...s, is_head_office: false };
        return s;
      }));
      notify.success(updated.is_head_office ? 'Marked as Head Office' : 'Head Office cleared');
    } catch (e) {
      notifyApiError(notify, e, 'Failed to update Head Office');
    } finally {
      setHqBusyId(null);
    }
  };

  const submitNewSite = async () => {
    if (!newSite.name.trim()) {
      notify.error('Site name is required');
      return;
    }
    setAdding(true);
    try {
      const r = await axios.post(`${API}/master-admin/organizations/${org.id}/sites`, newSite, { headers: authHeaders() });
      notify.success(`Site '${newSite.name}' added`);
      // Optimistically add the created site so success doesn't depend on a
      // follow-up refresh (a transient 401 on the refresh GET must NOT be
      // reported as "save failed" — the site is already persisted).
      if (r?.data?.id) setSites((prev) => [...(prev || []), r.data]);
      setNewSite({ name: '', address_line1: '', city: '', county: '', postcode: '', country: 'United Kingdom', phone: '', email: '', site_manager_email: '', is_head_office: false });
      setShowAdd(false);
    } catch (e) {
      notifyApiError(notify, e, 'Failed to create site');
      setAdding(false);
      return;
    }
    setAdding(false);
    // Refresh in the background; never let its failure surface as a save error.
    try { await loadSites(); } catch { /* already shown optimistically */ }
  };

  const downloadTemplate = async () => {
    try {
      const r = await axios.get(`${API}/master-admin/sites/template.csv`, {
        headers: authHeaders(), responseType: 'blob',
      });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement('a'); a.href = url;
      a.download = 'gymaxis-sites-template.csv'; a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      notifyApiError(notify, e, 'Failed to download template');
    }
  };

  const onCsvSelected = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setCsvBusy(true);
    try {
      const fd = new FormData(); fd.append('file', file);
      const r = await axios.post(`${API}/master-admin/sites/preview-csv`, fd, { headers: authHeaders() });
      setCsvPreview(r.data);
    } catch (err) {
      notifyApiError(notify, err, 'CSV parse failed');
    } finally {
      setCsvBusy(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const commitCsv = async () => {
    if (!csvPreview?.sites?.length) return;
    setCsvBusy(true);
    try {
      const r = await axios.post(
        `${API}/master-admin/organizations/${org.id}/sites/bulk`,
        { sites: csvPreview.sites },
        { headers: authHeaders() },
      );
      notify.success(`${r.data.created_count} site(s) imported`);
      setCsvPreview(null);
      await loadSites();
    } catch (e) {
      notifyApiError(notify, e, 'Bulk import failed');
    } finally {
      setCsvBusy(false);
    }
  };

  return (
    <div className="border-t border-zinc-100 bg-zinc-50 p-4" data-testid={`org-sites-panel-${org.id}`}>
      <div className="flex items-center justify-between mb-3 gap-2 flex-wrap">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-zinc-800 flex items-center gap-1.5">
            <MapPin size={14} className="text-[var(--color-brand-blue)]" /> Sites &amp; module overrides — {org.name}
          </p>
          <p className="text-[11px] text-zinc-500 mt-0.5">
            Add sites manually or import a CSV. Head Office orgs typically have zero machines —
            equipment lives on the individual sites.
          </p>
        </div>
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => setShowAdd((v) => !v)}
            className="inline-flex items-center gap-1 text-[11px] font-bold uppercase tracking-wider px-2.5 py-1.5 rounded-md border bg-white text-emerald-700 border-emerald-200 hover:bg-emerald-50"
            data-testid={`org-sites-add-btn-${org.id}`}
          >
            <Plus size={11} /> Add site
          </button>
          <button
            onClick={downloadTemplate}
            className="inline-flex items-center gap-1 text-[11px] font-bold uppercase tracking-wider px-2.5 py-1.5 rounded-md border bg-white text-zinc-600 border-zinc-200 hover:bg-zinc-100"
            data-testid={`org-sites-template-btn-${org.id}`}
          >
            <Download size={11} /> CSV template
          </button>
          <label className="inline-flex items-center gap-1 text-[11px] font-bold uppercase tracking-wider px-2.5 py-1.5 rounded-md border bg-white text-blue-700 border-blue-200 hover:bg-blue-50 cursor-pointer">
            <Upload size={11} /> Import CSV
            <input ref={fileRef} type="file" accept=".csv" className="hidden" onChange={onCsvSelected} data-testid={`org-sites-csv-input-${org.id}`} />
          </label>
          <button onClick={onClose} className="text-zinc-400 hover:text-zinc-600 ml-1"><X size={16} /></button>
        </div>
      </div>

      {/* Inline add-site form */}
      {showAdd && (
        <div className="bg-white border border-emerald-200 rounded-md p-3 mb-3" data-testid={`org-sites-add-form-${org.id}`}>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
            <input className="text-sm border border-zinc-200 rounded px-2 py-1" placeholder="Site name *" value={newSite.name} onChange={(e) => setNewSite({ ...newSite, name: e.target.value })} data-testid="new-site-name" />
            <input className="text-sm border border-zinc-200 rounded px-2 py-1" placeholder="Address line 1" value={newSite.address_line1} onChange={(e) => setNewSite({ ...newSite, address_line1: e.target.value })} />
            <input className="text-sm border border-zinc-200 rounded px-2 py-1" placeholder="Postcode" value={newSite.postcode} onChange={(e) => setNewSite({ ...newSite, postcode: e.target.value })} />
            <input className="text-sm border border-zinc-200 rounded px-2 py-1" placeholder="City" value={newSite.city} onChange={(e) => setNewSite({ ...newSite, city: e.target.value })} />
            <input className="text-sm border border-zinc-200 rounded px-2 py-1" placeholder="County" value={newSite.county} onChange={(e) => setNewSite({ ...newSite, county: e.target.value })} />
            <input className="text-sm border border-zinc-200 rounded px-2 py-1" placeholder="Site phone" value={newSite.phone} onChange={(e) => setNewSite({ ...newSite, phone: e.target.value })} />
            <input className="text-sm border border-zinc-200 rounded px-2 py-1 md:col-span-2" placeholder="Site manager email (auto-invite)" value={newSite.site_manager_email} onChange={(e) => setNewSite({ ...newSite, site_manager_email: e.target.value })} />
            <label className="flex items-center gap-1.5 text-xs text-zinc-700 px-2">
              <input type="checkbox" checked={newSite.is_head_office} onChange={(e) => setNewSite({ ...newSite, is_head_office: e.target.checked })} />
              Mark as Head Office
            </label>
          </div>
          <div className="mt-2 flex justify-end gap-2">
            <button onClick={() => setShowAdd(false)} className="text-xs px-3 py-1.5 rounded border border-zinc-200 text-zinc-600 hover:bg-zinc-50">Cancel</button>
            <button
              onClick={submitNewSite}
              disabled={adding || !newSite.name.trim()}
              className="text-xs px-3 py-1.5 rounded bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50 inline-flex items-center gap-1"
              data-testid="new-site-submit"
            >
              {adding ? <Loader2 size={11} className="animate-spin" /> : <Plus size={11} />} Add site
            </button>
          </div>
        </div>
      )}

      {/* CSV preview (before commit) */}
      {csvPreview && (
        <div className="bg-white border border-blue-200 rounded-md p-3 mb-3" data-testid={`org-sites-csv-preview-${org.id}`}>
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm font-semibold text-zinc-800">CSV preview — {csvPreview.sites.length} site(s) to import</p>
            <button onClick={() => setCsvPreview(null)} className="text-zinc-400 hover:text-zinc-600"><X size={14} /></button>
          </div>
          <div className="max-h-44 overflow-auto text-xs border border-zinc-100 rounded overflow-x-auto">
            <table className="w-full">
              <thead className="bg-zinc-50">
                <tr><th className="text-left p-1.5">Name</th><th className="text-left p-1.5">Postcode</th><th className="text-left p-1.5">City</th><th className="p-1.5">HQ?</th></tr>
              </thead>
              <tbody>
                {csvPreview.sites.map((s, i) => (
                  <tr key={i} className="border-t border-zinc-100">
                    <td className="p-1.5">{s.name}</td>
                    <td className="p-1.5">{s.postcode}</td>
                    <td className="p-1.5">{s.city}</td>
                    <td className="p-1.5 text-center">{s.is_head_office ? '✓' : ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {csvPreview.errors?.length > 0 && (
            <p className="mt-2 text-[11px] text-amber-700">
              {csvPreview.errors.length} row(s) skipped: {csvPreview.errors.map((e) => `line ${e.line} (${e.error})`).join(', ')}
            </p>
          )}
          <div className="mt-2 flex justify-end gap-2">
            <button onClick={() => setCsvPreview(null)} className="text-xs px-3 py-1.5 rounded border border-zinc-200 text-zinc-600 hover:bg-zinc-50">Cancel</button>
            <button
              onClick={commitCsv}
              disabled={csvBusy}
              className="text-xs px-3 py-1.5 rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 inline-flex items-center gap-1"
              data-testid="csv-import-commit"
            >
              {csvBusy ? <Loader2 size={11} className="animate-spin" /> : <Upload size={11} />} Confirm &amp; import
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="flex items-center gap-2 text-xs text-zinc-500"><Loader2 size={12} className="animate-spin" /> Loading sites…</div>
      ) : sites.length === 0 ? (
        <p className="text-xs text-zinc-500">No sites configured for this organisation. Use Add site or Import CSV above.</p>
      ) : (
        <div className="space-y-3">
          {sites.map((site) => (
            <div
              key={site.id}
              className={`bg-white border border-zinc-200 rounded-md p-3 transition-colors ${site.is_default ? '' : 'cursor-pointer hover:border-blue-300 hover:bg-blue-50/30'}`}
              data-testid={`org-site-row-${site.id}`}
              onClick={() => { if (!site.is_default) setSelectedSite(site); }}
            >
              <div className="flex items-center justify-between mb-1">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-zinc-800 truncate flex items-center gap-1.5">
                    {site.name}
                    {site.is_default && (<span className="ml-2 inline-block px-1.5 py-0.5 text-[9px] rounded bg-amber-100 text-amber-700">Default</span>)}
                    {site.is_head_office && (
                      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[9px] rounded bg-amber-50 text-amber-700 border border-amber-200" data-testid={`org-site-hq-badge-${site.id}`}>
                        <Crown size={9} /> HEAD OFFICE
                      </span>
                    )}
                  </p>
                  {site.address && (<p className="text-[10px] text-zinc-400 truncate">{site.address}{site.postcode ? ` · ${site.postcode}` : ''}</p>)}
                  <div className="flex items-center gap-3 mt-0.5 text-[10px] text-zinc-400">
                    <span>{site.equipment_count ?? 0} machines</span>
                    <span>{site.issue_count ?? 0} faults</span>
                    {site.invoice_customer_ref && <span>Ref: {site.invoice_customer_ref}</span>}
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {!site.is_default && (
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); setHeadOffice(site); }}
                      disabled={hqBusyId === site.id}
                      className={`text-[10px] font-bold uppercase tracking-wider px-2 py-1 rounded-md border transition-colors flex items-center gap-1 ${
                        site.is_head_office
                          ? 'bg-amber-50 text-amber-700 border-amber-200 hover:bg-amber-100'
                          : 'bg-white text-zinc-600 border-zinc-200 hover:border-amber-300 hover:text-amber-700'
                      }`}
                      data-testid={`org-site-hq-toggle-${site.id}`}
                      title={site.is_head_office ? 'Clear Head Office flag' : 'Mark as Head Office'}
                    >
                      {hqBusyId === site.id ? <Loader2 size={10} className="animate-spin" /> : <Crown size={10} />}
                      {site.is_head_office ? 'HQ' : 'Set HQ'}
                    </button>
                  )}
                  {!site.is_default && <ChevronRight size={14} className="text-zinc-400" />}
                </div>
              </div>
              {!site.is_default && (<SiteModulesOverride siteId={site.id} siteName={site.name} theme="light" />)}
              {site.is_default && (<p className="mt-2 text-[11px] text-zinc-400 italic">Default fallback site — overrides apply once a real site is created.</p>)}
            </div>
          ))}
        </div>
      )}

      {/* Iter 216h53 — Click-to-open Site Details + Equipment drawer */}
      {selectedSite && (
        <SiteDetailDrawer
          orgId={org.id}
          site={selectedSite}
          onClose={() => setSelectedSite(null)}
          onSaved={() => { loadSites(); }}
        />
      )}
    </div>
  );
};

export default OrgSitesPanel;
