import { useState, useEffect, useRef, useMemo } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import axios from 'axios';
import { notify } from '@/components/notifications';
import EmptyState from '@/components/shared/EmptyState';
import { useUploadQueue } from '@/components/shared/UploadQueue';
import {
  Upload, FileText, Trash2, Loader2, CheckCircle,
  Image as ImageIcon, RefreshCw, Search, X, ChevronDown, ChevronUp,
  AlertTriangle, CheckSquare, Square,
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL + '/api';

/**
 * Render any JSON value safely as a React child.
 *
 * Iter 216h11 — the dropdown-crash bug was caused by `<span>{val}</span>` when
 * `val` came back as a nested object (e.g. `{value: '180kg', unit: 'kg'}`) from
 * the AI extractor — React throws "Objects are not valid as a React child" and
 * the entire route white-screens. This helper coerces objects/arrays into a
 * compact human-readable string so the panel never crashes on weird data.
 */
const safeRenderValue = (val) => {
  if (val == null) return '';
  if (typeof val === 'string' || typeof val === 'number' || typeof val === 'boolean') return String(val);
  if (Array.isArray(val)) return val.map(safeRenderValue).join(', ');
  if (typeof val === 'object') {
    // Common shapes: {value, unit}, {min, max}, {imperial, metric}
    if ('value' in val) return `${safeRenderValue(val.value)}${val.unit ? ` ${val.unit}` : ''}`;
    if ('min' in val && 'max' in val) return `${safeRenderValue(val.min)}–${safeRenderValue(val.max)}${val.unit ? ` ${val.unit}` : ''}`;
    return Object.entries(val).map(([k, v]) => `${k}: ${safeRenderValue(v)}`).join('; ');
  }
  return '';
};

/**
 * Image with graceful fallback. The /spec-sheets/image endpoint is public —
 * no auth header needed — so a plain <img> works, but if the underlying
 * storage object is missing we show a friendly placeholder instead of a
 * broken-image icon.
 */
const SpecImage = ({ specId, alt }) => {
  const [errored, setErrored] = useState(false);
  if (errored) {
    return (
      <div className="w-full h-full flex flex-col items-center justify-center text-zinc-400 gap-0.5">
        <ImageIcon size={16} />
        <span className="text-[8px] uppercase tracking-wider">No image</span>
      </div>
    );
  }
  return (
    <img
      src={`${API}/spec-sheets/image/${specId}`}
      alt={alt || ''}
      className="w-full h-full object-contain"
      onError={() => setErrored(true)}
    />
  );
};

const AdminSpecSheets = ({ headers }) => {
  const [specSheets, setSpecSheets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dragOver, setDragOver] = useState(false);
  const [expandedSpec, setExpandedSpec] = useState(null);
  const [rematching, setRematching] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);
  const fileRef = useRef(null);
  const { enqueue } = useUploadQueue();

  const fetchSpecs = async () => {
    try {
      const res = await axios.get(`${API}/spec-sheets/list`, { headers });
      setSpecSheets(res.data.spec_sheets || []);
    } catch {
      // silent — empty grid is the right fallback
    }
    setLoading(false);
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — effect either runs once on mount or re-fires on the listed trigger deps; omitted refs are stable identities or fetcher closures that read live state at call time, so including them would re-fire without changing semantics.
  useEffect(() => { fetchSpecs(); }, []);

  const processFiles = (fileList) => {
    const pdfFiles = Array.from(fileList || []).filter(f => f.name.toLowerCase().endsWith('.pdf'));
    if (pdfFiles.length === 0) { notify.error('No PDF files found'); return; }
    // Iter 216h34 — hand off to the global UploadQueue so each file
    // gets a visible row in the bottom-right drawer with per-file
    // progress + retry. The previous "Processing… N remaining" pattern
    // hid which specific file was stuck or had failed.
    let completed = 0;
    enqueue(pdfFiles, async (file, onProgress) => {
      const formData = new FormData();
      formData.append('file', file);
      await axios.post(`${API}/spec-sheets/upload`, formData, {
        headers,
        // Iter 216h69 — bump per-file timeout 120 s → 300 s. AI
        // extraction (Claude / Gemini) on a 30 MB PDF can take
        // 60-90 s and the UploadQueue now caps concurrency at 3
        // (so the backend never sees more than 3 simultaneous
        // extractions). 5 min gives generous headroom even on a
        // saturated AI provider.
        timeout: 300000,
        onUploadProgress: (e) => {
          if (e.total) onProgress(Math.round((e.loaded / e.total) * 100));
        },
      });
    }, {
      source: 'spec-sheets',
      onDone: () => {
        completed += 1;
        // Refresh once we suspect the last upload landed. We refresh on
        // every onDone — cheap call, single-table read.
        fetchSpecs();
        if (completed === pdfFiles.length) {
          notify.success(`${pdfFiles.length} spec sheet${pdfFiles.length > 1 ? 's' : ''} uploaded and matched`);
        }
      },
    });
  };

  const handleFileInput = (e) => processFiles(e.target.files);
  // Iter 216h33 — file dropzones must guard ALL three of dragenter +
  // dragover + drop. Some browsers (Safari especially) fire `dragenter`
  // before any `dragover`, and if `dragenter` doesn't `preventDefault`
  // the browser locks in the "no drop allowed" cursor and the eventual
  // `drop` will fall back to the document default (opening the file).
  const handleDragEnter = (e) => { e.preventDefault(); e.stopPropagation(); setDragOver(true); };
  const handleDragOver = (e) => { e.preventDefault(); e.stopPropagation(); setDragOver(true); };
  const handleDragLeave = (e) => { e.preventDefault(); e.stopPropagation(); setDragOver(false); };
  const handleDrop = (e) => {
    e.preventDefault(); e.stopPropagation(); setDragOver(false);
    processFiles(e.dataTransfer?.files);
  };

  const handleDelete = async (specId, modelName) => {
    if (!window.confirm(`Delete spec sheet for "${modelName}"? This will remove it from all matched equipment.`)) return;
    try {
      await axios.delete(`${API}/spec-sheets/${specId}`, { headers });
      notify.success('Spec sheet deleted');
      fetchSpecs();
    } catch {
      notify.error('Delete failed');
    }
  };

  const handleRematch = async (specId) => {
    setRematching(specId);
    try {
      const res = await axios.post(`${API}/spec-sheets/${specId}/rematch`, {}, { headers });
      notify.success(`Matched to ${res.data.matched_count} equipment items`);
      fetchSpecs();
    } catch {
      notify.error('Rematch failed');
    }
    setRematching(null);
  };

  const filtered = useMemo(() => specSheets.filter(s => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (s.equipment_model || '').toLowerCase().includes(q) ||
           (s.equipment_type || '').toLowerCase().includes(q) ||
           (s.manufacturer || '').toLowerCase().includes(q);
  }), [specSheets, searchQuery]);

  // ─── Bulk selection (iter 216h11) ─────────────────────────────────────
  const toggleSelect = (id) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };
  const allFilteredSelected = filtered.length > 0 && filtered.every(s => selectedIds.has(s.id));
  const toggleSelectAll = () => {
    setSelectedIds(prev => {
      // If everything visible is already selected → clear the visible set.
      // Otherwise → add every visible id to the selection.
      const filteredIds = filtered.map(s => s.id);
      const everyVisibleSelected = filteredIds.every(id => prev.has(id));
      const next = new Set(prev);
      if (everyVisibleSelected) {
        filteredIds.forEach(id => next.delete(id));
      } else {
        filteredIds.forEach(id => next.add(id));
      }
      return next;
    });
  };
  const clearSelection = () => setSelectedIds(new Set());

  const bulkDelete = async () => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;
    const sure = window.confirm(
      `Delete ${ids.length} spec sheet${ids.length === 1 ? '' : 's'}?\n\n`
      + `This removes the PDF + hero image from storage and unlinks every equipment item that was matched to them. Cannot be undone.`
    );
    if (!sure) return;
    setBulkBusy(true);
    let okCount = 0;
    let failCount = 0;
    for (const id of ids) {
      try {
        await axios.delete(`${API}/spec-sheets/${id}`, { headers });
        okCount++;
      } catch {
        failCount++;
      }
    }
    setBulkBusy(false);
    clearSelection();
    if (okCount > 0) notify.success(`${okCount} spec sheet${okCount === 1 ? '' : 's'} deleted${failCount > 0 ? ` · ${failCount} failed` : ''}`);
    if (okCount === 0 && failCount > 0) notify.error(`Failed to delete ${failCount} spec sheet${failCount === 1 ? '' : 's'}`);
    fetchSpecs();
  };

  const levelColor = (l) => ({
    'Premium': 'bg-amber-50 text-amber-700 border-amber-200',
    'Club Line': 'bg-indigo-50 text-indigo-700 border-indigo-200',
    'Classic': 'bg-cyan-50 text-cyan-700 border-cyan-200',
    'Dual': 'bg-violet-50 text-violet-700 border-violet-200',
  }[l] || 'bg-zinc-100 text-zinc-600 border-zinc-200');

  const typeColor = (t) => ({
    'Treadmill': 'bg-blue-50 text-blue-700 border-blue-200',
    'Cycle': 'bg-green-50 text-green-700 border-green-200',
    'Cross-Trainer': 'bg-purple-50 text-purple-700 border-purple-200',
    'Rower': 'bg-amber-50 text-amber-700 border-amber-200',
    'Strength': 'bg-red-50 text-red-700 border-red-200',
    'Functional': 'bg-teal-50 text-teal-700 border-teal-200',
  }[t] || 'bg-zinc-100 text-zinc-600 border-zinc-200');

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="animate-spin text-zinc-400" size={24} /></div>;

  return (
    <div className="space-y-6" data-testid="admin-spec-sheets">
      {/* Upload Zone */}
      <Card
        className={`p-8 border-2 border-dashed transition-colors text-center cursor-pointer ${dragOver ? 'border-[var(--color-brand-blue-dark)] bg-[var(--color-brand-blue-dark)]/5' : 'border-zinc-200 hover:border-[var(--color-brand-blue-dark)]/30'}`}
        onClick={() => fileRef.current?.click()}
        onDragEnter={handleDragEnter}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        data-testid="spec-sheet-dropzone"
      >
        <input type="file" accept=".pdf" multiple onChange={handleFileInput} ref={fileRef} className="hidden" data-testid="spec-sheet-file-input" />
        <div className="flex flex-col items-center gap-3">
          <div className="w-16 h-16 rounded-full bg-[var(--color-brand-blue-dark)]/10 flex items-center justify-center">
            <Upload size={24} className="text-[var(--color-brand-blue-dark)]" />
          </div>
          <p className="text-sm text-zinc-600 font-medium">
            {specSheets.length > 0 ? 'Upload more spec sheets' : 'Upload Pulse Fitness spec sheets'}
          </p>
          <p className="text-xs text-zinc-400">Drop PDFs here or click to browse. AI will extract model info, specs, and product images. Track progress in the upload drawer.</p>
        </div>
      </Card>

      {/* Search + Count */}
      {specSheets.length > 0 && (
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3 flex-1 min-w-[240px]">
            <div className="relative flex-1 max-w-sm">
              <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400" />
              <input
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                placeholder="Search spec sheets..."
                className="w-full pl-9 pr-8 py-2 text-sm border border-zinc-200 rounded-lg focus:ring-1 focus:ring-[var(--color-brand-blue-dark)] focus:outline-none"
                data-testid="spec-search"
              />
              {searchQuery && (
                <button onClick={() => setSearchQuery('')} className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-600">
                  <X size={14} />
                </button>
              )}
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={toggleSelectAll}
              disabled={filtered.length === 0}
              className="text-xs h-9"
              data-testid="spec-select-all"
            >
              {allFilteredSelected ? <CheckSquare size={14} className="mr-1.5" /> : <Square size={14} className="mr-1.5" />}
              {allFilteredSelected ? 'Clear selection' : `Select all (${filtered.length})`}
            </Button>
          </div>
          <Badge className="bg-[var(--color-brand-blue-dark)]/10 text-[var(--color-brand-blue-dark)] border-[var(--color-brand-blue-dark)]/20">{specSheets.length} spec sheets</Badge>
        </div>
      )}

      {/* Bulk-action bar */}
      {selectedIds.size > 0 && (
        <div
          className="sticky top-2 z-10 flex items-center justify-between gap-3 px-3 py-2 rounded-lg bg-zinc-900 text-white shadow-lg"
          data-testid="spec-bulk-bar"
        >
          <p className="text-xs font-medium">
            <strong>{selectedIds.size}</strong> spec sheet{selectedIds.size === 1 ? '' : 's'} selected
          </p>
          <div className="flex items-center gap-2">
            <Button
              size="sm" variant="ghost"
              onClick={clearSelection}
              className="h-7 text-xs text-zinc-300 hover:text-white hover:bg-white/10"
              data-testid="spec-bulk-clear"
            >
              <X size={12} className="mr-1" /> Clear
            </Button>
            <Button
              size="sm"
              onClick={bulkDelete}
              disabled={bulkBusy}
              className="h-7 text-xs bg-red-600 hover:bg-red-700 text-white"
              data-testid="spec-bulk-delete"
            >
              {bulkBusy ? <Loader2 size={12} className="mr-1 animate-spin" /> : <Trash2 size={12} className="mr-1" />}
              Delete {selectedIds.size} selected
            </Button>
          </div>
        </div>
      )}

      {/* Spec Sheets Grid */}
      {filtered.length === 0 && specSheets.length === 0 ? (
        <EmptyState
          icon={FileText}
          title="No spec sheets uploaded yet"
          hint="Drop manufacturer PDFs above to extract key specs (model, weight, voltage, dimensions). Spec sheets attach to equipment automatically when models match — so every operator's equipment page links straight to the right PDF."
          testId="spec-sheets-empty"
        />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={FileText}
          title="No spec sheets match this filter"
          hint="Try clearing the search box or switching brand/category filters."
          testId="spec-sheets-empty-filtered"
        />
      ) : (
        <div className="space-y-3">
          {filtered.map(spec => {
            const checked = selectedIds.has(spec.id);
            const keySpecs = (spec.key_specs && typeof spec.key_specs === 'object' && !Array.isArray(spec.key_specs))
              ? spec.key_specs : {};
            return (
              <Card key={spec.id} className={`border-zinc-200 overflow-hidden transition-colors ${checked ? 'ring-2 ring-[var(--color-brand-blue-dark)] border-transparent' : ''}`} data-testid={`spec-sheet-${spec.id}`}>
                <div className="flex items-center gap-4 p-4">
                  {/* Selection checkbox */}
                  <button
                    type="button"
                    onClick={() => toggleSelect(spec.id)}
                    className={`w-5 h-5 rounded border flex items-center justify-center shrink-0 transition-colors ${checked ? 'bg-[var(--color-brand-blue-dark)] border-[var(--color-brand-blue-dark)] text-white' : 'border-zinc-300 hover:border-[var(--color-brand-blue-dark)]'}`}
                    aria-label={checked ? 'Deselect' : 'Select'}
                    data-testid={`spec-select-${spec.id}`}
                  >
                    {checked && <CheckSquare size={12} />}
                  </button>

                  {/* Hero image thumbnail — graceful fallback when storage 404s */}
                  <div className="w-16 h-16 rounded-lg bg-zinc-100 border border-zinc-200 flex items-center justify-center shrink-0 overflow-hidden">
                    {spec.hero_image_url ? (
                      <SpecImage specId={spec.id} alt={spec.equipment_model} />
                    ) : (
                      <ImageIcon size={20} className="text-zinc-400" />
                    )}
                  </div>

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <span className="text-sm font-semibold text-zinc-900 truncate">{spec.equipment_model || spec.original_filename}</span>
                      {spec.product_level && (
                        <Badge className={`text-[10px] ${levelColor(spec.product_level)}`}>{spec.product_level}</Badge>
                      )}
                      <Badge className={`text-[10px] ${typeColor(spec.equipment_type)}`}>{spec.equipment_type}</Badge>
                    </div>
                    <div className="flex items-center gap-3 text-xs text-zinc-500">
                      <span>{spec.manufacturer}</span>
                      {spec.matched_count > 0 && (
                        <span className="flex items-center gap-1 text-green-600">
                          <CheckCircle size={12} /> {spec.matched_count} matched
                        </span>
                      )}
                      {spec.matched_count === 0 && (
                        <span className="text-amber-600">No matches yet</span>
                      )}
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-2 shrink-0">
                    <Button variant="ghost" size="sm" onClick={() => handleRematch(spec.id)} disabled={rematching === spec.id}
                      className="h-8 px-2 text-zinc-500 hover:text-[var(--color-brand-blue-dark)]" data-testid={`spec-rematch-${spec.id}`}>
                      {rematching === spec.id ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => setExpandedSpec(expandedSpec === spec.id ? null : spec.id)}
                      className="h-8 px-2 text-zinc-500" data-testid={`spec-expand-${spec.id}`}>
                      {expandedSpec === spec.id ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => handleDelete(spec.id, spec.equipment_model)}
                      className="h-8 px-2 text-zinc-400 hover:text-red-500" data-testid={`spec-delete-${spec.id}`}>
                      <Trash2 size={14} />
                    </Button>
                  </div>
                </div>

                {/* Expanded Detail — wrapped in defensive value rendering so a
                    weirdly-shaped key_specs object can never crash the page. */}
                {expandedSpec === spec.id && (
                  <ExpandedDetail
                    spec={spec}
                    keySpecs={keySpecs}
                  />
                )}
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
};

/**
 * Expanded detail row — extracted to its own component with a per-instance
 * error boundary so a single corrupt spec sheet can't take down the panel.
 */
const ExpandedDetail = ({ spec, keySpecs }) => {
  const [pdfErrored, setPdfErrored] = useState(false);
  try {
    return (
      <div className="border-t border-zinc-200 p-4 bg-zinc-50">
        <div className="grid md:grid-cols-2 gap-4">
          <div>
            {spec.description && <p className="text-sm text-zinc-600 mb-3">{safeRenderValue(spec.description)}</p>}
            {Object.keys(keySpecs).length > 0 && (
              <div>
                <h4 className="text-xs font-semibold text-zinc-500 uppercase mb-2">Key Specifications</h4>
                <div className="grid grid-cols-2 gap-1">
                  {Object.entries(keySpecs).map(([key, val]) => (
                    <div key={key} className="text-xs">
                      <span className="text-zinc-400">{String(key).replace(/_/g, ' ')}:</span>{' '}
                      <span className="text-zinc-700 font-medium">{safeRenderValue(val)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            <div className="mt-3">
              <h4 className="text-xs font-semibold text-zinc-500 uppercase mb-1">Matched Equipment IDs</h4>
              {spec.matched_equipment_ids?.length > 0 ? (
                <p className="text-xs text-zinc-600">{spec.matched_equipment_ids.length} items matched</p>
              ) : (
                <p className="text-xs text-zinc-400">No equipment matched. Try rematching.</p>
              )}
            </div>
          </div>
          <div>
            {spec.pdf_url && !pdfErrored && (
              <div className="border border-zinc-200 rounded-lg overflow-hidden bg-white">
                <iframe
                  src={`${API}/spec-sheets/pdf/${spec.id}`}
                  title={spec.equipment_model || 'Spec sheet PDF'}
                  className="w-full h-64"
                  onError={() => setPdfErrored(true)}
                />
              </div>
            )}
            {pdfErrored && (
              <div className="border border-zinc-200 rounded-lg p-6 text-center bg-white">
                <AlertTriangle size={20} className="mx-auto text-amber-500 mb-2" />
                <p className="text-xs text-zinc-500">PDF preview unavailable. Try re-uploading.</p>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  } catch (err) {
    // Defensive last-resort fallback — should never fire now that
    // safeRenderValue() handles the only known crash vector, but kept
    // as belt-and-braces so future malformed payloads can't crash the route.
    return (
      <div className="border-t border-zinc-200 p-4 bg-amber-50 text-xs text-amber-800 flex items-center gap-2" data-testid={`spec-expand-error-${spec.id}`}>
        <AlertTriangle size={14} /> Couldn't render details for this spec sheet. The data may be malformed — try Rematch or delete + re-upload.
      </div>
    );
  }
};

export default AdminSpecSheets;
