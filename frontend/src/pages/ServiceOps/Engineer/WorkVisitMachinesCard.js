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
import {
  Plus, Loader2, Trash2, Copy, Wrench, Sparkles, ChevronDown,
  ChevronUp, Camera, X,
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
