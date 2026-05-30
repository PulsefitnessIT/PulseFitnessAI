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
  ChevronUp, Camera, X, PackagePlus, Package, CheckSquare, Square,
  ListChecks, Search,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import NotePresetChips from './NotePresetChips';
import MachineRowCustomFields from './MachineRowCustomFields';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const auth = () => ({
  headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
});

export default function WorkVisitMachinesCard({ caseId }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [expandedId, setExpandedId] = useState(null);
  const [assetOptions, setAssetOptions] = useState([]);
  const [assetSearch, setAssetSearch] = useState('');
  // Iter 220cj — Site equipment picker (multi-select w/ Select All)
  const [sitePickerOpen, setSitePickerOpen] = useState(false);

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

  useEffect(() => { load(); }, [load]); // eslint-disable-line

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

  const addRow = async (preset = {}) => {
    setAdding(true);
    try {
      const r = await axios.post(
        `${API}/svc/engineer/jobs/${caseId}/machines`,
        preset,
        auth(),
      );
      setRows((prev) => [...prev, r.data]);
      setExpandedId(r.data.id);
    } catch (e) {
      notify.error('Could not add machine', e?.response?.data?.detail || e?.message);
    } finally {
      setAdding(false);
    }
  };

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
      const fd = new FormData();
      fd.append('file', file);
      const u = await axios.post(`${API}/files/upload?category=service-media`, fd, {
        ...auth(),
        headers: { ...auth().headers, 'Content-Type': 'multipart/form-data' },
      });
      const fileUrl = u.data?.download_url || u.data?.storage_path;
      const r = await axios.post(`${API}/svc/engineer/photos`, {
        case_id: caseId,
        machine_row_id: rowId,
        file_url: fileUrl,
        mime_type: u.data?.content_type || 'image/jpeg',
        caption: caption || '',
      }, auth());
      // Optimistic insert into the row.
      setRows((prev) => prev.map(r2 => r2.id === rowId
        ? { ...r2, photos: [...(r2.photos || []), r.data] }
        : r2,
      ));
      notify.success('Photo attached');
    } catch (e) {
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
      <div className="p-4 border-b border-slate-100 flex items-center justify-between gap-2">
        <div>
          <p className="text-sm font-bold text-slate-900 flex items-center gap-2">
            <Wrench size={14} className="text-blue-600" />
            Machines on this visit
          </p>
          <p className="text-[11px] text-slate-500 mt-0.5">
            One row per Erg. Tick what you serviced / cleaned · add a note.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {/* Iter 220cj — Pre-load equipment from the job's site */}
          <button
            type="button"
            onClick={() => setSitePickerOpen(true)}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-blue-200 bg-blue-50 text-blue-700 text-xs font-bold hover:bg-blue-100"
            data-testid="machines-load-from-site-btn"
            title="Show all equipment for this site and pick which ones to work on"
          >
            <Package size={12} /> From site
          </button>
          <Link
            to={`/svc/engineer/equipment/new?case_id=${encodeURIComponent(caseId || '')}`}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-slate-200 text-slate-700 text-xs font-bold hover:bg-slate-50"
            data-testid="machines-new-asset-link"
            title="Create a brand-new equipment record and attach it"
          >
            <PackagePlus size={12} /> New asset
          </Link>
          <button
            type="button"
            onClick={() => addRow({})}
            disabled={adding}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-blue-600 text-white text-xs font-bold disabled:opacity-50"
            data-testid="machines-add-btn"
          >
            {adding ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />} Add machine
          </button>
        </div>
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
              expanded={expandedId === row.id}
              onExpand={() => setExpandedId(expandedId === row.id ? null : row.id)}
              onPatch={(patch) => patchRow(row.id, patch)}
              onDelete={() => deleteRow(row.id)}
              onCopyDown={(fields) => copyDown(row.id, fields)}
              onAttachPhoto={(file) => attachPhoto(row.id, file)}
              onRemovePhoto={(photoId) => removePhoto(row.id, photoId)}
              showCopyDown={idx < rows.length - 1}
              assetOptions={filteredAssets}
              assetSearch={assetSearch}
              setAssetSearch={setAssetSearch}
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
              className="w-full pl-9 pr-3 py-2 rounded-xl border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
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
                            ? 'bg-blue-50'
                            : 'hover:bg-slate-50'
                      }`}
                      data-testid={`site-equipment-item-${it.id}`}
                    >
                      <span className="w-5 h-5 flex-shrink-0">
                        {ticked
                          ? <CheckSquare size={20} className="text-blue-600" />
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
            className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-300 text-white rounded-xl py-2.5 text-sm font-bold inline-flex items-center justify-center gap-1.5"
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

function MachineAssetPicker({ row, assetOptions, onPatch }) {
  // Iter 220i — Closes on Enter / outside-click / Escape; auto-picks
  // when there's exactly one match. Search is local to this row so
  // typing in row 1 doesn't affect row 2's filter.
  const [open, setOpen] = useState(false);
  const [activeIdx, setActiveIdx] = useState(0);
  const wrapperRef = useRef(null);

  const filtered = (() => {
    const needle = (row.asset_name || '').trim().toLowerCase();
    if (needle.length < 2) return [];
    if (row.asset_id) return [];
    return assetOptions.filter(a =>
      a.label.toLowerCase().includes(needle) ||
      (a.serial || '').toLowerCase().includes(needle),
    ).slice(0, 8);
  })();

  useEffect(() => {
    setOpen(filtered.length > 0);
    setActiveIdx(0);
  }, [filtered.length, row.asset_name, row.asset_id]);

  useEffect(() => {
    const handler = (e) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const pick = (a) => {
    onPatch({
      asset_id: a.id,
      asset_name: a.label,
      asset_serial: a.serial || null,
      asset_type: a.equipment_type || null,
    });
    setOpen(false);
  };

  const onKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      if (filtered.length === 1) {
        pick(filtered[0]);
      } else if (filtered.length > 1 && open) {
        pick(filtered[activeIdx]);
      } else {
        // No matches → free text accepted, close the picker.
        setOpen(false);
      }
    } else if (e.key === 'ArrowDown' && open) {
      e.preventDefault();
      setActiveIdx((i) => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === 'ArrowUp' && open) {
      e.preventDefault();
      setActiveIdx((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  };

  return (
    <div ref={wrapperRef} className="relative">
      <input
        value={row.asset_name || ''}
        onChange={(e) => onPatch({ asset_name: e.target.value, asset_id: null })}
        onFocus={() => filtered.length && setOpen(true)}
        onKeyDown={onKeyDown}
        className="w-full mt-1 text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white"
        placeholder="e.g. BikeErg #03 (Concept 2)"
        maxLength={200}
        autoComplete="off"
        data-testid={`machine-name-input-${row.id}`}
      />
      {open && filtered.length > 0 && (
        <div
          className="mt-1 max-h-40 overflow-auto border border-slate-200 rounded-lg bg-white shadow-sm absolute left-0 right-0 z-10"
          data-testid={`machine-asset-picker-${row.id}`}
        >
          {filtered.map((a, idx) => (
            <button
              type="button"
              key={a.id}
              onMouseDown={(e) => { e.preventDefault(); pick(a); }}
              onMouseEnter={() => setActiveIdx(idx)}
              className={`w-full text-left px-3 py-1.5 text-xs flex items-center justify-between ${idx === activeIdx ? 'bg-blue-50' : 'hover:bg-slate-50'}`}
              data-testid={`machine-asset-option-${a.id}`}
            >
              <span className="truncate">{a.label}</span>
              {a.serial && <span className="font-mono text-[10px] text-slate-500 ml-2">{a.serial}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function MachineRow({
  row, index, expanded, onExpand, onPatch, onDelete, onCopyDown,
  onAttachPhoto, onRemovePhoto,
  showCopyDown, assetOptions, assetSearch, setAssetSearch,
}) {
  const notesRef = useRef(null);
  const photoInputRef = useRef(null);
  const insertNote = (text) => {
    const existing = (row.notes || '').trim();
    const next = existing ? `${existing}\n${text}` : text;
    onPatch({ notes: next });
    // Re-focus the textarea so the engineer can keep typing.
    setTimeout(() => notesRef.current?.focus(), 50);
  };

  const labelChip = (
    <div className="flex items-center gap-2 min-w-0 flex-1">
      <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-blue-100 text-blue-700 text-[11px] font-bold flex-shrink-0">
        {index + 1}
      </span>
      <p className="text-sm font-bold text-slate-900 truncate" data-testid={`machine-row-name-${row.id}`}>
        {row.asset_name || 'Unnamed machine'}
      </p>
      {row.asset_serial && (
        <span className="text-[10px] font-mono bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded">
          {row.asset_serial}
        </span>
      )}
    </div>
  );

  return (
    <div className="p-3" data-testid={`machine-row-${row.id}`}>
      <div className="flex items-center gap-2">
        {labelChip}
        <button
          type="button"
          onClick={() => onPatch({ serviced: !row.serviced })}
          className={`text-[10px] font-bold uppercase px-2 py-1 rounded-full transition-colors ${row.serviced ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'}`}
          data-testid={`machine-serviced-${row.id}`}
        >
          {row.serviced ? '✓ Serviced' : 'Serviced'}
        </button>
        <button
          type="button"
          onClick={() => onPatch({ cleaned: !row.cleaned })}
          className={`text-[10px] font-bold uppercase px-2 py-1 rounded-full transition-colors ${row.cleaned ? 'bg-sky-100 text-sky-700' : 'bg-slate-100 text-slate-500'}`}
          data-testid={`machine-cleaned-${row.id}`}
        >
          {row.cleaned ? '✓ Cleaned' : 'Cleaned'}
        </button>
        <button
          type="button"
          onClick={onExpand}
          className="p-1.5 rounded-lg hover:bg-slate-100"
          aria-label={expanded ? 'Collapse' : 'Expand'}
          data-testid={`machine-expand-${row.id}`}
        >
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>
      </div>

      {expanded && (
        <div className="mt-3 space-y-2.5 pl-8">
          <div>
            <label className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Machine</label>
            <MachineAssetPicker
              row={row}
              assetOptions={assetOptions}
              onPatch={onPatch}
            />
          </div>

          <div>
            <label className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Notes / Recommendations</label>
            <textarea
              ref={notesRef}
              value={row.notes || ''}
              onChange={(e) => onPatch({ notes: e.target.value })}
              rows={3}
              className="w-full mt-1 text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white"
              placeholder="e.g. Shock cord worn — recommend replacement. Million-Meter calibration check needed."
              maxLength={4000}
              data-testid={`machine-notes-${row.id}`}
            />
            <NotePresetChips onInsert={insertNote} currentText={row.notes || ''} />
          </div>

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
                className="inline-flex items-center gap-1 text-[10px] font-bold text-blue-700 px-2 py-1 rounded-full border border-blue-200 bg-blue-50 hover:bg-blue-100"
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
                    className="inline-flex items-center gap-1 text-[10px] font-bold text-blue-700 px-2 py-1 rounded-full border border-blue-200 bg-blue-50 hover:bg-blue-100"
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
              onClick={onDelete}
              className="inline-flex items-center gap-1 text-[10px] font-bold text-rose-600 px-2 py-1 rounded-full hover:bg-rose-50"
              data-testid={`machine-delete-${row.id}`}
            >
              <Trash2 size={10} /> Remove
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
