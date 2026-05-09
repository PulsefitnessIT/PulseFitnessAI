/**
 * ManufacturerDomainsPanel (Iter 215b — combined with catalogue stats)
 *
 * Single surface for managing the manufacturer-domain list AND seeing
 * per-domain image-catalogue coverage. Merges the former "Catalogue"
 * and "Crawl Domains" sub-tabs into one table so operators don't have
 * to bounce between them. Each row shows:
 *   • Brand / key (editable)
 *   • Domain     (editable)
 *   • Source     (Seed vs Override override)
 *   • Products   (from catalogue stats)
 *   • Last ingested (from catalogue stats)
 *   • Actions    (Sync Now, Edit, Delete-override)
 *
 * Top bar carries the bulk "Ingest all priority domains" CTA + a job
 * status card so large ingests are still first-class.
 */
import React, { useEffect, useState, useCallback, useMemo } from 'react';
import axios from 'axios';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  Globe, Plus, Trash2, Loader2, RefreshCw, ExternalLink, Pencil, X, Check, Zap,
  Sparkles, CheckCircle2, Eraser, Wand2,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { SkeletonLine } from '@/components/shared/Skeleton';

const fmtTimestamp = (iso) => {
  if (!iso) return 'Never';
  try { return new Date(iso).toLocaleString('en-GB'); } catch { return iso; }
};

