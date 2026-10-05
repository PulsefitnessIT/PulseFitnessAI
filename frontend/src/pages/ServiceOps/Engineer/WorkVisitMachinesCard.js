/**
 * WorkVisitMachinesCard — Iter 220d
 *
 * Per-machine work-report card shown inside the Engineer App's Complete
 * tab. Replicates the row-per-machine spreadsheet workflow that real
 * engineers use on PPM site visits (the dan_starr export):
 *
 *   Row 1  ·  BikeErg #03   ·  [✓] Serviced  [✓] Cleaned  ·  Notes…
 *   Row 2  ·  RowErg  #14   ·  [✓] Serviced  [ ] Cleaned  ·  Notes…
 *   ...
 *
 * Each row's notes field has the shared/personal `NotePresetChips`
 * palette attached, so recurring sentences become 1-tap entries.
 *
 * The "Apply to all rows below" action copies serviced/cleaned/notes
 * from the source row to subsequent rows — saves 8x typing on a PPM
 * visit where every BikeErg gets the same calibration note.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { Link } from 'react-router-dom';
import {
  Plus, Loader2, Trash2, Copy, Wrench, Sparkles, ChevronDown,
  ChevronUp, ChevronRight, Camera, X, PackagePlus, Package, CheckSquare, Square,
  ListChecks, Search, Check, Clock, ShieldCheck,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { chunkedUpload } from '@/utils/chunkedUpload';
import { stashPausedUpload } from '@/utils/engineerUploadStash';
import { outboxPost } from '@/utils/engineerOutbox';
import NotePresetChips from './NotePresetChips';
import MachineRowCustomFields from './MachineRowCustomFields';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const auth = () => ({
  headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
});

// Iter 220ea·21 — client idempotency key so an offline-queued
// "part used" replays exactly once when the connection returns.
const newIdemKey = () => (
  (typeof crypto !== 'undefined' && crypto.randomUUID)
    ? crypto.randomUUID()
    : `idem-${Date.now()}-${Math.random().toString(36).slice(2)}`
);

export default function WorkVisitMachinesCard({ caseId }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState(null);
  const [assetOptions, setAssetOptions] = useState([]);
  const [assetSearch, setAssetSearch] = useState('');
  // Iter 220cj — Site equipment picker (multi-select w/ Select All)
  const [sitePickerOpen, setSitePickerOpen] = useState(false);
  // Engineer-proposed equipment changes (office must approve before they apply)
  const [proposeOpen, setProposeOpen] = useState(false);
  const [proposals, setProposals] = useState([]);

  const loadProposals = useCallback(async () => {
    if (!caseId) return;
    try {
      const r = await axios.get(`${API}/svc/engineer/jobs/${caseId}/equipment-change-requests`, auth());
      setProposals(r.data?.requests || []);
    } catch { setProposals([]); }
  }, [caseId]);
  useEffect(() => { loadProposals(); }, [loadProposals]);

  const proposeRemoval = async (row) => {
    if (!row?.asset_id) { notify.error('This row has no linked asset to remove'); return; }
    const reason = window.prompt(`Propose removing "${row.asset_name}" from the site asset list?\n\nThe office will review before it is archived. Add a reason (optional):`, '');
    if (reason === null) return;
    try {
      await axios.post(`${API}/svc/engineer/equipment-change-requests`, {
        case_id: caseId, change_type: 'remove',
        equipment_id: row.asset_id, equipment_name: row.asset_name || '', reason,
      }, auth());
      notify.success('Removal proposed — sent to the office for review');
      loadProposals();
    } catch (e) { notify.error('Could not propose removal', e?.response?.data?.detail || e?.message); }
  };


  const load = useCallback(async () => {
    if (!caseId) { setLoading(false); return; }
    setLoading(true);
    try {
      const r = await axios.get(`${API}/svc/engineer/jobs/${caseId}/machines`, auth());
      const list = r.data?.machines || [];
      setRows(list);
      if (list.length && !expandedId) setExpandedId(list[0].id);
    } catch (e) {
      console.warn('[machines] load failed', e);
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [caseId, expandedId]);

  useEffect(() => { load(); }, [load]);  

  // Load equipment list for the asset picker — once per session is enough.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await axios.get(`${API}/equipment`, auth());
        if (cancelled) return;
        const trimmed = (r.data?.equipment || []).map(e => ({
          id: e.id,
          label: [e.manufacturer, e.model || e.name].filter(Boolean).join(' ').trim() || e.name || 'Equipment',
          serial: e.serial_number || '',
          equipment_type: e.equipment_type || '',
        }));
        setAssetOptions(trimmed);
      } catch (e) {
        setAssetOptions([]);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const patchRow = async (rowId, patch) => {
    // Optimistic.
    setRows((prev) => prev.map(r => r.id === rowId ? { ...r, ...patch } : r));
    try {
      const r = await axios.patch(
        `${API}/svc/engineer/jobs/${caseId}/machines/${rowId}`,
        patch,
        auth(),
      );
      setRows((prev) => prev.map(x => x.id === rowId ? r.data : x));
    } catch (e) {
      notify.error('Save failed', e?.response?.data?.detail || e?.message);
      load();
    }
  };

  const deleteRow = async (rowId) => {
    if (!window.confirm('Remove this machine from the report?')) return;
    try {
      await axios.delete(`${API}/svc/engineer/jobs/${caseId}/machines/${rowId}`, auth());
      setRows((prev) => prev.filter(x => x.id !== rowId));
    } catch (e) {
      notify.error('Could not remove', e?.response?.data?.detail || e?.message);
    }
  };

  const copyDown = async (rowId, fields) => {
    try {
      const r = await axios.post(
        `${API}/svc/engineer/jobs/${caseId}/machines/${rowId}/copy-down`,
        { fields },
        auth(),
      );
      notify.success(`Applied to ${r.data.updated} row${r.data.updated === 1 ? '' : 's'} below`);
      load();
    } catch (e) {
      notify.error('Copy-down failed', e?.response?.data?.detail || e?.message);
    }
  };

  const attachPhoto = async (rowId, file, caption = '') => {
    if (!file) return;
    try {
      // Iter 220ea·4 — Route through chunkedUpload so a 4G blip
      // drops one 1 MB chunk, not the entire upload. The stash
      // captures the session blob the moment init succeeds so
      // the engineer can resume from the paused-uploads pill if
      // the connection (or the tab) dies mid-flight.
      const uploaded = await chunkedUpload({
        baseURL: API,
        file,
        category: 'service-media',
        authHeaders: auth().headers,
        onSession: async ({ uploadId, totalChunks }) => {
          await stashPausedUpload({
            upload_id: uploadId,
            total_chunks: totalChunks,
            case_id: caseId,
            machine_row_id: rowId,
            filename: file.name || `photo-${Date.now()}.jpg`,
            size: file.size,
            content_type: file.type || 'image/jpeg',
            blob: file,
            caption: caption || '',
            kind: 'photo',
            saved_at: Date.now(),
          });
        },
      });
      const fileUrl = uploaded?.download_url || uploaded?.storage_path;
      const r = await axios.post(`${API}/svc/engineer/photos`, {
        case_id: caseId,
        machine_row_id: rowId,
        file_url: fileUrl,
        mime_type: uploaded?.content_type || 'image/jpeg',
        caption: caption || '',
      }, auth());
      // Optimistic insert into the row.
      setRows((prev) => prev.map(r2 => r2.id === rowId
        ? { ...r2, photos: [...(r2.photos || []), r.data] }
        : r2,
      ));
      // Upload landed cleanly — drop the stash row so it stops
      // counting against the paused-uploads pill.
      if (uploaded?.upload_method === 'chunked' && uploaded?.id) {
        // chunked path: session was stashed under upload_id which we
        // captured via onSession; we can't know it back here, so
        // delegate to a best-effort cleanup that walks the stash
        // for any row referencing this same case+filename+size and
        // drops it. Cheap, scoped, idempotent.
        try {
          const { listPausedUploads, dropPausedUpload: drop } = await import('@/utils/engineerUploadStash');
          for (const row of await listPausedUploads()) {
            if (row.case_id === caseId
                && row.filename === (file.name || '')
                && row.size === file.size) {
              await drop(row.upload_id);
            }
          }
        } catch { /* swallow */ }
      }
      notify.success('Photo attached');
    } catch (e) {
      // Stash row stays put — the resume sheet will pick it up.
      notify.error('Upload failed', e?.response?.data?.detail || e?.message);
    }
  };

  const removePhoto = async (rowId, photoId) => {
    if (!window.confirm('Remove this photo?')) return;
    try {
      await axios.delete(`${API}/svc/engineer/photos/${photoId}`, auth());
      setRows((prev) => prev.map(r => r.id === rowId
        ? { ...r, photos: (r.photos || []).filter(p => p.id !== photoId) }
        : r,
      ));
    } catch (e) {
      notify.error('Could not remove', e?.response?.data?.detail || e?.message);
    }
  };

  const filteredAssets = useMemo(() => {
    const needle = assetSearch.trim().toLowerCase();
    if (!needle) return assetOptions.slice(0, 50);
    return assetOptions.filter(a =>
      a.label.toLowerCase().includes(needle) ||
      (a.serial || '').toLowerCase().includes(needle),
    ).slice(0, 50);
  }, [assetOptions, assetSearch]);

  return (
    <div className="bg-white rounded-2xl border border-slate-200" data-testid="machines-card">
      {/* Iter 220ea·10 — Header + action bar redesign. The three
          actions used to sit in a wrap-cluster that stacked
          vertically on a 412 px phone; now they're an evenly
          spaced 3-up grid with clear labels. */}
      <div className="p-4 border-b border-slate-100">
        <div className="flex items-start gap-2 mb-3">
          <Wrench size={14} className="text-cyan-600 mt-0.5 shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-bold text-slate-900">
              Machines on this visit
            </p>
            <p className="text-[11px] text-slate-500 mt-0.5 leading-snug">
              One row per machine. Tick what you serviced or cleaned, then add notes.
            </p>
          </div>
        </div>
        {/* Iter 220ea·11 — "Add machine" removed. Every machine
            must be backed by a real asset record so the engineer
            picks "From site" (existing equipment for this gym)
            or "New asset" (create + attach). The old blank-row
            "Add machine" path created orphan rows with no asset
            linkage. */}
        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={() => setSitePickerOpen(true)}
            className="inline-flex flex-col items-center justify-center gap-1 py-2.5 rounded-xl border border-cyan-200 bg-cyan-50 text-cyan-700 text-xs font-extrabold hover:bg-cyan-100"
            data-testid="machines-load-from-site-btn"
            title="Show all equipment for this site and pick which ones to work on"
          >
            <Package size={16} />
            <span>From site</span>
          </button>
          <button
            type="button"
            onClick={() => setProposeOpen(true)}
            className="inline-flex flex-col items-center justify-center gap-1 py-2.5 rounded-xl border border-slate-200 bg-white text-slate-700 text-xs font-extrabold hover:bg-slate-50"
            data-testid="machines-propose-asset-btn"
            title="Propose a brand-new asset for this site — the office reviews it before it's added"
          >
            <PackagePlus size={16} />
            <span>Propose new</span>
          </button>
        </div>
        {proposals.length > 0 && (
          <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-2.5" data-testid="machines-proposals">
            <p className="text-[11px] font-extrabold uppercase tracking-wide text-amber-700 mb-1">Proposed changes · office review</p>
            <ul className="space-y-1">
              {proposals.map((p) => (
                <li key={p.id} className="text-[11px] text-amber-900 flex items-center justify-between gap-2" data-testid={`machine-proposal-${p.id}`}>
                  <span className="truncate">
                    {p.change_type === 'add' ? `Add: ${p.proposed?.name || ''}` : `Remove: ${p.equipment_name || ''}`}
                  </span>
                  <span className={`shrink-0 text-[9px] font-bold uppercase px-1.5 py-0.5 rounded-full ${p.status === 'pending' ? 'bg-amber-200 text-amber-800' : p.status === 'approved' ? 'bg-emerald-200 text-emerald-800' : 'bg-rose-200 text-rose-800'}`}>{p.status}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {loading ? (
        <div className="p-6 flex items-center justify-center text-slate-400">
          <Loader2 size={14} className="animate-spin mr-2" /> Loading…
        </div>
      ) : rows.length === 0 ? (
        <div className="p-6 text-center" data-testid="machines-empty">
          <p className="text-sm font-bold text-slate-900">No machines added yet</p>
          <p className="text-xs text-slate-500 mt-1">
            Tap <span className="font-bold">Add machine</span> for each Erg you serviced.
            You can still complete the job without adding any.
          </p>
        </div>
      ) : (
        <div className="divide-y divide-slate-100">
          {rows.map((row, idx) => (
            <MachineRow
              key={row.id}
              row={row}
              index={idx}
              caseId={caseId}
              expanded={expandedId === row.id}
              onExpand={() => setExpandedId(expandedId === row.id ? null : row.id)}
              onPatch={(patch) => patchRow(row.id, patch)}
              onDelete={() => deleteRow(row.id)}
              onCopyDown={(fields) => copyDown(row.id, fields)}
              onAttachPhoto={(file) => attachPhoto(row.id, file)}
              onRemovePhoto={(photoId) => removePhoto(row.id, photoId)}
              onProposeRemoval={() => proposeRemoval(row)}
              showCopyDown={idx < rows.length - 1}
              assetOptions={filteredAssets}
              assetSearch={assetSearch}
              setAssetSearch={setAssetSearch}
              refreshRows={load}
            />
          ))}
        </div>
      )}
      {/* Iter 220cj — Site equipment picker modal */}
      {sitePickerOpen ? (
        <SiteEquipmentPicker
          caseId={caseId}
          onClose={() => setSitePickerOpen(false)}
          onImported={() => { setSitePickerOpen(false); load(); }}
        />
      ) : null}
      {proposeOpen ? (
        <ProposeEquipmentModal
          caseId={caseId}
          onClose={() => setProposeOpen(false)}
          onProposed={() => { setProposeOpen(false); loadProposals(); }}
        />
      ) : null}
    </div>
  );
}

// Engineer proposes a brand-new asset for the site. Goes to the office review
// queue — nothing is added to the live asset list until approved.
function ProposeEquipmentModal({ caseId, onClose, onProposed }) {
  const [form, setForm] = useState({ name: '', equipment_type: '', manufacturer: '', model: '', serial_number: '', notes: '' });
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setForm((p) => ({ ...p, [k]: v }));
  const submit = async () => {
    if (!form.name.trim()) { notify.error('Give the equipment a name'); return; }
    setBusy(true);
    try {
      await axios.post(`${API}/svc/engineer/equipment-change-requests`, {
        case_id: caseId, change_type: 'add', proposed: form,
      }, auth());
      notify.success('New equipment proposed — sent to the office for review');
      onProposed?.();
    } catch (e) { notify.error('Could not propose', e?.response?.data?.detail || e?.message); }
    finally { setBusy(false); }
  };
  const inp = 'w-full mt-1 text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white';
  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-end sm:items-center justify-center p-0 sm:p-4" data-testid="propose-equipment-modal">
      <div className="bg-white w-full sm:max-w-md max-h-[92vh] sm:rounded-2xl rounded-t-2xl shadow-2xl flex flex-col overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-200 flex items-center justify-between">
          <p className="text-sm font-bold text-slate-900">Propose new equipment</p>
          <button onClick={onClose} className="w-9 h-9 rounded-xl border border-slate-200 flex items-center justify-center text-slate-600" data-testid="propose-equipment-close"><X size={16} /></button>
        </div>
        <div className="p-4 overflow-y-auto space-y-2.5">
          <p className="text-[11px] text-slate-500">The office reviews this before it's added to the site's asset list.</p>
          <div><label className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Name *</label>
            <input className={inp} value={form.name} onChange={(e) => set('name', e.target.value)} placeholder="e.g. Technogym Run 1000" data-testid="propose-name" /></div>
          <div className="grid grid-cols-2 gap-2">
            <div><label className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Type</label>
              <input className={inp} value={form.equipment_type} onChange={(e) => set('equipment_type', e.target.value)} placeholder="Treadmill" data-testid="propose-type" /></div>
            <div><label className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Serial no.</label>
              <input className={inp} value={form.serial_number} onChange={(e) => set('serial_number', e.target.value)} data-testid="propose-serial" /></div>
            <div><label className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Manufacturer</label>
              <input className={inp} value={form.manufacturer} onChange={(e) => set('manufacturer', e.target.value)} data-testid="propose-manufacturer" /></div>
            <div><label className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Model</label>
              <input className={inp} value={form.model} onChange={(e) => set('model', e.target.value)} data-testid="propose-model" /></div>
          </div>
          <div><label className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Notes</label>
            <textarea className={inp} rows={2} value={form.notes} onChange={(e) => set('notes', e.target.value)} data-testid="propose-notes" /></div>
        </div>
        <div className="px-4 py-3 border-t border-slate-200 flex gap-2">
          <button onClick={onClose} className="flex-1 border border-slate-300 rounded-xl py-2.5 text-sm font-semibold" data-testid="propose-cancel">Cancel</button>
          <button onClick={submit} disabled={busy} className="flex-1 bg-cyan-600 hover:bg-cyan-700 disabled:bg-slate-300 text-white rounded-xl py-2.5 text-sm font-bold inline-flex items-center justify-center gap-1.5" data-testid="propose-submit">
            {busy ? <><Loader2 size={12} className="animate-spin" /> Sending…</> : <><PackagePlus size={14} /> Propose</>}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────
// Iter 220cj — SiteEquipmentPicker
// Mobile-first multi-select sheet. Pulls every equipment record on the
// case's site, lets the engineer tick 1 / many / all, and bulk-attaches
// them as machine rows on the job. Already-attached items are ghosted.
// ─────────────────────────────────────────────────────────────────────

function SiteEquipmentPicker({ caseId, onClose, onImported }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [q, setQ] = useState('');
  const [selected, setSelected] = useState(() => new Set());
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError('');
      try {
        const r = await axios.get(
          `${API}/svc/engineer/jobs/${caseId}/site-equipment`, auth(),
        );
        if (cancelled) return;
        setItems(r.data?.site_equipment || []);
      } catch (e) {
        if (cancelled) return;
        setError(e?.response?.data?.detail || e?.message || 'Failed to load');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [caseId]);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return items;
    return items.filter((it) =>
      (it.name || '').toLowerCase().includes(needle)
      || (it.serial_number || '').toLowerCase().includes(needle)
      || (it.manufacturer || '').toLowerCase().includes(needle)
      || (it.equipment_type || '').toLowerCase().includes(needle),
    );
  }, [items, q]);

  const selectable = filtered.filter((i) => !i.already_on_job);
  const allSelected =
    selectable.length > 0 && selectable.every((i) => selected.has(i.id));
  const someSelected = selectable.some((i) => selected.has(i.id));

  const toggle = (id) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    setSelected((prev) => {
      if (allSelected) {
        const next = new Set(prev);
        selectable.forEach((i) => next.delete(i.id));
        return next;
      }
      const next = new Set(prev);
      selectable.forEach((i) => next.add(i.id));
      return next;
    });
  };

  const onAttach = async () => {
    if (selected.size === 0) return;
    setSubmitting(true);
    try {
      const r = await axios.post(
        `${API}/svc/engineer/jobs/${caseId}/machines/bulk-from-site`,
        { equipment_ids: Array.from(selected) },
        auth(),
      );
      const inserted = r.data?.inserted || 0;
      const skipped = r.data?.skipped || 0;
      notify.success(
        `Added ${inserted} machine${inserted === 1 ? '' : 's'}` +
        (skipped > 0 ? ` · skipped ${skipped} already on job` : ''),
      );
      onImported?.();
    } catch (e) {
      notify.error('Could not attach',
                   e?.response?.data?.detail || e?.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 flex items-end sm:items-center justify-center p-0 sm:p-4"
      data-testid="site-equipment-picker"
    >
      <div className="bg-white w-full sm:max-w-lg max-h-[92vh] sm:rounded-2xl rounded-t-2xl shadow-2xl flex flex-col overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-200 flex items-center justify-between gap-3">
          <div className="flex-1 min-w-0">
            <p className="text-sm font-bold text-slate-900">Pre-load from site</p>
            <p className="text-[11px] text-slate-500 leading-tight">
              Tick one, several, or Select all
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="w-9 h-9 rounded-xl border border-slate-200 flex items-center justify-center text-slate-600 hover:bg-slate-50"
            data-testid="site-equipment-picker-close"
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>

        <div className="px-4 pt-3 pb-2 border-b border-slate-100 space-y-2">
          <div className="relative">
            <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
            <input
              type="text"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Filter by name, serial, manufacturer…"
              className="w-full pl-9 pr-3 py-2 rounded-xl border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500"
              data-testid="site-equipment-picker-search"
            />
          </div>
          {selectable.length > 0 ? (
            <button
              type="button"
              onClick={toggleAll}
              className="w-full inline-flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 text-xs font-bold text-slate-700 hover:bg-slate-50"
              data-testid="site-equipment-picker-select-all"
            >
              {allSelected
                ? <><CheckSquare size={12} /> Deselect all ({selectable.length})</>
                : someSelected
                  ? <><ListChecks size={12} /> Select all ({selectable.length})</>
                  : <><Square size={12} /> Select all ({selectable.length})</>}
            </button>
          ) : null}
        </div>

        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center py-10 text-slate-400">
              <Loader2 size={14} className="animate-spin mr-2" /> Loading site equipment…
            </div>
          ) : error ? (
            <div className="m-4 bg-rose-50 border border-rose-200 rounded-xl p-3 text-xs text-rose-700">
              {error}
            </div>
          ) : filtered.length === 0 ? (
            <div className="px-4 py-10 text-center" data-testid="site-equipment-picker-empty">
              <Package size={24} className="mx-auto text-slate-300 mb-2" />
              <p className="text-sm font-bold text-slate-900">
                {q ? 'No matches' : 'No equipment for this site yet'}
              </p>
              <p className="text-xs text-slate-500 mt-1">
                {q ? 'Adjust your search.' : 'Add some via the Equipment tab — they\'ll appear here on every future job.'}
              </p>
            </div>
          ) : (
            <ul className="divide-y divide-slate-100" data-testid="site-equipment-picker-list">
              {filtered.map((it) => {
                const ticked = selected.has(it.id);
                const disabled = it.already_on_job;
                return (
                  <li key={it.id}>
                    <button
                      type="button"
                      onClick={() => !disabled && toggle(it.id)}
                      disabled={disabled}
                      className={`w-full text-left px-4 py-3 flex items-center gap-3 ${
                        disabled
                          ? 'opacity-50 cursor-not-allowed'
                          : ticked
                            ? 'bg-cyan-50'
                            : 'hover:bg-slate-50'
                      }`}
                      data-testid={`site-equipment-item-${it.id}`}
                    >
                      <span className="w-5 h-5 flex-shrink-0">
                        {ticked
                          ? <CheckSquare size={20} className="text-cyan-600" />
                          : <Square size={20} className="text-slate-400" />}
                      </span>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-bold text-slate-900 truncate">
                          {it.name}
                          <span className="ml-1.5 text-[11px] font-medium text-slate-500">
                            {it.manufacturer ? `${it.manufacturer} ` : ''}{it.model || ''}
                          </span>
                        </p>
                        <p className="text-[11px] text-slate-500 truncate flex items-center gap-2 flex-wrap">
                          {it.equipment_type && <span>{it.equipment_type}</span>}
                          {it.serial_number && <span className="font-mono">SN {it.serial_number}</span>}
                          {it.location && <span>· {it.location}</span>}
                          {disabled && <span className="text-emerald-700 font-bold">· Already on job</span>}
                        </p>
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <div className="px-4 py-3 border-t border-slate-200 flex gap-2">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 border border-slate-300 rounded-xl py-2.5 text-sm font-semibold"
            data-testid="site-equipment-picker-cancel"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={submitting || selected.size === 0}
            onClick={onAttach}
            className="flex-1 bg-cyan-600 hover:bg-cyan-700 disabled:bg-slate-300 text-white rounded-xl py-2.5 text-sm font-bold inline-flex items-center justify-center gap-1.5"
            data-testid="site-equipment-picker-attach"
          >
            {submitting
              ? <><Loader2 size={12} className="animate-spin" /> Adding…</>
              : <><Plus size={12} /> Add {selected.size || ''}</>}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Iter 220ea·12 · Per-machine parts widgets ────────────────────
// Two compact inline widgets that surface parts tagged to a single
// machine row. Both reuse the existing engineer parts endpoints
// (`/parts/use` for consumed parts, `/parts-requests` for parts
// the engineer wants ops to order for a return visit). Each widget
// is self-fetching so it can live inside the per-row expansion
// without the card having to ferry data through props.

function MachineRowPartsPickerInline({ onPick, onCancel, busy }) {
  const [q, setQ] = useState('');
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [qty, setQty] = useState(1);
  const [picked, setPicked] = useState(null);

  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(async () => {
      if (!q || q.length < 2) { setResults([]); return; }
      setSearching(true);
      try {
        const r = await axios.get(`${API}/svc/parts`, {
          ...auth(), params: { q, limit: 8 },
        });
        if (!cancelled) setResults(r.data?.items || []);
      } catch { if (!cancelled) setResults([]); }
      finally { if (!cancelled) setSearching(false); }
    }, 250);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [q]);

  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-2 space-y-2"
         data-testid="machine-parts-picker">
      {!picked ? (
        <>
          <div className="relative">
            <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              autoFocus
              type="text"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search parts by name or SKU…"
              className="w-full pl-7 pr-2 py-1.5 text-xs border border-slate-200 rounded-lg bg-white focus:outline-none focus:ring-1 focus:ring-cyan-300"
              data-testid="machine-parts-search-input"
            />
          </div>
          {searching && (
            <p className="text-[11px] text-slate-500">Searching…</p>
          )}
          {!searching && q.length >= 2 && results.length === 0 && (
            <p className="text-[11px] text-slate-500">
              No matches. Use the Parts tab to request an unlisted part.
            </p>
          )}
          {results.length > 0 && (
            <ul className="space-y-1">
              {results.map((p) => (
                <li key={p.sku}>
                  <button
                    type="button"
                    onClick={() => setPicked(p)}
                    className="w-full text-left flex items-center justify-between gap-2 px-2 py-1.5 rounded-lg bg-white border border-slate-200 hover:bg-cyan-50"
                    data-testid={`machine-parts-pick-${p.sku}`}
                  >
                    <div className="min-w-0 flex-1">
                      <p className="text-xs font-bold text-slate-900 truncate">{p.name || p.sku}</p>
                      <p className="text-[10px] text-slate-500 font-mono">{p.sku}</p>
                    </div>
                    <ChevronRight size={12} className="text-slate-400" />
                  </button>
                </li>
              ))}
            </ul>
          )}
          <button
            type="button"
            onClick={onCancel}
            className="w-full text-center text-[11px] text-slate-500 hover:text-slate-700 underline underline-offset-2"
            data-testid="machine-parts-picker-cancel"
          >
            Cancel
          </button>
        </>
      ) : (
        <div className="space-y-2">
          <div className="rounded-lg bg-white border border-slate-200 px-2 py-1.5">
            <p className="text-xs font-bold text-slate-900">{picked.name || picked.sku}</p>
            <p className="text-[10px] text-slate-500 font-mono">{picked.sku}</p>
          </div>
          <div className="flex items-center gap-2">
            <label className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Qty</label>
            <input
              type="number"
              min={1}
              max={999}
              value={qty}
              onChange={(e) => setQty(Math.max(1, Math.min(999, parseInt(e.target.value || '1', 10))))}
              className="w-16 text-xs px-2 py-1 border border-slate-200 rounded-lg bg-white"
              data-testid="machine-parts-qty-input"
            />
            <button
              type="button"
              onClick={() => setPicked(null)}
              className="ml-auto text-[10px] text-slate-500 underline"
              data-testid="machine-parts-pick-back"
            >
              Change
            </button>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onCancel}
              className="flex-1 px-2 py-1.5 rounded-lg border border-slate-200 bg-white text-slate-700 text-[11px] font-extrabold uppercase tracking-wider"
              data-testid="machine-parts-picker-cancel-2"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => onPick(picked, qty)}
              disabled={busy}
              className="flex-1 px-2 py-1.5 rounded-lg bg-cyan-600 text-white text-[11px] font-extrabold uppercase tracking-wider hover:bg-cyan-700 disabled:opacity-50"
              data-testid="machine-parts-picker-confirm"
            >
              {busy ? 'Saving…' : 'Add'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function MachineRowPartsUsed({ row, caseId, onChange }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [items, setItems] = useState([]);

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/svc/engineer/jobs/${caseId}`, auth());
      const allocated = r.data?.allocated_parts || [];
      setItems(allocated.filter(p => p.machine_id === row.id));
    } catch { setItems([]); }
  }, [caseId, row.id]);
  useEffect(() => { load(); }, [load]);

  const add = async (part, qty) => {
    setBusy(true);
    const idem = newIdemKey();
    try {
      const res = await outboxPost(`${API}/svc/engineer/jobs/${caseId}/parts/use`, {
        part_sku: part.sku,
        qty,
        notes: '',
        machine_id: row.id,
        machine_name: row.asset_name || null,
      }, {
        headers: { ...auth().headers, 'Idempotency-Key': idem },
        kind: 'parts_use',
        label: `Part ${part.sku} ×${qty}`,
      });
      if (res?.queued) {
        // Offline — show an optimistic "pending sync" chip; the real
        // row will replace it once the outbox drains and load() runs.
        setItems((prev) => [...prev, {
          id: `pending-${idem}`, part_sku: part.sku, qty, machine_id: row.id, _pending: true,
        }]);
        notify.success('Saved offline — will sync when back online');
      } else {
        notify.success(`${part.sku} × ${qty} added`);
        await load();
      }
      setOpen(false);
      onChange?.();
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Could not add part');
    } finally { setBusy(false); }
  };

  return (
    <div data-testid={`machine-parts-used-${row.id}`}>
      <div className="flex items-center justify-between mb-1.5">
        <label className="text-[10px] font-bold uppercase tracking-wide text-slate-500">
          Parts used {items.length > 0 ? `· ${items.length}` : ''}
        </label>
        {!open && (
          <button
            type="button"
            onClick={() => setOpen(true)}
            className="inline-flex items-center gap-1 text-[10px] font-extrabold uppercase tracking-wider px-2 py-0.5 rounded-full bg-cyan-50 text-cyan-700 border border-cyan-200 hover:bg-cyan-100"
            data-testid={`machine-parts-used-add-${row.id}`}
          >
            <Plus size={10} /> Tag part
          </button>
        )}
      </div>
      {items.length === 0 && !open && (
        <p className="text-[11px] text-slate-400 italic">No parts tagged to this machine yet.</p>
      )}
      {items.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {items.map((p) => {
            const tone = p._pending
              ? 'bg-slate-50 text-slate-500 border-slate-200'
              : p.covered
                ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                : p.chargeable
                  ? 'bg-amber-50 text-amber-800 border-amber-200'
                  : 'bg-emerald-50 text-emerald-800 border-emerald-200';
            return (
              <span
                key={p.id}
                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[10px] font-bold ${tone}`}
                data-testid={`machine-parts-used-chip-${p.id}`}
                title={p.cover_reason || ''}
              >
                {p._pending ? <Clock size={10} className="animate-pulse" /> : <Check size={10} />}
                <span className="font-mono">{p.part_sku}</span>
                <span>× {p.qty}</span>
                {!p._pending && p.covered && (
                  <span className="inline-flex items-center gap-0.5 pl-1 border-l border-emerald-300" data-testid={`machine-parts-cover-${p.id}`}>
                    <ShieldCheck size={10} /> Covered
                  </span>
                )}
                {!p._pending && p.chargeable && (
                  <span className="pl-1 border-l border-amber-300" data-testid={`machine-parts-charge-${p.id}`}>
                    Chargeable
                  </span>
                )}
                {p._pending && <span className="pl-1 border-l border-slate-300">Pending</span>}
              </span>
            );
          })}
        </div>
      )}
      {open && (
        <div className="mt-2">
          <MachineRowPartsPickerInline
            onPick={add}
            onCancel={() => setOpen(false)}
            busy={busy}
          />
        </div>
      )}
    </div>
  );
}

function MachineRowPartsForReturn({ row, caseId, onChange }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [items, setItems] = useState([]);

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/svc/engineer/parts-requests`, {
        ...auth(), params: { case_id: caseId },
      });
      const all = r.data?.items || [];
      setItems(all.filter(p => p.machine_id === row.id));
    } catch { setItems([]); }
  }, [caseId, row.id]);
  useEffect(() => { load(); }, [load]);

  const add = async (part, qty) => {
    setBusy(true);
    try {
      await axios.post(`${API}/svc/engineer/parts-requests`, {
        case_id: caseId,
        part_sku: part.sku,
        part_name: part.name || part.sku,
        qty,
        urgency: 'next_visit',
        notes: 'Required for return visit',
        machine_id: row.id,
        machine_name: row.asset_name || null,
      }, auth());
      notify.success('Added to parts request');
      setOpen(false);
      await load();
      onChange?.();
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Could not request part');
    } finally { setBusy(false); }
  };

  const cancel = async (id) => {
    if (!window.confirm('Cancel this parts request?')) return;
    try {
      await axios.delete(`${API}/svc/engineer/parts-requests/${id}`, auth());
      await load();
      notify.success('Request cancelled');
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Could not cancel');
    }
  };

  return (
    <div data-testid={`machine-parts-return-${row.id}`}>
      <div className="flex items-center justify-between mb-1.5">
        <label className="text-[10px] font-bold uppercase tracking-wide text-slate-500">
          Parts for return visit {items.length > 0 ? `· ${items.length}` : ''}
        </label>
        {!open && (
          <button
            type="button"
            onClick={() => setOpen(true)}
            className="inline-flex items-center gap-1 text-[10px] font-extrabold uppercase tracking-wider px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200 hover:bg-amber-100"
            data-testid={`machine-parts-return-add-${row.id}`}
          >
            <Plus size={10} /> Tag part to order
          </button>
        )}
      </div>
      {items.length === 0 && !open && (
        <p className="text-[11px] text-slate-400 italic">No return-visit parts tagged.</p>
      )}
      {items.length > 0 && (
        <ul className="space-y-1">
          {items.map((p) => (
            <li
              key={p.id}
              className={`flex items-center justify-between gap-2 px-2 py-1 rounded-lg border text-[11px] ${
                p.status === 'pending'
                  ? 'bg-amber-50 border-amber-200 text-amber-900'
                  : p.status === 'approved'
                    ? 'bg-emerald-50 border-emerald-200 text-emerald-900'
                    : 'bg-slate-50 border-slate-200 text-slate-700'
              }`}
              data-testid={`machine-parts-return-row-${p.id}`}
            >
              <div className="min-w-0 flex-1">
                <p className="text-xs font-bold truncate">
                  <span className="font-mono">{p.part_sku}</span> × {p.qty}
                </p>
                <p className="text-[10px] uppercase tracking-wide opacity-75">{p.status}</p>
              </div>
              {p.status === 'pending' && (
                <button
                  type="button"
                  onClick={() => cancel(p.id)}
                  className="text-rose-600 hover:text-rose-700 p-1"
                  aria-label="Cancel request"
                  data-testid={`machine-parts-return-cancel-${p.id}`}
                >
                  <X size={11} />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {open && (
        <div className="mt-2">
          <MachineRowPartsPickerInline
            onPick={add}
            onCancel={() => setOpen(false)}
            busy={busy}
          />
        </div>
      )}
    </div>
  );
}


// Iter 220eb — Isolated, debounced text field for per-machine notes.
// Fixes the "cursor jumps on spacebar" bug: previously every keystroke
// fired an async PATCH that replaced the whole row object on response,
// yanking the caret to the end / dropping characters. This component
// owns its value while the engineer types and only commits (debounced +
// on blur) to the parent, ignoring incoming prop updates while focused.
function MachineTextField({
  value, onCommit, presetChips = false, label, placeholder,
  rows = 3, testId,
}) {
  const [local, setLocal] = useState(value || '');
  const focusedRef = useRef(false);
  const timerRef = useRef(null);
  const ref = useRef(null);

  useEffect(() => {
    if (!focusedRef.current) setLocal(value || '');
  }, [value]);

  useEffect(() => () => clearTimeout(timerRef.current), []);

  const schedule = (v) => {
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => onCommit(v), 600);
  };
  const commitNow = (v) => {
    clearTimeout(timerRef.current);
    onCommit(v);
  };
  const handleChange = (e) => {
    const v = e.target.value;
    setLocal(v);
    schedule(v);
  };
  const insert = (text) => {
    const next = (local.trim() ? `${local}\n` : '') + text;
    setLocal(next);
    commitNow(next);
    setTimeout(() => ref.current?.focus(), 50);
  };

  return (
    <div>
      {label && (
        <label className="text-[10px] font-bold uppercase tracking-wide text-slate-500">
          {label}
        </label>
      )}
      <textarea
        ref={ref}
        value={local}
        onChange={handleChange}
        onFocus={() => { focusedRef.current = true; }}
        onBlur={() => { focusedRef.current = false; commitNow(local); }}
        rows={rows}
        className="w-full mt-1 text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white"
        placeholder={placeholder}
        maxLength={4000}
        data-testid={testId}
      />
      {presetChips && (
        <NotePresetChips onInsert={insert} currentText={local} />
      )}
    </div>
  );
}

function MachineRow({
  row, index, caseId, expanded, onExpand, onPatch, onDelete, onCopyDown,
  onAttachPhoto, onRemovePhoto, onProposeRemoval,
  showCopyDown, assetOptions: _assetOptions,
  assetSearch: _assetSearch, setAssetSearch: _setAssetSearch,
  refreshRows,
}) {
  const photoInputRef = useRef(null);

  // Iter 220ea·10 — Row header redesign. Name no longer truncates;
  // serial + type sit on a dedicated meta line. Serviced / Cleaned
  // pills moved to their own action row so the header can use the
  // full row width and read cleanly on a 412 px phone.
  const labelChip = (
    <div className="flex items-start gap-2.5 min-w-0 flex-1">
      <span className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-cyan-100 text-cyan-700 text-xs font-extrabold flex-shrink-0 mt-0.5">
        {index + 1}
      </span>
      <div className="min-w-0 flex-1">
        <p
          className="text-sm font-extrabold text-slate-900 leading-snug break-words"
          data-testid={`machine-row-name-${row.id}`}
        >
          {row.asset_name || 'Unnamed machine'}
        </p>
        {(row.asset_serial || row.asset_type) && (
          <p
            className="text-[11px] text-slate-500 leading-snug mt-0.5 break-words"
            data-testid={`machine-row-meta-${row.id}`}
          >
            {row.asset_type && (
              <span className="font-semibold uppercase tracking-wide text-slate-400">
                {row.asset_type}
              </span>
            )}
            {row.asset_type && row.asset_serial && <span className="mx-1.5">·</span>}
            {row.asset_serial && (
              <span className="font-mono">SN {row.asset_serial}</span>
            )}
          </p>
        )}
      </div>
    </div>
  );

  return (
    <div className="p-3 space-y-2" data-testid={`machine-row-${row.id}`}>
      <div className="flex items-start gap-2">
        {labelChip}
        <button
          type="button"
          onClick={onExpand}
          className="p-1.5 rounded-lg hover:bg-slate-100 mt-0.5"
          aria-label={expanded ? 'Collapse' : 'Expand'}
          data-testid={`machine-expand-${row.id}`}
        >
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>
      </div>
      {/* Action row — Serviced / Cleaned status pills. Sits on
          its own line so the header can show the full machine
          name without competing for horizontal space. */}
      <div className="flex items-center gap-2 pl-9">
        <button
          type="button"
          onClick={() => onPatch({ serviced: !row.serviced })}
          className={`inline-flex items-center gap-1 text-[10px] font-extrabold uppercase tracking-wider px-2.5 py-1 rounded-full transition-colors ${row.serviced ? 'bg-emerald-100 text-emerald-700 border border-emerald-200' : 'bg-slate-100 text-slate-500 border border-slate-200'}`}
          data-testid={`machine-serviced-${row.id}`}
        >
          {row.serviced && <Check size={10} />} Serviced
        </button>
        <button
          type="button"
          onClick={() => onPatch({ cleaned: !row.cleaned })}
          className={`inline-flex items-center gap-1 text-[10px] font-extrabold uppercase tracking-wider px-2.5 py-1 rounded-full transition-colors ${row.cleaned ? 'bg-sky-100 text-sky-700 border border-sky-200' : 'bg-slate-100 text-slate-500 border border-slate-200'}`}
          data-testid={`machine-cleaned-${row.id}`}
        >
          {row.cleaned && <Check size={10} />} Cleaned
        </button>
      </div>

      {expanded && (
        <div className="mt-3 space-y-3 pl-8">
          {/* Iter 220ea·12 — Machine name picker removed. The
              asset is locked from "From site" / "New asset", so
              the engineer shouldn't be able to overwrite it inline. */}

          <MachineTextField
            label="Work actioned"
            value={row.notes || ''}
            onCommit={(v) => onPatch({ notes: v })}
            presetChips
            rows={3}
            placeholder="e.g. Replaced drive belt, calibrated speed sensor, lubricated deck."
            testId={`machine-notes-${row.id}`}
          />

          {/* Iter 220ea·12 — Parts used on this visit. Surfaces
              the existing parts-tagging flow inline on the row so
              the engineer can link parts to *this specific machine*
              without leaving the Equipment tab. */}
          <MachineRowPartsUsed row={row} caseId={caseId} onChange={refreshRows} />

          <MachineTextField
            label="Further work required"
            value={row.further_work || ''}
            onCommit={(v) => onPatch({ further_work: v })}
            rows={2}
            placeholder="e.g. Console PCB needs replacing on return visit."
            testId={`machine-further-work-${row.id}`}
          />

          {/* Iter 220ea·12 — Parts to order for the return visit.
              Wraps the existing parts-request endpoint with a
              row-scoped picker so the parts the engineer flags
              here are tagged to this machine for ops to action. */}
          <MachineRowPartsForReturn row={row} caseId={caseId} onChange={refreshRows} />

          <MachineRowCustomFields row={row} onPatch={onPatch} />

          <div data-testid={`machine-photos-${row.id}`}>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-[10px] font-bold uppercase tracking-wide text-slate-500">
                Photos {(row.photos || []).length > 0 ? `· ${(row.photos || []).length}` : ''}
              </label>
              <input
                ref={photoInputRef}
                type="file"
                accept="image/*"
                capture="environment"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  e.target.value = '';
                  if (f) onAttachPhoto(f);
                }}
                data-testid={`machine-photo-input-${row.id}`}
              />
              <button
                type="button"
                onClick={() => photoInputRef.current?.click()}
                className="inline-flex items-center gap-1 text-[10px] font-bold text-cyan-700 px-2 py-1 rounded-full border border-cyan-200 bg-cyan-50 hover:bg-cyan-100"
                data-testid={`machine-photo-add-${row.id}`}
              >
                <Camera size={10} /> Add photo
              </button>
            </div>
            {(row.photos || []).length > 0 ? (
              <div className="grid grid-cols-3 gap-1.5" data-testid={`machine-photo-grid-${row.id}`}>
                {(row.photos || []).map((p) => (
                  <div
                    key={p.id}
                    className="relative aspect-square rounded-lg overflow-hidden bg-slate-100 border border-slate-200 group"
                    data-testid={`machine-photo-${p.id}`}
                  >
                    <img
                      src={p.file_url}
                      alt={p.caption || 'machine'}
                      className="w-full h-full object-cover"
                      loading="lazy"
                    />
                    <button
                      type="button"
                      onClick={() => onRemovePhoto(p.id)}
                      className="absolute top-1 right-1 p-0.5 rounded-full bg-black/60 text-white opacity-0 group-hover:opacity-100 transition-opacity"
                      aria-label="Remove photo"
                      data-testid={`machine-photo-remove-${p.id}`}
                    >
                      <X size={10} />
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-[10px] text-slate-400 italic">
                No photos attached. Tap "Add photo" to snap one — it'll print on the customer report.
              </p>
            )}
          </div>

          <div className="flex items-center justify-between pt-1">
            <div className="flex items-center gap-2">
              {showCopyDown && (
                <>
                  <button
                    type="button"
                    onClick={() => onCopyDown(['serviced', 'cleaned', 'notes'])}
                    className="inline-flex items-center gap-1 text-[10px] font-bold text-cyan-700 px-2 py-1 rounded-full border border-cyan-200 bg-cyan-50 hover:bg-cyan-100"
                    data-testid={`machine-copy-down-${row.id}`}
                    title="Apply Serviced/Cleaned/Notes to every row below"
                  >
                    <Copy size={10} /> Apply to rows below
                  </button>
                  <button
                    type="button"
                    onClick={() => onCopyDown(['notes'])}
                    className="inline-flex items-center gap-1 text-[10px] font-bold text-slate-700 px-2 py-1 rounded-full border border-slate-200 bg-white hover:bg-slate-50"
                    data-testid={`machine-copy-notes-down-${row.id}`}
                    title="Apply just this note to every row below"
                  >
                    <Sparkles size={10} /> Notes only
                  </button>
                </>
              )}
            </div>
            <button
              type="button"
              onClick={onProposeRemoval}
              className="inline-flex items-center gap-1 text-[10px] font-bold text-amber-700 px-2 py-1 rounded-full hover:bg-amber-50"
              data-testid={`machine-propose-removal-${row.id}`}
              title="Propose removing this asset from the site list (office approves)"
            >
              <PackagePlus size={10} className="rotate-45" /> Propose removal
            </button>
            <button
              type="button"
              onClick={onDelete}
              className="inline-flex items-center gap-1 text-[10px] font-bold text-rose-600 px-2 py-1 rounded-full hover:bg-rose-50"
              data-testid={`machine-delete-${row.id}`}
            >
              <Trash2 size={10} /> Remove from visit
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
