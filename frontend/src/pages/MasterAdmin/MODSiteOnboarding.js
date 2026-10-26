/**
 * Master Admin — MOD Equipment Onboarding & Site Readiness.
 *
 * Pulse Fitness onboards equipment on behalf of MOD sites (thousands of
 * machines) so a site is ready to use on day one — mirroring the commercial
 * bulk-import flow. Also surfaces a per-site go-live checklist.
 *
 * Endpoints:
 *   GET  /api/master-admin/mod-estate/site-readiness
 *   GET  /api/master-admin/mod-estate/equipment-template.xlsx | .csv
 *   POST /api/master-admin/bulk-import/equipment?organization_id=<site>
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import {
  Download, Upload, Loader2, CheckCircle2, AlertCircle, FileSpreadsheet,
  Dumbbell, Users, Truck, FileText, ClipboardCheck, RefreshCw, ShieldCheck,
  Link2, Inbox, ThumbsUp, Undo2, Bell, Eye, X, AlertTriangle, Copy, Mail, Sparkles, Trash2, Timer,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { notify } from '@/components/notifications';
import AIKitImportModal from './AIKitImportModal';

const API = process.env.REACT_APP_BACKEND_URL + '/api';

const STEP_META = {
  equipment: { label: 'Equipment', icon: Dumbbell },
  staff: { label: 'Staff', icon: Users },
  suppliers: { label: 'Suppliers', icon: Truck },
  documents: { label: 'Documents', icon: FileText },
  checks: { label: 'Check Sheets', icon: ClipboardCheck },
};

const downloadBlob = async (path, filename, token) => {
  const r = await fetch(`${API}${path}`, { headers: { Authorization: `Bearer ${token}` } });
  if (!r.ok) throw new Error(`Download failed: ${r.status}`);
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
};

const MODSiteOnboarding = () => {
  const token = localStorage.getItem('token');
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);
  const [sites, setSites] = useState([]);
  const [totals, setTotals] = useState(null);
  const [loading, setLoading] = useState(true);
  const [uploadingId, setUploadingId] = useState(null);
  const [aiKitSite, setAiKitSite] = useState(null);
  const [deleteSite, setDeleteSite] = useState(null);
  const [confirmName, setConfirmName] = useState('');
  const [deleting, setDeleting] = useState(false);
  const [result, setResult] = useState(null);
  const [filter, setFilter] = useState('all'); // all | needs-equipment | ready
  const [captures, setCaptures] = useState([]);
  const [linkBusyId, setLinkBusyId] = useState(null);
  const [reviewBusyId, setReviewBusyId] = useState(null);
  const [remindBusyId, setRemindBusyId] = useState(null);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [lastBulkRunId, setLastBulkRunId] = useState(null);
  const [skipDups, setSkipDups] = useState(true);
  const [review, setReview] = useState(null);   // { loading, detail } for the diff modal
  const [emailStatus, setEmailStatus] = useState(null);
  const [emailBusy, setEmailBusy] = useState(false);
  const [kitDrill, setKitDrill] = useState(null);   // { site, category, loading, items }
  const [providerModal, setProviderModal] = useState(null); // { site }
  const [estateSuppliers, setEstateSuppliers] = useState([]);
  const [provForm, setProvForm] = useState({ mode: 'existing', estate_supplier_id: '', name: '', email: '', phone: '', contact_name: '' });
  const [provBusy, setProvBusy] = useState(false);
  const fileInput = useRef(null);
  const targetSite = useRef(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [readiness, caps, mailSt] = await Promise.all([
        axios.get(`${API}/master-admin/mod-estate/site-readiness`, { headers }),
        axios.get(`${API}/master-admin/mod-estate/captures`, { headers }),
        axios.get(`${API}/master-admin/mod-estate/readiness-email/status`, { headers }).catch(() => null),
      ]);
      setSites(readiness.data?.sites || []);
      setTotals(readiness.data?.totals || null);
      setCaptures(caps.data?.captures || []);
      if (mailSt?.data) setEmailStatus(mailSt.data);
    } catch (e) {
      notify.error('Could not load MOD sites', e?.response?.data?.detail || 'Server error');
    } finally {
      setLoading(false);
    }
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  const openProviderModal = async (site) => {
    setProviderModal({ site });
    setProvForm({ mode: 'existing', estate_supplier_id: '', name: '', email: '', phone: '', contact_name: '' });
    try {
      const { data } = await axios.get(`${API}/master-admin/mod-estate/suppliers`, { headers });
      setEstateSuppliers(data?.suppliers || []);
    } catch { setEstateSuppliers([]); }
  };

  const saveProvider = async ({ clear } = {}) => {
    if (!providerModal?.site) return;
    let body;
    if (clear) {
      body = { clear: true };
    } else if (provForm.mode === 'existing') {
      if (!provForm.estate_supplier_id) { notify.error('Pick a provider', 'Select an existing provider or add a new one.'); return; }
      body = { estate_supplier_id: provForm.estate_supplier_id };
    } else {
      if (!provForm.name.trim()) { notify.error('Name required', 'Enter the provider name.'); return; }
      body = { name: provForm.name.trim(), email: provForm.email.trim(), phone: provForm.phone.trim(), contact_name: provForm.contact_name.trim() };
    }
    setProvBusy(true);
    try {
      const { data } = await axios.put(
        `${API}/master-admin/mod-estate/sites/${providerModal.site.id}/service-provider`, body, { headers });
      if (clear) notify.success('Overseas provider removed', 'This site now routes jobs to Pulse Fitness only.');
      else notify.success('Overseas provider saved', data?.provider?.allocated === false
        ? 'Assigned, but it has no email yet — add one so it receives job emails.'
        : 'Both Pulse Fitness and this provider will now be emailed when a job is logged.');
      setProviderModal(null);
      await load();
    } catch (e) {
      notify.error('Could not update provider', e?.response?.data?.detail || 'Server error');
    } finally { setProvBusy(false); }
  };

  // ── SLA editor ─────────────────────────────────────────────────
  const [slaModal, setSlaModal] = useState(null); // { site }
  const [slaForm, setSlaForm] = useState({ response_hours: '', fix_hours: '', use_default: true });
  const [slaBusy, setSlaBusy] = useState(false);

  const openSlaModal = (site) => {
    const sla = site.sla || {};
    const isCustom = sla.response_source === 'custom' || sla.fix_source === 'custom';
    setSlaForm({
      response_hours: String(sla.response_hours ?? sla.default_response_hours ?? ''),
      fix_hours: String(sla.fix_hours ?? sla.default_fix_hours ?? ''),
      use_default: !isCustom,
    });
    setSlaModal({ site });
  };

  const saveSla = async () => {
    if (!slaModal?.site) return;
    let body;
    if (slaForm.use_default) {
      body = { use_default: true };
    } else {
      const resp = parseInt(slaForm.response_hours, 10);
      const fix = parseInt(slaForm.fix_hours, 10);
      if (!resp || !fix) { notify.error('Enter both targets', 'Response and fix hours are required.'); return; }
      if (fix < resp) { notify.error('Invalid targets', 'Fix target must be greater than or equal to response.'); return; }
      body = { response_hours: resp, fix_hours: fix };
    }
    setSlaBusy(true);
    try {
      await axios.put(`${API}/master-admin/mod-estate/sites/${slaModal.site.id}/sla`, body, { headers });
      notify.success('SLA saved', slaForm.use_default ? 'Reset to the default target for this site.' : 'Custom SLA target applied.');
      setSlaModal(null);
      await load();
    } catch (e) {
      notify.error('Could not save SLA', e?.response?.data?.detail || 'Server error');
    } finally { setSlaBusy(false); }
  };

  const sendReadinessEmail = async (emailOverride) => {
    setEmailBusy(true);
    try {
      const { data } = await axios.post(
        `${API}/master-admin/mod-estate/readiness-email/send`,
        { ...(emailOverride ? { email: emailOverride } : {}) },
        { headers },
      );
      if (data.sent) {
        notify.success(`Readiness sheet emailed to ${data.recipient}`, 'The Excel + summary was sent to HQ.');
      } else {
        notify.error('Email not sent', 'Resend may be unavailable in this environment (works in production).');
      }
      axios.get(`${API}/master-admin/mod-estate/readiness-email/status`, { headers })
        .then((r) => setEmailStatus(r.data)).catch(() => {});
    } catch (e) {
      notify.error('Could not send readiness email', e?.response?.data?.detail || 'Server error');
    } finally {
      setEmailBusy(false);
    }
  };

  const sendCaptureLink = async (site, emailOverride) => {
    setLinkBusyId(site.id);
    try {
      const { data } = await axios.post(
        `${API}/master-admin/mod-estate/capture-link`,
        { site_id: site.id, send_email: true, ...(emailOverride ? { email: emailOverride } : {}) },
        { headers },
      );
      try { await navigator.clipboard.writeText(data.share_url); } catch { /* clipboard blocked */ }
      if (data.emailed) {
        notify.success(`Capture link emailed to ${data.site_email}`, 'Link also copied to your clipboard as a backup.');
      } else if (data.needs_email) {
        const entered = window.prompt(`No email on file for ${site.name}. Enter the site's email to send the capture link:`, '');
        if (entered && entered.trim()) {
          await sendCaptureLink(site, entered.trim());
          return;
        }
        notify.info('Link created & copied', `No email sent. Send this to ${site.name}: ${data.share_url}`);
      } else {
        notify.success('Capture link ready & copied', `Send this to ${site.name}: ${data.share_url}`);
      }
      load();
    } catch (e) {
      notify.error('Could not create link', e?.response?.data?.detail || 'Server error');
    } finally {
      setLinkBusyId(null);
    }
  };

  const approveCapture = async (c, skipDuplicates = false) => {
    setReviewBusyId(c.id);
    try {
      const { data } = await axios.post(`${API}/master-admin/mod-estate/captures/${c.id}/approve`, { skip_duplicates: skipDuplicates }, { headers });
      const r = data.import_result || {};
      const dropped = data.skipped_duplicates || 0;
      notify.success(
        `Imported ${r.imported} machines into ${c.site_name}`,
        dropped ? `${dropped} flagged duplicate${dropped === 1 ? '' : 's'} skipped.` : (r.skipped ? `${r.skipped} skipped.` : 'Confirmed & imported.'),
      );
      setReview(null);
      load();
    } catch (e) {
      notify.error('Import failed', e?.response?.data?.detail || 'Server error');
    } finally {
      setReviewBusyId(null);
    }
  };

  const bulkApprove = async () => {
    const pending = captures.filter((c) => c.status === 'submitted').length;
    if (!pending) return;
    if (!window.confirm(`Confirm all ${pending} submitted site${pending === 1 ? '' : 's'} at once? Flagged duplicate rows will be skipped; only clean rows import.`)) return;
    setBulkBusy(true);
    try {
      const { data } = await axios.post(`${API}/master-admin/mod-estate/captures/bulk-approve`, { skip_duplicates: true }, { headers });
      notify.success(
        `Imported ${data.total_imported} machines across ${data.processed} site${data.processed === 1 ? '' : 's'}`,
        data.total_skipped_duplicates ? `${data.total_skipped_duplicates} flagged duplicate row(s) skipped. Report downloading…` : 'All clean rows imported. Report downloading…',
      );
      if (data.run_id) {
        setLastBulkRunId(data.run_id);
        downloadBlob(`/master-admin/mod-estate/bulk-report/${data.run_id}.xlsx`, `MOD_Bulk_Import_Report.xlsx`, token).catch(() => {});
      }
      load();
    } catch (e) {
      notify.error('Bulk confirm failed', e?.response?.data?.detail || 'Server error');
    } finally {
      setBulkBusy(false);
    }
  };

  const rejectCapture = async (c) => {
    const reason = window.prompt(`Ask ${c.site_name} to change something (they'll see this note):`, '');
    if (reason === null) return;
    setReviewBusyId(c.id);
    try {
      await axios.post(`${API}/master-admin/mod-estate/captures/${c.id}/reject`, { reason }, { headers });
      notify.success('Sent back to the site for changes');
      setReview(null);
      load();
    } catch (e) {
      notify.error('Could not send back', e?.response?.data?.detail || 'Server error');
    } finally {
      setReviewBusyId(null);
    }
  };

  const remindCapture = async (c, emailOverride) => {
    setRemindBusyId(c.id);
    try {
      const { data } = await axios.post(
        `${API}/master-admin/mod-estate/captures/${c.id}/remind`,
        { ...(emailOverride ? { email: emailOverride } : {}) }, { headers },
      );
      if (data.reminded) {
        notify.success(`Reminder emailed to ${data.site_email}`, `${c.site_name} — nudged to submit their equipment.`);
        load();
      } else if (data.needs_email) {
        const entered = window.prompt(`No email on file for ${c.site_name}. Enter an email to send the reminder:`, '');
        if (entered && entered.trim()) { await remindCapture(c, entered.trim()); return; }
      } else {
        notify.warning('Reminder not sent', 'Email could not be delivered — check the email service.');
      }
    } catch (e) {
      notify.error('Could not send reminder', e?.response?.data?.detail || 'Server error');
    } finally {
      setRemindBusyId(null);
    }
  };

  const openReview = async (c) => {
    setReview({ loading: true, id: c.id });
    try {
      const { data } = await axios.get(`${API}/master-admin/mod-estate/captures/${c.id}`, { headers });
      setSkipDups((data.duplicate_count || 0) > 0);
      setReview({ loading: false, detail: data, id: c.id });
    } catch (e) {
      notify.error('Could not load submission', e?.response?.data?.detail || 'Server error');
      setReview(null);
    }
  };

  const pickFileFor = (site) => { targetSite.current = site; fileInput.current?.click(); };

  const openKitDrill = async (site, category) => {
    setKitDrill({ site, category, loading: true, items: [] });
    try {
      const { data } = await axios.get(
        `${API}/master-admin/mod-estate/site/${encodeURIComponent(site.id)}/equipment-by-category`,
        { headers, params: { category } },
      );
      setKitDrill({ site, category, loading: false, items: data.items || [] });
    } catch (e) {
      notify.error('Could not load machines', e?.response?.data?.detail || 'Server error');
      setKitDrill(null);
    }
  };
  const [savingLocId, setSavingLocId] = useState(null);
  const saveEquipLocation = async (equipmentId, location, inputEl, prev) => {
    setSavingLocId(equipmentId);
    try {
      const { data } = await axios.patch(
        `${API}/master-admin/mod-estate/equipment/${encodeURIComponent(equipmentId)}`,
        { location }, { headers },
      );
      setKitDrill((k) => (k ? { ...k, items: k.items.map((m) => (m.id === equipmentId ? { ...m, location: data.location } : m)) } : k));
      notify.success('Location saved', data.location ? `Zone set to "${data.location}"` : 'Location cleared');
    } catch (e) {
      if (inputEl) inputEl.value = prev || ''; // revert so the UI reflects the actual saved state
      notify.error('Could not save location', e?.response?.data?.detail || 'Server error');
    } finally {
      setSavingLocId(null);
    }
  };

  const doDeleteSite = async () => {
    if (!deleteSite) return;
    setDeleting(true);
    try {
      const { data } = await axios.delete(
        `${API}/master-admin/mod-estate/sites/${encodeURIComponent(deleteSite.id)}`,
        { headers, params: { confirm_name: confirmName } },
      );
      notify.success('Site removed', `${data.name} and ${data.equipment_removed} item(s) removed.`);
      setDeleteSite(null); setConfirmName('');
      load();
    } catch (e) {
      notify.error('Could not remove site', e?.response?.data?.detail || 'Server error');
    } finally {
      setDeleting(false);
    }
  };
  const onFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    const site = targetSite.current;
    if (!file || !site) return;
    setUploadingId(site.id);
    setResult(null);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const { data } = await axios.post(
        `${API}/master-admin/bulk-import/equipment?organization_id=${encodeURIComponent(site.id)}`,
        fd,
        { headers: { ...headers, 'Content-Type': 'multipart/form-data' } },
      );
      setResult({ site, ...data });
      notify.success(
        `Imported ${data.imported} machines into ${site.name}`,
        data.skipped ? `${data.skipped} rows skipped — see details.` : 'All rows accepted.',
      );
      load();
    } catch (err) {
      notify.error('Equipment import failed', err?.response?.data?.detail || 'Server error');
    } finally {
      setUploadingId(null);
    }
  };

  const visible = sites.filter((s) => {
    if (filter === 'needs-equipment') return !s.steps.equipment.ready;
    if (filter === 'ready') return s.fully_ready;
    return true;
  });

  return (
    <div className="space-y-5" data-testid="mod-site-onboarding">
      <Card className="p-5 rounded-xl border-zinc-200">
        <div className="flex items-center gap-2 mb-2">
          <ShieldCheck size={18} className="text-cyan-600" />
          <h3 className="text-base font-extrabold tracking-tight">MOD equipment onboarding & readiness</h3>
        </div>
        <p className="text-xs text-zinc-600 leading-relaxed">
          Load each site's equipment on their behalf so the platform is ready the day they log in — just like a
          commercial site. Send the capture template to a site, then upload the completed sheet against that site.
          The checklist shows what each site still needs to go live.
        </p>
        <div className="flex flex-wrap gap-2 mt-4">
          <Button variant="outline" data-testid="mod-equip-template-xlsx"
            onClick={() => downloadBlob('/master-admin/mod-estate/equipment-template.xlsx', 'Equipment Import - Sicon Template.xlsx', token).catch((e) => notify.error('Template error', e.message))}>
            <FileSpreadsheet size={14} className="mr-1.5" /> Sicon template (Excel · send to sites)
          </Button>
          <Button variant="outline" data-testid="mod-equip-template-csv"
            onClick={() => downloadBlob('/master-admin/mod-estate/equipment-template.csv', 'Equipment Import - Sicon Template.csv', token).catch((e) => notify.error('Template error', e.message))}>
            <Download size={14} className="mr-1.5" /> Template (CSV)
          </Button>
          <Button variant="outline" onClick={load} data-testid="mod-equip-refresh">
            <RefreshCw size={14} className="mr-1.5" /> Refresh
          </Button>
          <Button variant="outline" data-testid="mod-readiness-export"
            onClick={() => downloadBlob('/master-admin/mod-estate/readiness-export.xlsx', 'MOD_Estate_Readiness.xlsx', token).catch((e) => notify.error('Export error', e.message))}>
            <FileSpreadsheet size={14} className="mr-1.5" /> Readiness checklist (Excel)
          </Button>
          <Button variant="outline" data-testid="mod-readiness-email-send" disabled={emailBusy}
            onClick={() => sendReadinessEmail()}>
            {emailBusy ? <Loader2 size={14} className="mr-1.5 animate-spin" /> : <Mail size={14} className="mr-1.5" />}
            Email readiness to HQ now
          </Button>
          {lastBulkRunId && (
            <Button variant="outline" data-testid="mod-bulk-report-download"
              onClick={() => downloadBlob(`/master-admin/mod-estate/bulk-report/${lastBulkRunId}.xlsx`, 'MOD_Bulk_Import_Report.xlsx', token).catch((e) => notify.error('Report error', e.message))}>
              <Download size={14} className="mr-1.5" /> Last bulk report
            </Button>
          )}
        </div>
        <input ref={fileInput} type="file" accept=".csv,.xlsx,text/csv" className="hidden" onChange={onFile} data-testid="mod-equip-file-input" />
        {emailStatus && (
          <p className="text-[11px] text-zinc-500 mt-3 flex items-center gap-1.5" data-testid="mod-readiness-email-status">
            <Mail size={12} className="text-cyan-600" />
            Auto-emailed to <strong className="text-zinc-700">{emailStatus.recipient}</strong> every Monday
            {typeof emailStatus.send_hour_utc === 'number' ? ` at ${String(emailStatus.send_hour_utc).padStart(2, '0')}:00 UTC` : ''}.
            {emailStatus.last_sent_at ? ` Last sent ${new Date(emailStatus.last_sent_at).toLocaleString()}.` : ' Not sent yet.'}
          </p>
        )}
      </Card>

      {totals && (
        <div className="flex flex-wrap gap-2 text-xs" data-testid="mod-equip-totals">
          {[
            { k: 'all', label: `${totals.sites} sites` },
            { k: 'needs-equipment', label: `${totals.no_equipment} need equipment` },
            { k: 'ready', label: `${totals.fully_ready} fully ready` },
          ].map((b) => (
            <button key={b.k} onClick={() => setFilter(b.k)}
              className={`px-3 py-1.5 rounded-full font-semibold border ${filter === b.k ? 'bg-[var(--color-brand-blue)] text-white border-transparent' : 'border-zinc-200 text-zinc-600 hover:border-zinc-300'}`}
              data-testid={`mod-equip-filter-${b.k}`}>
              {b.label}
            </button>
          ))}
        </div>
      )}

      {result && (
        <Card className="p-4 rounded-xl border-emerald-200 bg-emerald-50" data-testid="mod-equip-result">
          <div className="flex items-center gap-2 text-sm font-bold text-emerald-800">
            <CheckCircle2 size={15} /> {result.site.name}: {result.imported} imported
            {result.skipped ? <span className="text-amber-700"> · {result.skipped} skipped</span> : null}
          </div>
          {(result.errors || []).length > 0 && (
            <ul className="mt-2 list-disc pl-5 text-[11px] text-amber-800 space-y-0.5" data-testid="mod-equip-result-errors">
              {result.errors.slice(0, 8).map((e, i) => <li key={i}>{e}</li>)}
              {result.errors.length > 8 ? <li>… and {result.error_count - 8} more</li> : null}
            </ul>
          )}
        </Card>
      )}

      {captures.filter((c) => c.status === 'submitted').length > 0 && (
        <Card className="p-4 rounded-xl border-amber-200 bg-amber-50/50" data-testid="mod-capture-review-queue">
          <div className="flex items-center gap-2 mb-3">
            <Inbox size={16} className="text-amber-600" />
            <h4 className="text-sm font-extrabold text-amber-900">Site submissions to review</h4>
            <span className="text-[11px] text-amber-700">Nothing is imported until you confirm.</span>
            <div className="ml-auto">
              <Button size="sm" variant="outline" onClick={bulkApprove} disabled={bulkBusy} data-testid="mod-capture-bulk-approve">
                {bulkBusy ? <Loader2 size={13} className="animate-spin mr-1" /> : <ThumbsUp size={13} className="mr-1" />}
                Confirm all clean ({captures.filter((c) => c.status === 'submitted').length})
              </Button>
            </div>
          </div>
          <div className="space-y-2">
            {captures.filter((c) => c.status === 'submitted').map((c) => (
              <div key={c.id} className="flex flex-wrap items-center justify-between gap-2 bg-white rounded-lg border border-amber-200 px-3 py-2" data-testid={`mod-capture-review-${c.id}`}>
                <div className="text-sm">
                  <span className="font-bold text-zinc-800">{c.site_name}</span>
                  <span className="text-zinc-500"> · {c.row_count} machine{c.row_count === 1 ? '' : 's'}</span>
                  <span className="ml-2 text-[10px] uppercase font-bold px-1.5 py-0.5 rounded bg-amber-100 text-amber-700">Ready to review</span>
                </div>
                <div className="flex items-center gap-2">
                  <Button size="sm" variant="outline" onClick={() => openReview(c)} data-testid={`mod-capture-viewdiff-${c.id}`}>
                    <Eye size={13} className="mr-1" /> Review
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => rejectCapture(c)} disabled={reviewBusyId === c.id} data-testid={`mod-capture-reject-${c.id}`}>
                    <Undo2 size={13} className="mr-1" /> Request changes
                  </Button>
                  <Button size="sm" onClick={() => approveCapture(c)} disabled={reviewBusyId === c.id} data-testid={`mod-capture-approve-${c.id}`}>
                    {reviewBusyId === c.id ? <Loader2 size={13} className="animate-spin mr-1" /> : <ThumbsUp size={13} className="mr-1" />}
                    Confirm &amp; import
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {captures.filter((c) => c.status === 'open' || c.status === 'changes_requested').length > 0 && (
        <Card className="p-4 rounded-xl border-zinc-200" data-testid="mod-capture-awaiting">
          <div className="flex items-center gap-2 mb-3">
            <Bell size={16} className="text-zinc-500" />
            <h4 className="text-sm font-extrabold text-zinc-700">Awaiting sites (link sent, not yet submitted)</h4>
          </div>
          <div className="space-y-2">
            {captures.filter((c) => c.status === 'open' || c.status === 'changes_requested').map((c) => (
              <div key={c.id} className="flex flex-wrap items-center justify-between gap-2 bg-zinc-50 rounded-lg border border-zinc-200 px-3 py-2" data-testid={`mod-capture-awaiting-${c.id}`}>
                <div className="text-sm">
                  <span className="font-bold text-zinc-800">{c.site_name}</span>
                  {c.status === 'changes_requested'
                    ? <span className="ml-2 text-[10px] uppercase font-bold px-1.5 py-0.5 rounded bg-amber-100 text-amber-700">Changes requested</span>
                    : <span className="ml-2 text-[10px] uppercase font-bold px-1.5 py-0.5 rounded bg-zinc-100 text-zinc-500">Awaiting submission</span>}
                  {c.reminder_count ? <span className="ml-2 text-[11px] text-zinc-400">reminded {c.reminder_count}×</span> : null}
                </div>
                <div className="flex items-center gap-2">
                  <Button size="sm" variant="outline" onClick={() => { navigator.clipboard?.writeText(c.share_url); notify.success('Link copied'); }} data-testid={`mod-capture-copy-${c.id}`}>
                    <Copy size={13} className="mr-1" /> Copy link
                  </Button>
                  <Button size="sm" onClick={() => remindCapture(c)} disabled={remindBusyId === c.id} data-testid={`mod-capture-remind-${c.id}`}>
                    {remindBusyId === c.id ? <Loader2 size={13} className="animate-spin mr-1" /> : <Bell size={13} className="mr-1" />}
                    Remind
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {loading ? (
        <div className="p-8 text-center text-sm text-zinc-500" data-testid="mod-equip-loading">
          <Loader2 size={16} className="animate-spin inline mr-2" /> Loading MOD sites…
        </div>
      ) : visible.length === 0 ? (
        <Card className="p-8 text-center text-sm text-zinc-500 rounded-xl" data-testid="mod-equip-empty">
          No MOD sites yet. Create sites in <strong>MOD Estate Setup</strong> or <strong>MOD Sites (CSV bulk)</strong> first.
        </Card>
      ) : (
        <div className="space-y-3">
          {visible.map((s) => (
            <Card key={s.id} className="p-4 rounded-xl border-zinc-200" data-testid={`mod-equip-site-${s.id}`}>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-bold text-sm text-zinc-800">{s.name}</span>
                    {s.force && <span className="text-[10px] uppercase font-bold px-1.5 py-0.5 rounded bg-zinc-100 text-zinc-600">{s.force}</span>}
                    {s.is_overseas && <span className="text-[10px] uppercase font-bold px-1.5 py-0.5 rounded bg-amber-100 text-amber-700">Overseas</span>}
                    <span className={`text-[10px] uppercase font-bold px-1.5 py-0.5 rounded ${s.fully_ready ? 'bg-emerald-100 text-emerald-700' : 'bg-zinc-100 text-zinc-500'}`} data-testid={`mod-equip-progress-${s.id}`}>
                      {s.ready_count}/{s.total_steps} ready
                    </span>
                  </div>
                  {/* Service providers — who receives job emails for this site.
                      Pulse Fitness always; overseas sites also route to their
                      assigned external provider. */}
                  <div className="flex flex-wrap items-center gap-1.5 mt-2" data-testid={`mod-site-providers-${s.id}`}>
                    <span className="inline-flex items-center gap-1 text-[10px] uppercase font-bold tracking-wide text-zinc-400">
                      <Truck size={11} /> Serviced by
                    </span>
                    <span className="inline-flex items-center text-[11px] font-semibold px-2 py-0.5 rounded-full bg-sky-50 text-sky-800 border border-sky-100"
                      title="Pulse Fitness MOD Service desk — always notified when a job is logged">
                      Pulse Fitness
                    </span>
                    {s.is_overseas && (
                      s.service_provider ? (
                        <span className="inline-flex items-center text-[11px] font-semibold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-800 border border-emerald-100"
                          title={s.service_provider_email ? `Overseas provider · ${s.service_provider_email} (emailed on every job)` : 'Overseas provider — no email set, so it will NOT receive job emails'}
                          data-testid={`mod-site-overseas-provider-${s.id}`}>
                          Overseas: {s.service_provider}
                          {!s.service_provider_email && <AlertCircle size={11} className="ml-1 text-amber-500" />}
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200"
                          title="This overseas site has no external service provider assigned — only Pulse Fitness is notified"
                          data-testid={`mod-site-overseas-provider-${s.id}`}>
                          <AlertCircle size={11} /> No overseas provider assigned
                        </span>
                      )
                    )}
                    {s.is_overseas && (
                      <button type="button" onClick={() => openProviderModal(s)}
                        className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full border border-zinc-300 text-zinc-600 hover:text-zinc-900 hover:border-zinc-400 transition-colors"
                        data-testid={`mod-site-assign-provider-${s.id}`}>
                        <Truck size={11} /> {s.service_provider ? 'Change provider' : 'Assign provider'}
                      </button>
                    )}
                  </div>
                  {/* SLA targets — differ for UK vs overseas; editable per site. */}
                  {s.sla && (
                    <div className="flex flex-wrap items-center gap-1.5 mt-2" data-testid={`mod-site-sla-${s.id}`}>
                      <span className="inline-flex items-center gap-1 text-[10px] uppercase font-bold tracking-wide text-zinc-400">
                        <Timer size={11} /> SLA
                      </span>
                      <span className="inline-flex items-center text-[11px] font-semibold px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-800 border border-indigo-100"
                        title={`${s.sla.is_overseas ? 'Overseas' : 'UK'} site · ${s.sla.response_source === 'custom' || s.sla.fix_source === 'custom' ? 'custom target' : 'default target'}`}>
                        {s.sla.response_hours}h response · {s.sla.fix_hours}h fix
                      </span>
                      {(s.sla.response_source === 'custom' || s.sla.fix_source === 'custom') && (
                        <span className="inline-flex items-center text-[10px] font-bold px-1.5 py-0.5 rounded bg-amber-50 text-amber-700 border border-amber-200">Custom</span>
                      )}
                      <button type="button" onClick={() => openSlaModal(s)}
                        className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full border border-zinc-300 text-zinc-600 hover:text-zinc-900 hover:border-zinc-400 transition-colors"
                        data-testid={`mod-site-edit-sla-${s.id}`}>
                        <Timer size={11} /> Edit SLA
                      </button>
                    </div>
                  )}
                  {/* Checklist */}
                  <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2">
                    {Object.entries(s.steps).map(([key, v]) => {
                      const M = STEP_META[key]; const Icon = M?.icon || FileText;
                      return (
                        <span key={key} className={`inline-flex items-center gap-1.5 text-[11px] ${v.ready ? 'text-emerald-700' : 'text-zinc-400'}`} data-testid={`mod-equip-step-${key}-${s.id}`}>
                          {v.ready ? <CheckCircle2 size={12} /> : <AlertCircle size={12} />}
                          <Icon size={12} /> {M?.label || key} <strong>{v.count}</strong>
                        </span>
                      );
                    })}
                  </div>
                  {/* Kit by category — equipment mix at a glance */}
                  {(s.kit_by_category || []).length > 0 && (
                    <div className="flex flex-wrap items-center gap-1.5 mt-2.5" data-testid={`mod-equip-kit-cat-${s.id}`}>
                      <span className="inline-flex items-center gap-1 text-[10px] uppercase font-bold tracking-wide text-zinc-400">
                        <Dumbbell size={11} /> Kit by category
                      </span>
                      {s.kit_by_category.map((c) => (
                        <button key={c.category} type="button"
                          onClick={() => openKitDrill(s, c.category)}
                          className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full bg-cyan-50 text-cyan-800 border border-cyan-100 hover:bg-cyan-100 hover:border-cyan-300 transition-colors cursor-pointer"
                          title={`View the ${c.count} ${c.category} machine${c.count === 1 ? '' : 's'}`}
                          data-testid={`mod-equip-kit-cat-${s.id}-${String(c.category).toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}>
                          {c.category} <strong className="text-cyan-900">{c.count}</strong>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <Button size="sm" variant="outline" onClick={() => sendCaptureLink(s)} disabled={linkBusyId === s.id} data-testid={`mod-equip-capture-link-${s.id}`}>
                    {linkBusyId === s.id ? <Loader2 size={14} className="animate-spin mr-1.5" /> : <Link2 size={14} className="mr-1.5" />}
                    Send capture link
                  </Button>
                  <Button size="sm" onClick={() => setAiKitSite(s)} data-testid={`mod-equip-import-${s.id}`}>
                    <Sparkles size={14} className="mr-1.5" /> Import equipment
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => { setDeleteSite(s); setConfirmName(''); }}
                    className="text-red-600 border-red-200 hover:bg-red-50" data-testid={`mod-site-delete-${s.id}`}>
                    <Trash2 size={14} className="mr-1.5" /> Remove
                  </Button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {review && (
        <div className="fixed inset-0 z-[120] flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.7)' }} data-testid="mod-capture-review-modal">
          <div className="bg-white rounded-2xl w-full max-w-5xl max-h-[88vh] flex flex-col shadow-2xl">
            {review.loading || !review.detail ? (
              <div className="p-10 text-center text-zinc-500"><Loader2 className="animate-spin inline mr-2" size={16} /> Loading submission…</div>
            ) : (
              <>
                <div className="flex items-start justify-between gap-3 p-5 border-b border-zinc-200">
                  <div>
                    <h3 className="text-base font-extrabold text-zinc-900">{review.detail.capture.site_name} — equipment submission</h3>
                    <p className="text-xs text-zinc-500 mt-1">
                      {review.detail.row_count} machine{review.detail.row_count === 1 ? '' : 's'} entered ·
                      {review.detail.existing_equipment_count} already on the platform ·
                      {review.detail.duplicate_count > 0
                        ? <span className="text-red-600 font-semibold"> {review.detail.duplicate_count} likely duplicate{review.detail.duplicate_count === 1 ? '' : 's'} flagged</span>
                        : <span className="text-emerald-600 font-semibold"> no duplicates detected</span>}
                    </p>
                  </div>
                  <button onClick={() => setReview(null)} className="p-1.5 rounded-full hover:bg-zinc-100" aria-label="Close" data-testid="mod-capture-review-close"><X size={16} /></button>
                </div>

                <div className="overflow-auto p-5 flex-1">
                  <table className="w-full text-xs border-collapse" data-testid="mod-capture-diff-table">
                    <thead>
                      <tr className="text-left text-zinc-500 border-b border-zinc-200">
                        <th className="py-2 pr-3">#</th>
                        {['name', 'equipment_type', 'manufacturer', 'model', 'serial_number', 'asset_number', 'location'].map((k) => (
                          <th key={k} className="py-2 pr-3 font-semibold whitespace-nowrap">{review.detail.field_labels[k] || k}</th>
                        ))}
                        <th className="py-2 pr-3">Flags</th>
                      </tr>
                    </thead>
                    <tbody>
                      {review.detail.rows.map((a) => {
                        const dup = a.flags.some((f) => f.startsWith('duplicate') || f === 'possible_duplicate');
                        return (
                          <tr key={a.index} className={`border-b border-zinc-100 ${dup ? 'bg-red-50/60' : ''}`} data-testid={`mod-capture-diff-row-${a.index}`}>
                            <td className="py-2 pr-3 text-zinc-400">{a.index + 1}</td>
                            {['name', 'equipment_type', 'manufacturer', 'model', 'serial_number', 'asset_number', 'location'].map((k) => (
                              <td key={k} className="py-2 pr-3 text-zinc-700 whitespace-nowrap max-w-[160px] truncate" title={a.row[k] || ''}>{a.row[k] || <span className="text-zinc-300">—</span>}</td>
                            ))}
                            <td className="py-2 pr-3">
                              <div className="flex flex-wrap gap-1">
                                {a.flags.length === 0 && <span className="text-emerald-600">✓</span>}
                                {a.flags.map((f) => {
                                  const map = {
                                    duplicate_serial: ['Duplicate serial', 'bg-red-100 text-red-700'],
                                    duplicate_in_sheet: ['Repeated in sheet', 'bg-amber-100 text-amber-700'],
                                    possible_duplicate: ['Possible duplicate', 'bg-amber-100 text-amber-700'],
                                    missing_name: ['Missing name', 'bg-red-100 text-red-700'],
                                  };
                                  const [label, cls] = map[f] || [f, 'bg-zinc-100 text-zinc-600'];
                                  return <span key={f} className={`inline-flex items-center gap-1 text-[10px] font-semibold px-1.5 py-0.5 rounded ${cls}`}><AlertTriangle size={9} /> {label}</span>;
                                })}
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                <div className="flex items-center justify-between gap-2 p-4 border-t border-zinc-200 bg-zinc-50 rounded-b-2xl">
                  <label className="flex items-center gap-2 text-[12px] text-zinc-600 cursor-pointer select-none" data-testid="mod-capture-skip-dups-label">
                    <input type="checkbox" checked={skipDups} onChange={(e) => setSkipDups(e.target.checked)} data-testid="mod-capture-skip-dups" className="rounded" />
                    Skip the {review.detail.duplicate_count} flagged duplicate row{review.detail.duplicate_count === 1 ? '' : 's'} on import
                  </label>
                  <div className="flex items-center gap-2">
                    <Button size="sm" variant="outline" onClick={() => rejectCapture(review.detail.capture)} disabled={reviewBusyId === review.detail.capture.id} data-testid="mod-capture-modal-reject">
                      <Undo2 size={13} className="mr-1" /> Request changes
                    </Button>
                    <Button size="sm" onClick={() => approveCapture(review.detail.capture, skipDups)} disabled={reviewBusyId === review.detail.capture.id} data-testid="mod-capture-modal-approve">
                      {reviewBusyId === review.detail.capture.id ? <Loader2 size={13} className="animate-spin mr-1" /> : <ThumbsUp size={13} className="mr-1" />}
                      {skipDups && review.detail.duplicate_count > 0 ? `Import ${review.detail.row_count - review.detail.duplicate_count} clean` : 'Confirm & import'}
                    </Button>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {aiKitSite && (
        <AIKitImportModal
          site={aiKitSite}
          headers={headers}
          guided
          onClose={() => setAiKitSite(null)}
          onImported={() => load()}
        />
      )}

      {deleteSite && (
        <div className="fixed inset-0 z-[130] flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.7)' }} data-testid="mod-site-delete-modal" onClick={() => !deleting && setDeleteSite(null)}>
          <div className="bg-white rounded-2xl w-full max-w-md p-5 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center gap-2 mb-2">
              <AlertTriangle size={18} className="text-red-600" />
              <h3 className="text-base font-extrabold text-zinc-900">Remove MOD site</h3>
            </div>
            <p className="text-xs text-zinc-600 mb-3">
              This permanently removes <b>{deleteSite.name}</b> and all its equipment, staff logins and suppliers. This can't be undone.
            </p>
            <label className="text-[11px] font-semibold text-zinc-500">Type the site name to confirm</label>
            <input value={confirmName} onChange={(e) => setConfirmName(e.target.value)} placeholder={deleteSite.name}
              className="w-full mt-1 px-3 py-2 text-sm rounded-md border border-zinc-300 focus:border-red-400 focus:outline-none"
              data-testid="mod-site-delete-confirm-input" autoFocus />
            <div className="flex justify-end gap-2 mt-4">
              <button onClick={() => setDeleteSite(null)} disabled={deleting} className="px-3 py-1.5 text-xs font-semibold text-zinc-600" data-testid="mod-site-delete-cancel">Cancel</button>
              <button onClick={doDeleteSite}
                disabled={deleting || confirmName.trim().toLowerCase() !== (deleteSite.name || '').trim().toLowerCase()}
                className="px-3 py-1.5 text-xs font-bold rounded-md bg-red-600 text-white disabled:opacity-40 inline-flex items-center gap-1.5"
                data-testid="mod-site-delete-confirm">
                {deleting ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />} Remove site
              </button>
            </div>
          </div>
        </div>
      )}

      {kitDrill && (
        <div className="fixed inset-0 z-[120] flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.7)' }} data-testid="mod-kit-drill-modal" onClick={() => setKitDrill(null)}>
          <div className="bg-white rounded-2xl w-full max-w-3xl max-h-[85vh] flex flex-col shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-start justify-between gap-3 p-5 border-b border-zinc-200">
              <div>
                <div className="flex items-center gap-2">
                  <Dumbbell size={16} className="text-cyan-600" />
                  <h3 className="text-base font-extrabold text-zinc-900">{kitDrill.category}</h3>
                  <span className="text-[10px] uppercase font-bold px-1.5 py-0.5 rounded bg-cyan-100 text-cyan-700">{kitDrill.items.length} machine{kitDrill.items.length === 1 ? '' : 's'}</span>
                </div>
                <p className="text-xs text-zinc-500 mt-1">{kitDrill.site.name}</p>
              </div>
              <button onClick={() => setKitDrill(null)} className="p-1.5 rounded-full hover:bg-zinc-100" aria-label="Close" data-testid="mod-kit-drill-close"><X size={16} /></button>
            </div>
            <div className="overflow-auto p-5 flex-1">
              {kitDrill.loading ? (
                <div className="py-10 text-center text-sm text-zinc-500"><Loader2 size={16} className="animate-spin inline mr-2" /> Loading machines…</div>
              ) : kitDrill.items.length === 0 ? (
                <div className="py-10 text-center text-sm text-zinc-500" data-testid="mod-kit-drill-empty">No machines found in this category.</div>
              ) : (
                <>
                <table className="w-full text-xs border-collapse" data-testid="mod-kit-drill-table">
                  <thead>
                    <tr className="text-left text-zinc-500 border-b border-zinc-200">
                      <th className="py-2 pr-3">#</th>
                      <th className="py-2 pr-3 font-semibold">Name</th>
                      <th className="py-2 pr-3 font-semibold">Manufacturer</th>
                      <th className="py-2 pr-3 font-semibold">Model</th>
                      <th className="py-2 pr-3 font-semibold whitespace-nowrap">Serial</th>
                      <th className="py-2 pr-3 font-semibold whitespace-nowrap">Asset #</th>
                      <th className="py-2 pr-3 font-semibold whitespace-nowrap">Location / zone</th>
                    </tr>
                  </thead>
                  <tbody>
                    {kitDrill.items.map((m, i) => (
                      <tr key={m.id || i} className="border-b border-zinc-100" data-testid={`mod-kit-drill-row-${m.id || i}`}>
                        <td className="py-2 pr-3 text-zinc-400">{i + 1}</td>
                        <td className="py-2 pr-3 text-zinc-800 font-medium">{m.name}</td>
                        <td className="py-2 pr-3 text-zinc-700">{m.manufacturer || <span className="text-zinc-300">—</span>}</td>
                        <td className="py-2 pr-3 text-zinc-700">{m.model || <span className="text-zinc-300">—</span>}</td>
                        <td className="py-2 pr-3 text-zinc-700 whitespace-nowrap">{m.serial_number || <span className="text-zinc-300">—</span>}</td>
                        <td className="py-2 pr-3 text-zinc-700 whitespace-nowrap">{m.asset_number || <span className="text-zinc-300">—</span>}</td>
                        <td className="py-2 pr-2">
                          <div className="flex items-center gap-1">
                            <input
                              list="mod-kit-drill-zones"
                              defaultValue={m.location || ''}
                              placeholder="e.g. Main Gym"
                              disabled={savingLocId === m.id}
                              onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur(); }}
                              onBlur={(e) => {
                                const v = e.target.value.trim();
                                if (v !== (m.location || '')) saveEquipLocation(m.id, v, e.target, m.location || '');
                              }}
                              className="w-32 rounded border border-zinc-300 px-2 py-1 text-xs focus:outline-none focus:border-cyan-500 disabled:opacity-50"
                              data-testid={`mod-kit-location-input-${m.id}`}
                            />
                            {savingLocId === m.id && <Loader2 size={12} className="animate-spin text-cyan-600" />}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <datalist id="mod-kit-drill-zones">
                  {Array.from(new Set(kitDrill.items.map((m) => (m.location || '').trim()).filter(Boolean))).map((loc) => (
                    <option key={loc} value={loc} />
                  ))}
                </datalist>
                <p className="text-[11px] text-zinc-500 mt-3" data-testid="mod-kit-location-hint">
                  Set each machine's location/zone here — the reporter's Fault Wizard groups machines by these zones so it matches your real gym layout. Press Enter or click away to save.
                </p>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {providerModal && (
        <div className="fixed inset-0 z-[130] flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.7)' }} data-testid="mod-provider-modal" onClick={() => !provBusy && setProviderModal(null)}>
          <div className="bg-white rounded-2xl w-full max-w-md p-5 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center gap-2 mb-1">
              <Truck size={18} className="text-cyan-600" />
              <h3 className="text-base font-extrabold text-zinc-900">Overseas service provider</h3>
            </div>
            <p className="text-xs text-zinc-500 mb-4">
              <b>{providerModal.site.name}</b> — jobs logged here always email <b>Pulse Fitness</b>. Assign an overseas provider and they'll be emailed too.
            </p>

            <div className="flex gap-1 mb-3 p-0.5 bg-zinc-100 rounded-lg">
              <button type="button" onClick={() => setProvForm((f) => ({ ...f, mode: 'existing' }))}
                className={`flex-1 text-[11px] font-bold py-1.5 rounded-md ${provForm.mode === 'existing' ? 'bg-white shadow text-zinc-900' : 'text-zinc-500'}`}
                data-testid="mod-provider-mode-existing">Pick existing</button>
              <button type="button" onClick={() => setProvForm((f) => ({ ...f, mode: 'new' }))}
                className={`flex-1 text-[11px] font-bold py-1.5 rounded-md ${provForm.mode === 'new' ? 'bg-white shadow text-zinc-900' : 'text-zinc-500'}`}
                data-testid="mod-provider-mode-new">Add new</button>
            </div>

            {provForm.mode === 'existing' ? (
              <div>
                <label className="text-[11px] font-semibold text-zinc-500">Estate provider registry</label>
                <select value={provForm.estate_supplier_id}
                  onChange={(e) => setProvForm((f) => ({ ...f, estate_supplier_id: e.target.value }))}
                  className="w-full mt-1 px-3 py-2 text-sm rounded-md border border-zinc-300 focus:border-cyan-400 focus:outline-none bg-white"
                  data-testid="mod-provider-select">
                  <option value="">Select a provider…</option>
                  {estateSuppliers.map((sup) => (
                    <option key={sup.id} value={sup.id}>
                      {sup.name}{sup.email ? ` · ${sup.email}` : ' (no email)'}
                    </option>
                  ))}
                </select>
                {estateSuppliers.length === 0 && (
                  <p className="text-[11px] text-zinc-400 mt-1">No providers in the registry yet — use “Add new”.</p>
                )}
              </div>
            ) : (
              <div className="space-y-2">
                <input value={provForm.name} onChange={(e) => setProvForm((f) => ({ ...f, name: e.target.value }))}
                  placeholder="Provider name *" className="w-full px-3 py-2 text-sm rounded-md border border-zinc-300 focus:border-cyan-400 focus:outline-none" data-testid="mod-provider-name" autoFocus />
                <input value={provForm.email} onChange={(e) => setProvForm((f) => ({ ...f, email: e.target.value }))}
                  placeholder="Email (so they receive job alerts)" className="w-full px-3 py-2 text-sm rounded-md border border-zinc-300 focus:border-cyan-400 focus:outline-none" data-testid="mod-provider-email" />
                <div className="flex gap-2">
                  <input value={provForm.contact_name} onChange={(e) => setProvForm((f) => ({ ...f, contact_name: e.target.value }))}
                    placeholder="Contact name" className="w-1/2 px-3 py-2 text-sm rounded-md border border-zinc-300 focus:border-cyan-400 focus:outline-none" data-testid="mod-provider-contact" />
                  <input value={provForm.phone} onChange={(e) => setProvForm((f) => ({ ...f, phone: e.target.value }))}
                    placeholder="Phone" className="w-1/2 px-3 py-2 text-sm rounded-md border border-zinc-300 focus:border-cyan-400 focus:outline-none" data-testid="mod-provider-phone" />
                </div>
              </div>
            )}

            <div className="flex items-center justify-between gap-2 mt-5">
              <div>
                {providerModal.site.service_provider && (
                  <button onClick={() => saveProvider({ clear: true })} disabled={provBusy}
                    className="text-[11px] font-semibold text-red-600 hover:text-red-700 disabled:opacity-40" data-testid="mod-provider-clear">
                    Remove provider
                  </button>
                )}
              </div>
              <div className="flex gap-2">
                <button onClick={() => setProviderModal(null)} disabled={provBusy} className="px-3 py-1.5 text-xs font-semibold text-zinc-600" data-testid="mod-provider-cancel">Cancel</button>
                <button onClick={() => saveProvider()} disabled={provBusy}
                  className="px-3 py-1.5 text-xs font-bold rounded-md bg-cyan-600 text-white disabled:opacity-40 inline-flex items-center gap-1.5" data-testid="mod-provider-save">
                  {provBusy ? <Loader2 size={13} className="animate-spin" /> : <CheckCircle2 size={13} />} Save provider
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* SLA editor modal */}
      {slaModal && (
        <div className="fixed inset-0 z-[130] flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.7)' }} data-testid="mod-sla-modal" onClick={() => !slaBusy && setSlaModal(null)}>
          <div className="w-full max-w-md rounded-2xl bg-white shadow-2xl overflow-hidden" onClick={(e) => e.stopPropagation()}>
            <div className="px-5 py-4 border-b border-zinc-100 flex items-center justify-between">
              <div>
                <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-indigo-600">SLA targets</div>
                <div className="text-base font-extrabold text-zinc-900">{slaModal.site.name}</div>
              </div>
              <button onClick={() => setSlaModal(null)} className="p-1.5 rounded-lg hover:bg-zinc-100 text-zinc-500" data-testid="mod-sla-close"><X size={16} /></button>
            </div>
            <div className="p-5 space-y-4">
              <div className="text-[12px] text-zinc-600">
                {slaModal.site.sla?.is_overseas ? 'Overseas' : 'UK'} site. Default is{' '}
                <strong>{slaModal.site.sla?.default_response_hours}h response / {slaModal.site.sla?.default_fix_hours}h fix</strong>.
              </div>
              <label className="flex items-center gap-2 text-sm text-zinc-800 cursor-pointer" data-testid="mod-sla-use-default">
                <input type="checkbox" checked={slaForm.use_default}
                  onChange={(e) => setSlaForm((f) => ({ ...f, use_default: e.target.checked }))} />
                Use the default target for this {slaModal.site.sla?.is_overseas ? 'overseas' : 'UK'} site
              </label>
              {!slaForm.use_default && (
                <div className="grid grid-cols-2 gap-3">
                  <label className="block">
                    <span className="text-[11px] font-bold uppercase tracking-wide text-zinc-500">Response (hours)</span>
                    <input type="number" min="1" max="8760" value={slaForm.response_hours}
                      onChange={(e) => setSlaForm((f) => ({ ...f, response_hours: e.target.value }))}
                      className="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm" data-testid="mod-sla-response-input" />
                  </label>
                  <label className="block">
                    <span className="text-[11px] font-bold uppercase tracking-wide text-zinc-500">Fix (hours)</span>
                    <input type="number" min="1" max="8760" value={slaForm.fix_hours}
                      onChange={(e) => setSlaForm((f) => ({ ...f, fix_hours: e.target.value }))}
                      className="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm" data-testid="mod-sla-fix-input" />
                  </label>
                </div>
              )}
              <div className="flex items-center justify-end gap-2 pt-2">
                <button onClick={() => setSlaModal(null)} disabled={slaBusy}
                  className="px-3 py-2 rounded-lg text-sm font-semibold text-zinc-600 hover:bg-zinc-100" data-testid="mod-sla-cancel">Cancel</button>
                <button onClick={saveSla} disabled={slaBusy}
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-bold bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50" data-testid="mod-sla-save">
                  {slaBusy ? <Loader2 size={13} className="animate-spin" /> : <CheckCircle2 size={13} />} Save SLA
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default MODSiteOnboarding;