const ManufacturerDomainsPanel = () => {
  const { API } = useAuth();
  const [rows, setRows] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState({ key: '', domain: '', label: '' });
  const [editingKey, setEditingKey] = useState(null);
  const [editDraft, setEditDraft] = useState({ domain: '', label: '' });
  const [filter, setFilter] = useState('');
  const [ingestStatus, setIngestStatus] = useState({});
  const [cleanupBusy, setCleanupBusy] = useState(false);
  const [rematchBusy, setRematchBusy] = useState(false);

  /* Iter 216e — one-click cleanup of social/press noise from the
     manufacturer catalogue (across all domains) so future matchers
     don't get fooled by Instagram archive pages. Idempotent — safe
     to spam. */
  const handleCleanup = async () => {
    setCleanupBusy(true);
    try {
      const r = await axios.post(`${API}/master-admin/catalogue/cleanup`, {}, { headers: headers() });
      const n = r.data?.deleted ?? 0;
      notify.success(n > 0 ? `Removed ${n} non-product entries` : 'Catalogue is clean');
      loadAll();
    } catch (e) {
      notify.error(`Cleanup failed: ${e.response?.data?.detail || e.message}`);
    }
    setCleanupBusy(false);
  };

  /* Iter 216e — re-run auto_match_equipment_to_specs for every
     equipment row in every org. Persists `spec_sheet_image` and
     `manufacturer_page_url` onto matched rows so the operations UI
     shows real product photos + brand-correct manufacturer links. */
  const handleRematch = async () => {
    setRematchBusy(true);
    try {
      const r = await axios.post(`${API}/master-admin/catalogue/rematch-equipment`, {}, { headers: headers() });
      const m = r.data?.matched ?? 0;
      const u = r.data?.unchanged ?? 0;
      const s = r.data?.skipped ?? 0;
      notify.success(`Re-match done · ${m} updated · ${u} unchanged · ${s} no match`);
    } catch (e) {
      notify.error(`Rematch failed: ${e.response?.data?.detail || e.message}`);
    }
    setRematchBusy(false);
  };
  const [job, setJob] = useState(null);

  const headers = () => ({ Authorization: `Bearer ${localStorage.getItem('token')}` });

  const loadDomains = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/master-admin/manufacturer-domains`, { headers: headers() });
      setRows(r.data?.rows || []);
    } catch (e) {
      notify.error('Could not load domains', e.response?.data?.detail);
    }
  }, [API]);

  const loadStats = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/master-admin/catalogue/stats`, { headers: headers() });
      setStats(r.data);
    } catch {
      // stats are supplementary; a silent failure still lets admins manage the domain list
    }
  }, [API]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    await Promise.all([loadDomains(), loadStats()]);
    setLoading(false);
  }, [loadDomains, loadStats]);

  useEffect(() => { loadAll(); }, [loadAll]);

  // Poll the active ingest-all job until it finishes, then refresh stats.
  useEffect(() => {
    if (!job?.job_id || job.status !== 'running') return undefined;
    let cancelled = false;
    const tick = async () => {
      try {
        const r = await axios.get(`${API}/master-admin/catalogue/jobs/${job.job_id}`, { headers: headers() });
        if (cancelled) return;
        setJob({ ...r.data, job_id: job.job_id });
        if (r.data.status !== 'running') loadStats();
      } catch {
        /* ignore polling errors */
      }
    };
    const id = setInterval(tick, 4000);
    return () => { cancelled = true; clearInterval(id); };
  }, [API, job?.job_id, job?.status, loadStats]);

  const upsert = async (payload) => {
    try {
      await axios.post(`${API}/master-admin/manufacturer-domains`, payload, { headers: headers() });
      notify.success('Saved', `${payload.label || payload.key} → ${payload.domain}`);
      await loadDomains();
      return true;
    } catch (e) {
      notify.error('Save failed', e.response?.data?.detail);
      return false;
    }
  };

  const handleAdd = async () => {
    if (!draft.key.trim() || !draft.domain.trim()) {
      notify.error('Missing fields', 'Brand key and domain are required');
      return;
    }
    setAdding(true);
    const ok = await upsert(draft);
    setAdding(false);
    if (ok) setDraft({ key: '', domain: '', label: '' });
  };

  const handleEditSave = async (row) => {
    const ok = await upsert({
      key: row.key,
      domain: editDraft.domain.trim(),
      label: editDraft.label.trim() || row.label,
      enabled: row.enabled !== false,
    });
    if (ok) setEditingKey(null);
  };

  const handleDelete = async (row) => {
    if (!window.confirm(`Remove override for "${row.label || row.key}"? The seed entry (if any) will become effective again.`)) return;
    try {
      await axios.delete(`${API}/master-admin/manufacturer-domains/${encodeURIComponent(row.key)}`, { headers: headers() });
      notify.success('Override removed', row.label || row.key);
      await loadDomains();
    } catch (e) {
      notify.error('Delete failed', e.response?.data?.detail);
    }
  };

  const handleSyncNow = async (row) => {
    if (!row.domain) return;
    setIngestStatus((s) => ({ ...s, [row.domain]: { status: 'starting' } }));
    try {
      const r = await axios.post(
        `${API}/master-admin/catalogue/ingest?domain=${encodeURIComponent(row.domain)}`,
        {}, { headers: headers() },
      );
      const jobId = r.data?.job_id;
      setIngestStatus((s) => ({ ...s, [row.domain]: { status: 'running', jobId } }));
      const poll = async () => {
        try {
          const j = await axios.get(`${API}/master-admin/catalogue/jobs/${jobId}`, { headers: headers() });
          if (j.data.status === 'running') {
            setTimeout(poll, 3000);
          } else {
            const result = (j.data.results || []).find((x) => x.domain === row.domain) || j.data.results?.[0] || {};
            setIngestStatus((s) => ({ ...s, [row.domain]: { status: j.data.status, ...result } }));
            if (result.error) {
              notify.error(`Sync failed for ${row.label || row.domain}`, result.error.slice(0, 120));
            } else {
              notify.success(
                `Synced ${row.label || row.domain}`,
                `Saved ${result.saved ?? 0}, skipped ${result.skipped ?? 0}${result.discovery === 'category_page_fallback' ? ' (category fallback)' : ''}.`,
              );
            }
            loadStats();
          }
        } catch {
          setIngestStatus((s) => ({ ...s, [row.domain]: { status: 'failed', error: 'poll failed' } }));
        }
      };
      setTimeout(poll, 1500);
    } catch (e) {
      setIngestStatus((s) => ({ ...s, [row.domain]: { status: 'failed' } }));
      notify.error('Could not start sync', e.response?.data?.detail);
    }
  };

  const triggerIngestAll = async () => {
    try {
      const r = await axios.post(`${API}/master-admin/catalogue/ingest`, {}, { headers: headers() });
      setJob(r.data);
      notify.info('Ingesting all priority domains…', 'This runs in the background. Stats refresh on completion.');
    } catch (e) {
      notify.error('Ingest failed to start', e.response?.data?.detail);
    }
  };

  const isRunning = job?.status === 'running';
  const completedDomains = useMemo(
    () => new Set((job?.results || []).map((r) => r.domain)),
    [job?.results],
  );

  // Merge domain rows with stats for each row.
  const statsByDomain = useMemo(() => {
    const m = {};
    (stats?.domains || []).forEach((d) => { m[d.domain] = d; });
    return m;
  }, [stats]);

  const filtered = rows.filter((r) => {
    if (!filter.trim()) return true;
    const q = filter.toLowerCase();
    return (r.label || '').toLowerCase().includes(q)
        || (r.key || '').toLowerCase().includes(q)
        || (r.domain || '').toLowerCase().includes(q);
  });

  const overrideCount = rows.filter((r) => r.source === 'override').length;
  const seedCount = rows.filter((r) => r.source === 'seed').length;

  return (
    <div className="space-y-4" data-testid="manufacturer-domains-panel">
      <Card className="p-5 border-zinc-200">
        <div className="flex items-start justify-between mb-4 flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <Globe size={20} className="text-zinc-700" />
            <div>
              <h3 className="text-base font-semibold text-zinc-900">Manufacturer crawl list</h3>
              <p className="text-xs text-zinc-500 mt-0.5">
                Domains the Image Catalogue ingest job crawls.
                Seed: <strong>{seedCount}</strong> · Overrides: <strong>{overrideCount}</strong>
                {stats && <> · Total products: <strong>{stats.total_products.toLocaleString()}</strong></>}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <Input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filter…"
              className="h-9 w-48"
              data-testid="domains-filter"
            />
            <Button
              onClick={triggerIngestAll}
              disabled={isRunning}
              className="bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white"
              data-testid="catalogue-ingest-all-btn"
            >
              {isRunning
                ? <><Loader2 size={14} className="mr-2 animate-spin" /> Ingesting…</>
                : <><Sparkles size={14} className="mr-2" /> Ingest all</>}
            </Button>
            {/* Iter 216e — strip Instagram / press / after-sales noise that
                some manufacturers (e.g. Pulse Fitness) publish under their
                own product URL slugs. Future ingests skip these via the
                tightened `SKIP_PATTERNS` regex; this button cleans
                already-ingested entries. Idempotent. */}
            <Button
              onClick={handleCleanup}
              disabled={cleanupBusy}
              variant="outline"
              size="sm"
              title="Remove social/press/after-sales URLs that pollute the catalogue"
              data-testid="catalogue-cleanup-btn"
            >
              {cleanupBusy
                ? <><Loader2 size={13} className="mr-1 animate-spin" /> Cleaning…</>
                : <><Eraser size={13} className="mr-1" /> Clean noise</>}
            </Button>
            {/* Iter 216e — push the latest catalogue images + manufacturer
                page URLs onto every equipment row in every org. Run after
                a fresh ingest to backfill photos for equipment that was
                logged before the catalogue had coverage. */}
            <Button
              onClick={handleRematch}
              disabled={rematchBusy}
              variant="outline"
              size="sm"
              title="Re-run auto-match across all equipment so cards show real product photos"
              data-testid="catalogue-rematch-btn"
            >
              {rematchBusy
                ? <><Loader2 size={13} className="mr-1 animate-spin" /> Matching…</>
                : <><Wand2 size={13} className="mr-1" /> Re-match equipment</>}
            </Button>
            <Button variant="outline" size="sm" onClick={loadAll} data-testid="domains-refresh">
              <RefreshCw size={13} className="mr-1" /> Refresh
            </Button>
          </div>
        </div>

        {/* Add row */}
        <div className="grid grid-cols-1 md:grid-cols-12 gap-2 p-3 bg-zinc-50 rounded-lg border border-dashed border-zinc-200" data-testid="domains-add-row">
          <Input
            value={draft.key}
            onChange={(e) => setDraft({ ...draft, key: e.target.value })}
            placeholder="brand key (e.g. acme fitness)"
            className="md:col-span-3 h-9"
            data-testid="domains-add-key"
          />
          <Input
            value={draft.label}
            onChange={(e) => setDraft({ ...draft, label: e.target.value })}
            placeholder="Display label (optional)"
            className="md:col-span-3 h-9"
            data-testid="domains-add-label"
          />
          <Input
            value={draft.domain}
            onChange={(e) => setDraft({ ...draft, domain: e.target.value })}
            placeholder="https://www.acmefitness.com"
            className="md:col-span-4 h-9"
            data-testid="domains-add-domain"
          />
          <Button
            onClick={handleAdd}
            disabled={adding}
            className="md:col-span-2 h-9 bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white"
            data-testid="domains-add-btn"
          >
            {adding ? <Loader2 size={14} className="animate-spin" /> : <><Plus size={14} className="mr-1" /> Add</>}
          </Button>
        </div>
      </Card>

      <Card className="border-zinc-200 overflow-hidden">
        {loading ? (
          <div className="p-4 space-y-3" data-testid="domains-loading">
            {[0,1,2,3,4].map((i) => (
              <div key={i} className="grid grid-cols-12 gap-3 items-center">
                <SkeletonLine className="col-span-3" />
                <SkeletonLine className="col-span-4" width="80%" />
                <SkeletonLine className="col-span-1" width="50%" />
                <SkeletonLine className="col-span-1" width="40%" />
                <SkeletonLine className="col-span-2" width="70%" />
                <SkeletonLine className="col-span-1" width="60%" />
              </div>
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <p className="text-zinc-400 text-sm text-center py-8">No domains match your filter.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-zinc-50 border-b border-zinc-200">
                <tr className="text-left text-[10px] uppercase tracking-wider text-zinc-500">
                  <th className="px-4 py-2.5 font-semibold">Brand / Key</th>
                  <th className="px-4 py-2.5 font-semibold">Domain</th>
                  <th className="px-4 py-2.5 font-semibold">Source</th>
                  <th className="px-4 py-2.5 font-semibold text-right">Products</th>
                  <th className="px-4 py-2.5 font-semibold">Last ingested</th>
                  <th className="px-4 py-2.5 font-semibold w-[160px] text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((row) => {
                  const editing = editingKey === row.key;
                  const s = statsByDomain[row.domain];
                  const wasJustRun = completedDomains.has(row.domain);
                  return (
                    <tr key={row.key} className="border-b border-zinc-100 last:border-0 hover:bg-zinc-50" data-testid={`domains-row-${row.key}`}>
                      <td className="px-4 py-2.5">
                        <div className="font-medium text-zinc-900">{row.label}</div>
                        <div className="text-[10px] text-zinc-400 font-mono">{row.key}</div>
                      </td>
                      <td className="px-4 py-2.5">
                        {editing ? (
                          <Input
                            value={editDraft.domain}
                            onChange={(e) => setEditDraft({ ...editDraft, domain: e.target.value })}
                            className="h-8 text-xs"
                            data-testid={`domains-edit-domain-${row.key}`}
                          />
                        ) : (
                          <a
                            href={`https://${row.domain}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-blue-600 hover:underline text-xs font-mono inline-flex items-center gap-1"
                          >
                            {row.domain}
                            <ExternalLink size={10} />
                          </a>
                        )}
                      </td>
                      <td className="px-4 py-2.5">
                        <Badge className={row.source === 'override' ? 'bg-amber-50 text-amber-700 border border-amber-200' : 'bg-zinc-100 text-zinc-600 border border-zinc-200'}>
                          {row.source === 'override' ? 'Override' : 'Seed'}
                        </Badge>
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        {s ? (
                          <Badge className={s.products > 0
                            ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                            : 'bg-amber-50 text-amber-700 border border-amber-200'}>
                            {s.products}
                          </Badge>
                        ) : (
                          <span className="text-zinc-300 text-xs">—</span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-zinc-600 text-xs whitespace-nowrap">
                        {fmtTimestamp(s?.last_ingested)}
                        {wasJustRun && <CheckCircle2 size={11} className="inline ml-1 text-emerald-600" />}
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        {editing ? (
                          <div className="flex items-center gap-1 justify-end">
                            <Button size="sm" variant="outline" className="h-7 px-2" onClick={() => setEditingKey(null)} data-testid={`domains-cancel-${row.key}`}>
                              <X size={13} />
                            </Button>
                            <Button size="sm" className="h-7 px-2 bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white" onClick={() => handleEditSave(row)} data-testid={`domains-save-${row.key}`}>
                              <Check size={13} />
                            </Button>
                          </div>
                        ) : (
                          <div className="flex items-center gap-1 justify-end">
                            <Button
                              size="sm"
                              variant="outline"
                              className="h-7 px-2"
                              onClick={() => handleSyncNow(row)}
                              disabled={ingestStatus[row.domain]?.status === 'running' || ingestStatus[row.domain]?.status === 'starting'}
                              title="Trigger a one-shot ingest of this domain now — no need to wait for the next scheduled poll."
                              data-testid={`domains-sync-${row.key}`}
                            >
                              {ingestStatus[row.domain]?.status === 'running' || ingestStatus[row.domain]?.status === 'starting'
                                ? <Loader2 size={12} className="animate-spin" />
                                : <Zap size={12} />}
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              className="h-7 px-2"
                              onClick={() => { setEditingKey(row.key); setEditDraft({ domain: row.domain, label: row.label }); }}
                              data-testid={`domains-edit-${row.key}`}
                            >
                              <Pencil size={12} />
                            </Button>
                            {row.source === 'override' && (
                              <Button
                                size="sm"
                                variant="outline"
                                className="h-7 px-2 text-rose-600 hover:bg-rose-50 border-rose-200"
                                onClick={() => handleDelete(row)}
                                data-testid={`domains-delete-${row.key}`}
                              >
                                <Trash2 size={12} />
                              </Button>
                            )}
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {job && (
        <Card className="p-5 bg-zinc-50 border-zinc-200" data-testid="catalogue-job-card">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-zinc-800">
              Latest ingestion job · <span className="font-mono text-xs">{job.job_id}</span>
            </h3>
            <Badge className={
              job.status === 'running' ? 'bg-blue-50 text-blue-700 border border-blue-200'
              : job.status === 'complete' ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
              : 'bg-rose-50 text-rose-700 border border-rose-200'
            }>
              {job.status}
            </Badge>
          </div>
          <div className="space-y-1 text-xs text-zinc-700">
            {(job.results || []).map((r) => (
              <div key={r.domain} className="flex items-center justify-between font-mono">
                <span>{r.domain}</span>
                <span>
                  {r.error
                    ? <span className="text-rose-600">error: {r.error.slice(0, 60)}</span>
                    : <>examined {r.examined ?? '?'} · saved {r.saved ?? '?'} · skipped {r.skipped ?? '?'}</>
                  }
                </span>
              </div>
            ))}
            {(job.results || []).length === 0 && (
              <p className="text-zinc-500 text-xs">Waiting for first domain result…</p>
            )}
          </div>
        </Card>
      )}
    </div>
  );
};

export default ManufacturerDomainsPanel;
