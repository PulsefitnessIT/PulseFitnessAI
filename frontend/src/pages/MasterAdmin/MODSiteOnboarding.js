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
  Link2, Inbox, ThumbsUp, Undo2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { notify } from '@/components/notifications';

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
  const [result, setResult] = useState(null);
  const [filter, setFilter] = useState('all'); // all | needs-equipment | ready
  const [captures, setCaptures] = useState([]);
  const [linkBusyId, setLinkBusyId] = useState(null);
  const [reviewBusyId, setReviewBusyId] = useState(null);
  const fileInput = useRef(null);
  const targetSite = useRef(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [readiness, caps] = await Promise.all([
        axios.get(`${API}/master-admin/mod-estate/site-readiness`, { headers }),
        axios.get(`${API}/master-admin/mod-estate/captures`, { headers }),
      ]);
      setSites(readiness.data?.sites || []);
      setTotals(readiness.data?.totals || null);
      setCaptures(caps.data?.captures || []);
    } catch (e) {
      notify.error('Could not load MOD sites', e?.response?.data?.detail || 'Server error');
    } finally {
      setLoading(false);
    }
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  const sendCaptureLink = async (site) => {
    setLinkBusyId(site.id);
    try {
      const { data } = await axios.post(`${API}/master-admin/mod-estate/capture-link`, { site_id: site.id }, { headers });
      try { await navigator.clipboard.writeText(data.share_url); } catch { /* clipboard blocked */ }
      notify.success('Capture link ready & copied', `Send this to ${site.name}: ${data.share_url}`);
      load();
    } catch (e) {
      notify.error('Could not create link', e?.response?.data?.detail || 'Server error');
    } finally {
      setLinkBusyId(null);
    }
  };

  const approveCapture = async (c) => {
    setReviewBusyId(c.id);
    try {
      const { data } = await axios.post(`${API}/master-admin/mod-estate/captures/${c.id}/approve`, {}, { headers });
      const r = data.import_result || {};
      notify.success(`Imported ${r.imported} machines into ${c.site_name}`, r.skipped ? `${r.skipped} skipped.` : 'Confirmed & imported.');
      load();
    } catch (e) {
      notify.error('Import failed', e?.response?.data?.detail || 'Server error');
    } finally {
      setReviewBusyId(null);
    }
  };

  const rejectCapture = async (c) => {
    const reason = window.prompt(`Ask ${c.site_name} to change something (they'll see this note):`, '');
    if (reason === null) return;
    setReviewBusyId(c.id);
    try {
      await axios.post(`${API}/master-admin/mod-estate/captures/${c.id}/reject`, { reason }, { headers });
      notify.success('Sent back to the site for changes');
      load();
    } catch (e) {
      notify.error('Could not send back', e?.response?.data?.detail || 'Server error');
    } finally {
      setReviewBusyId(null);
    }
  };

  const pickFileFor = (site) => { targetSite.current = site; fileInput.current?.click(); };

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
            onClick={() => downloadBlob('/master-admin/mod-estate/equipment-template.xlsx', 'MOD_Equipment_Capture_Template.xlsx', token).catch((e) => notify.error('Template error', e.message))}>
            <FileSpreadsheet size={14} className="mr-1.5" /> Capture template (Excel · send to sites)
          </Button>
          <Button variant="outline" data-testid="mod-equip-template-csv"
            onClick={() => downloadBlob('/master-admin/mod-estate/equipment-template.csv', 'MOD_Equipment_Capture_Template.csv', token).catch((e) => notify.error('Template error', e.message))}>
            <Download size={14} className="mr-1.5" /> Template (CSV)
          </Button>
          <Button variant="outline" onClick={load} data-testid="mod-equip-refresh">
            <RefreshCw size={14} className="mr-1.5" /> Refresh
          </Button>
        </div>
        <input ref={fileInput} type="file" accept=".csv,.xlsx,text/csv" className="hidden" onChange={onFile} data-testid="mod-equip-file-input" />
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

      {captures.filter((c) => c.status === 'submitted' || c.status === 'changes_requested').length > 0 && (
        <Card className="p-4 rounded-xl border-amber-200 bg-amber-50/50" data-testid="mod-capture-review-queue">
          <div className="flex items-center gap-2 mb-3">
            <Inbox size={16} className="text-amber-600" />
            <h4 className="text-sm font-extrabold text-amber-900">Site submissions to review</h4>
            <span className="text-[11px] text-amber-700">Nothing is imported until you confirm.</span>
          </div>
          <div className="space-y-2">
            {captures.filter((c) => c.status === 'submitted' || c.status === 'changes_requested').map((c) => (
              <div key={c.id} className="flex flex-wrap items-center justify-between gap-2 bg-white rounded-lg border border-amber-200 px-3 py-2" data-testid={`mod-capture-review-${c.id}`}>
                <div className="text-sm">
                  <span className="font-bold text-zinc-800">{c.site_name}</span>
                  <span className="text-zinc-500"> · {c.row_count} machine{c.row_count === 1 ? '' : 's'}</span>
                  {c.status === 'changes_requested'
                    ? <span className="ml-2 text-[10px] uppercase font-bold px-1.5 py-0.5 rounded bg-zinc-100 text-zinc-500">Awaiting site</span>
                    : <span className="ml-2 text-[10px] uppercase font-bold px-1.5 py-0.5 rounded bg-amber-100 text-amber-700">Ready to review</span>}
                </div>
                {c.status === 'submitted' && (
                  <div className="flex items-center gap-2">
                    <Button size="sm" variant="outline" onClick={() => rejectCapture(c)} disabled={reviewBusyId === c.id} data-testid={`mod-capture-reject-${c.id}`}>
                      <Undo2 size={13} className="mr-1" /> Request changes
                    </Button>
                    <Button size="sm" onClick={() => approveCapture(c)} disabled={reviewBusyId === c.id} data-testid={`mod-capture-approve-${c.id}`}>
                      {reviewBusyId === c.id ? <Loader2 size={13} className="animate-spin mr-1" /> : <ThumbsUp size={13} className="mr-1" />}
                      Confirm & import
                    </Button>
                  </div>
                )}
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
                </div>
                <div className="flex items-center gap-2">
                  <Button size="sm" variant="outline" onClick={() => sendCaptureLink(s)} disabled={linkBusyId === s.id} data-testid={`mod-equip-capture-link-${s.id}`}>
                    {linkBusyId === s.id ? <Loader2 size={14} className="animate-spin mr-1.5" /> : <Link2 size={14} className="mr-1.5" />}
                    Send capture link
                  </Button>
                  <Button size="sm" onClick={() => pickFileFor(s)} disabled={uploadingId === s.id} data-testid={`mod-equip-import-${s.id}`}>
                    {uploadingId === s.id ? <Loader2 size={14} className="animate-spin mr-1.5" /> : <Upload size={14} className="mr-1.5" />}
                    {uploadingId === s.id ? 'Importing…' : 'Import equipment'}
                  </Button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
};

export default MODSiteOnboarding;
