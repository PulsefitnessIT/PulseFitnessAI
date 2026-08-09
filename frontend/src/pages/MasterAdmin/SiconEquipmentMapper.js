import { useState, useEffect, useMemo, useCallback } from 'react';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import axios from 'axios';
import { notify } from '@/components/notifications';
import {
  Link2, Loader2, Save, Search, Building2, MapPin, RefreshCw, CheckCircle2,
  Wand2, Upload, X, AlertTriangle, Bookmark, Trash2,
} from 'lucide-react';

// Split pasted/uploaded CSV or TSV into a cell matrix (delimiter auto-detected).
function splitTable(text) {
  const lines = (text || '').split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  if (!lines.length) return [];
  const delim = lines[0].includes('\t') ? '\t' : ',';
  const splitLine = (line) => {
    const out = []; let cur = ''; let inQ = false;
    for (let i = 0; i < line.length; i += 1) {
      const c = line[i];
      if (c === '"') { inQ = !inQ; continue; }
      if (c === delim && !inQ) { out.push(cur); cur = ''; continue; }
      cur += c;
    }
    out.push(cur);
    return out.map((s) => s.trim());
  };
  return lines.map(splitLine);
}

// Signature of an export's shape, used to auto-apply a saved template.
// Header present → the lowercased header names joined; else the column count.
function sigFor(analysis, firstRowHeader) {
  if (!analysis) return '';
  if (firstRowHeader && analysis.table[0]) {
    return 'h:' + analysis.table[0].map((c) => String(c).trim().toLowerCase()).join('|');
  }
  return 'c:' + analysis.colCount;
}

// Analyze the table: detect a header row + best-guess column indices for
// serial / sicon / sage. The user can override both in the mapping UI.
function analyzeImport(text) {
  const table = splitTable(text);
  if (!table.length) return null;
  const first = table[0].map((c) => c.toLowerCase());
  const findIdx = (preds) => first.findIndex((h) => preds.some((p) => h.includes(p)));
  const serialIdx = findIdx(['serial']);
  const siconIdx = first.findIndex((h) => h.includes('sicon') || (h.includes('equip') && h.includes('id')) || h.includes('assetid') || h === 'asset id');
  const sageIdx = first.findIndex((h) => h.includes('sage') || (h.includes('item') && h.includes('id')) || h.includes('stock'));
  const autoHasHeader = serialIdx !== -1 || siconIdx !== -1 || sageIdx !== -1;
  const colCount = Math.max(...table.map((r) => r.length));
  const detected = {
    serial: serialIdx !== -1 ? serialIdx : 0,
    sicon: siconIdx !== -1 ? siconIdx : (colCount > 1 ? 1 : -1),
    sage: sageIdx !== -1 ? sageIdx : (colCount > 2 ? 2 : -1),
  };
  return { table, colCount, detected, autoHasHeader };
}

// Build normalized import rows from data rows using the chosen column map.
function buildRows(dataRows, colMap) {
  const rows = [];
  (dataRows || []).forEach((cells) => {
    const serial = colMap.serial >= 0 ? (cells[colMap.serial] || '').trim() : '';
    if (!serial) return;
    rows.push({
      serial,
      sicon_equipment_id: colMap.sicon >= 0 ? (cells[colMap.sicon] || '').trim() : '',
      sage_item_id: colMap.sage >= 0 ? (cells[colMap.sage] || '').trim() : '',
    });
  });
  return rows;
}

export default function SiconEquipmentMapper() {
  const { API } = useAuth();
  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const [orgs, setOrgs] = useState([]);
  const [orgId, setOrgId] = useState('');
  const [loadingOrgs, setLoadingOrgs] = useState(true);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [rows, setRows] = useState([]);
  const [meta, setMeta] = useState({ total: 0, mapped: 0 });
  const [edits, setEdits] = useState({}); // id -> {sicon_equipment_id, sage_item_id}
  const [q, setQ] = useState('');
  const [showMatch, setShowMatch] = useState(false);
  const [pasteText, setPasteText] = useState('');
  const [colMap, setColMap] = useState({ serial: 0, sicon: 1, sage: 2 });
  const [firstRowHeader, setFirstRowHeader] = useState(false);
  const [matching, setMatching] = useState(false);
  const [matchStats, setMatchStats] = useState(null);
  const [fuzzyMatches, setFuzzyMatches] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [appliedTpl, setAppliedTpl] = useState(null); // name auto-applied

  const loadOrgs = useCallback(async () => {
    setLoadingOrgs(true);
    try {
      const res = await axios.get(`${API}/master-admin/sicon/equipment-mapping/orgs`, { headers });
      const list = res.data?.organizations || [];
      setOrgs(list);
      if (list.length && !orgId) setOrgId(list[0].organization_id);
    } catch (err) {
      notify.error('Failed to load organisations');
    } finally {
      setLoadingOrgs(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [API]);

  const loadEquipment = useCallback(async (oid) => {
    if (!oid) return;
    setLoading(true);
    setEdits({});
    try {
      const res = await axios.get(`${API}/master-admin/sicon/equipment-mapping/${oid}`, { headers });
      setRows(res.data?.equipment || []);
      setMeta({ total: res.data?.total || 0, mapped: res.data?.mapped || 0 });
    } catch (err) {
      notify.error('Failed to load equipment');
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [API]);

  useEffect(() => { loadOrgs(); }, [loadOrgs]);
  useEffect(() => { if (orgId) loadEquipment(orgId); }, [orgId, loadEquipment]);

  const setField = (id, field, value) => {
    setEdits((prev) => {
      const row = rows.find((r) => r.id === id) || {};
      const cur = prev[id] || {
        sicon_equipment_id: row.sicon_equipment_id ?? '',
        sage_item_id: row.sage_item_id ?? '',
      };
      return { ...prev, [id]: { ...cur, [field]: value } };
    });
  };

  const valueFor = (row, field) => {
    if (edits[row.id] && field in edits[row.id]) return edits[row.id][field];
    return row[field] ?? '';
  };

  const dirtyCount = Object.keys(edits).length;

  // Re-analyze whenever the pasted text changes; reset the column map + header
  // toggle to the best-guess detection (user can override via the UI below).
  const analysis = useMemo(() => analyzeImport(pasteText), [pasteText]);
  useEffect(() => {
    if (analysis) { setColMap(analysis.detected); setFirstRowHeader(analysis.autoHasHeader); }
  }, [analysis]);
  const header = analysis && firstRowHeader ? analysis.table[0] : null;
  const dataRows = analysis ? (firstRowHeader ? analysis.table.slice(1) : analysis.table) : [];

  // Load saved column-mapping templates once.
  const loadTemplates = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/master-admin/sicon/import-templates`, { headers });
      setTemplates(res.data?.templates || []);
    } catch { /* non-fatal */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [API]);
  useEffect(() => { loadTemplates(); }, [loadTemplates]);

  const applyTemplate = useCallback((tpl, silent) => {
    if (!tpl) return;
    if (typeof tpl.first_row_header === 'boolean') setFirstRowHeader(tpl.first_row_header);
    if (tpl.col_map) setColMap({
      serial: tpl.col_map.serial ?? 0,
      sicon: tpl.col_map.sicon ?? -1,
      sage: tpl.col_map.sage ?? -1,
    });
    setAppliedTpl(tpl.name);
    if (!silent) notify.success(`Applied template "${tpl.name}"`);
  }, []);

  // Auto-apply a template whose header signature matches the pasted export.
  useEffect(() => {
    if (!analysis || !templates.length) return;
    const sigHeader = sigFor(analysis, true);
    const sigCols = sigFor(analysis, false);
    const hit = templates.find((t) => t.header_signature && (t.header_signature === sigHeader || t.header_signature === sigCols));
    if (hit) applyTemplate(hit, true);
    else setAppliedTpl(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [analysis, templates]);

  const saveTemplate = async () => {
    const name = window.prompt('Name this export format (e.g. "Sage 200 export", "Sicon asset dump"):');
    if (!name || !name.trim()) return;
    try {
      const res = await axios.post(`${API}/master-admin/sicon/import-templates`, {
        name: name.trim(),
        col_map: colMap,
        first_row_header: firstRowHeader,
        header_signature: sigFor(analysis, firstRowHeader),
      }, { headers });
      notify.success(`Saved template "${name.trim()}"`, 'It will auto-apply next time this format is pasted.');
      setAppliedTpl(name.trim());
      await loadTemplates();
    } catch (err) {
      notify.error('Could not save template', err?.response?.data?.detail || '');
    }
  };

  const deleteTemplate = async (tpl) => {
    if (!window.confirm(`Delete template "${tpl.name}"?`)) return;
    try {
      await axios.delete(`${API}/master-admin/sicon/import-templates/${tpl.id}`, { headers });
      if (appliedTpl === tpl.name) setAppliedTpl(null);
      await loadTemplates();
    } catch { notify.error('Could not delete template'); }
  };

  const runAutoMatch = async () => {
    const importRows = buildRows(dataRows, colMap);
    if (!importRows.length) {
      notify.error('Nothing to match', 'Check the Serial column is mapped and has values.');
      return;
    }
    setMatching(true);
    try {
      const res = await axios.post(
        `${API}/master-admin/sicon/equipment-mapping/${orgId}/auto-match`,
        { source: 'import', rows: importRows },
        { headers },
      );
      const { matched = [], fuzzy = [], stats = {} } = res.data || {};
      // Pre-fill only EXACT matches where a suggestion differs from current.
      const next = {};
      matched.forEach((m) => {
        const patch = {};
        if (m.suggested_sicon_equipment_id != null && m.suggested_sicon_equipment_id !== m.current_sicon_equipment_id) {
          patch.sicon_equipment_id = String(m.suggested_sicon_equipment_id);
        }
        if (m.suggested_sage_item_id != null && m.suggested_sage_item_id !== m.current_sage_item_id) {
          patch.sage_item_id = String(m.suggested_sage_item_id);
        }
        if (Object.keys(patch).length) {
          const row = rows.find((r) => r.id === m.equipment_id) || {};
          next[m.equipment_id] = {
            sicon_equipment_id: patch.sicon_equipment_id ?? (row.sicon_equipment_id ?? ''),
            sage_item_id: patch.sage_item_id ?? (row.sage_item_id ?? ''),
          };
        }
      });
      setEdits((prev) => ({ ...prev, ...next }));
      setMatchStats(stats);
      setFuzzyMatches(fuzzy); // near-misses require explicit confirmation
      const prefilled = Object.keys(next).length;
      notify.success(
        `Matched ${stats.matched || 0} of ${stats.import_rows || 0} import rows — ${prefilled} pre-filled`,
        `${stats.fuzzy || 0} near-miss(es) to review · ${stats.unmatched_import || 0} with no match. Review, then Save.`,
      );
      setShowMatch(false);
    } catch (err) {
      notify.error('Auto-match failed', err?.response?.data?.detail || 'Please try again.');
    } finally {
      setMatching(false);
    }
  };

  const onFile = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setPasteText(String(reader.result || ''));
    reader.readAsText(file);
  };

  const applyFuzzy = (fm) => {
    const row = rows.find((r) => r.id === fm.equipment_id) || {};
    setEdits((prev) => ({
      ...prev,
      [fm.equipment_id]: {
        sicon_equipment_id: fm.suggested_sicon_equipment_id != null ? String(fm.suggested_sicon_equipment_id) : (row.sicon_equipment_id ?? ''),
        sage_item_id: fm.suggested_sage_item_id != null ? String(fm.suggested_sage_item_id) : (row.sage_item_id ?? ''),
      },
    }));
    setFuzzyMatches((prev) => prev.filter((x) => x.equipment_id !== fm.equipment_id));
  };
  const applyAllFuzzy = () => {
    fuzzyMatches.forEach(applyFuzzy);
    setFuzzyMatches([]);
  };
  const dismissFuzzy = (id) => setFuzzyMatches((prev) => prev.filter((x) => x.equipment_id !== id));

  const handleSave = async () => {
    if (!dirtyCount) return;
    const mappings = Object.entries(edits).map(([equipment_id, v]) => ({
      equipment_id,
      sicon_equipment_id: v.sicon_equipment_id === '' ? null : v.sicon_equipment_id,
      sage_item_id: v.sage_item_id === '' ? null : v.sage_item_id,
    }));
    setSaving(true);
    try {
      const res = await axios.put(`${API}/master-admin/sicon/equipment-mapping/${orgId}`, { mappings }, { headers });
      notify.success(`Saved ${res.data?.updated || 0} machine(s)`, `${res.data?.mapped || 0}/${res.data?.total || 0} now mapped.`);
      await loadEquipment(orgId);
      await loadOrgs();
    } catch (err) {
      notify.error('Save failed', err?.response?.data?.detail || 'Please try again.');
    } finally {
      setSaving(false);
    }
  };

  const filtered = rows.filter((r) => {
    if (!q.trim()) return true;
    const s = q.toLowerCase();
    return (r.name || '').toLowerCase().includes(s)
      || (r.serial_number || '').toLowerCase().includes(s)
      || (r.location || '').toLowerCase().includes(s);
  });

  const coveragePct = meta.total ? Math.round((meta.mapped / meta.total) * 100) : 0;

  return (
    <div className="space-y-5" data-testid="sicon-equipment-mapper">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h3 className="text-lg font-semibold text-zinc-900 flex items-center gap-2">
            <Link2 size={18} className="text-violet-600" />
            Equipment ID Mapper
          </h3>
          <p className="text-sm text-zinc-500 mt-0.5">
            Map each machine to its Sicon asset ID so faults cross-link to the right asset from day one.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" onClick={() => setShowMatch((v) => !v)} disabled={!orgId}
            className="border-violet-300 text-violet-700 hover:bg-violet-50" data-testid="sicon-mapper-automatch-toggle">
            <Wand2 size={12} className="mr-1" /> Auto-match by serial
          </Button>
          <Button size="sm" variant="outline" onClick={() => loadEquipment(orgId)} disabled={loading || !orgId} data-testid="sicon-mapper-refresh">
            <RefreshCw size={12} className="mr-1" /> Reload
          </Button>
          <Button size="sm" onClick={handleSave} disabled={saving || dirtyCount === 0}
            className="bg-violet-600 hover:bg-violet-700 text-white" data-testid="sicon-mapper-save">
            {saving ? <Loader2 size={12} className="animate-spin mr-1" /> : <Save size={12} className="mr-1" />}
            Save{dirtyCount ? ` (${dirtyCount})` : ''}
          </Button>
        </div>
      </div>

      {/* Auto-match panel */}
      {showMatch && (
        <Card className="p-4 border-violet-200 bg-violet-50/40" data-testid="sicon-mapper-automatch-panel">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-zinc-800 flex items-center gap-1.5">
                <Wand2 size={14} className="text-violet-600" /> Auto-match from a Sage / Sicon export
              </p>
              <p className="text-xs text-zinc-500 mt-0.5">
                Paste or upload CSV/Excel rows. I match by <b>serial number</b> and pre-fill the Sicon Asset IDs for review — nothing saves until you hit Save.
              </p>
            </div>
            <button type="button" onClick={() => setShowMatch(false)} className="text-zinc-400 hover:text-zinc-700" data-testid="sicon-mapper-automatch-close"><X size={16} /></button>
          </div>
          <textarea
            value={pasteText}
            onChange={(e) => setPasteText(e.target.value)}
            placeholder={'Serial, SiconAssetID, SageItemID\nSN-10231, 4021, 8801\nSN-10232, 4022'}
            rows={5}
            className="mt-3 w-full px-3 py-2 rounded-md border border-zinc-300 bg-white text-sm font-mono focus:outline-none focus:border-violet-500"
            data-testid="sicon-mapper-automatch-textarea"
          />
          <div className="flex items-center justify-between gap-3 mt-2 flex-wrap">
            <label className="inline-flex items-center gap-1.5 text-xs text-violet-700 cursor-pointer hover:underline">
              <Upload size={12} />
              Upload CSV
              <input type="file" accept=".csv,text/csv,text/plain" className="hidden" onChange={onFile} data-testid="sicon-mapper-automatch-file" />
            </label>
            <span className="text-[11px] text-zinc-400">Headers auto-detected — override the columns below if they look wrong.</span>
          </div>

          {/* Column mapping — pick which column is Serial / Sicon / Sage */}
          {analysis && (
            <div className="mt-3 p-3 rounded-md bg-white border border-zinc-200" data-testid="sicon-mapper-colmap">
              <div className="flex items-center justify-between gap-2 mb-2 flex-wrap">
                <p className="text-[11px] font-semibold text-zinc-600">
                  Column mapping <span className="font-normal text-zinc-400">· {dataRows.length} data row(s)</span>
                  {appliedTpl && <span className="ml-1 text-violet-600">· template “{appliedTpl}” applied</span>}
                </p>
                <div className="flex items-center gap-2 flex-wrap">
                  {templates.length > 0 && (
                    <select
                      value={appliedTpl || ''}
                      onChange={(e) => { const t = templates.find((x) => x.name === e.target.value); if (t) applyTemplate(t); }}
                      className="h-7 px-2 rounded border border-zinc-300 bg-white text-[11px] focus:outline-none focus:border-violet-500"
                      data-testid="sicon-mapper-template-select"
                    >
                      <option value="">Load template…</option>
                      {templates.map((t) => <option key={t.id} value={t.name}>{t.name}</option>)}
                    </select>
                  )}
                  {appliedTpl && templates.find((t) => t.name === appliedTpl) && (
                    <button type="button" onClick={() => deleteTemplate(templates.find((t) => t.name === appliedTpl))}
                      className="text-zinc-400 hover:text-red-600" title="Delete this template" data-testid="sicon-mapper-template-delete">
                      <Trash2 size={12} />
                    </button>
                  )}
                  <button type="button" onClick={saveTemplate} className="inline-flex items-center gap-1 text-[11px] text-violet-700 hover:underline" data-testid="sicon-mapper-template-save">
                    <Bookmark size={11} /> Save template
                  </button>
                  <label className="inline-flex items-center gap-1.5 text-[11px] text-zinc-600 cursor-pointer" data-testid="sicon-mapper-header-toggle">
                    <input type="checkbox" checked={firstRowHeader} onChange={(e) => setFirstRowHeader(e.target.checked)} className="accent-violet-600" />
                    First row is a header
                  </label>
                </div>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                {[
                  { key: 'serial', label: 'Serial *', allowNone: false },
                  { key: 'sicon', label: 'Sicon Asset ID', allowNone: true },
                  { key: 'sage', label: 'Sage Item ID', allowNone: true },
                ].map(({ key, label, allowNone }) => (
                  <label key={key} className="text-xs text-zinc-600">
                    <span className="block mb-1 font-medium">{label}</span>
                    <select
                      value={colMap[key]}
                      onChange={(e) => setColMap((m) => ({ ...m, [key]: parseInt(e.target.value, 10) }))}
                      className="h-8 w-full px-2 rounded border border-zinc-300 bg-white text-xs focus:outline-none focus:border-violet-500"
                      data-testid={`sicon-mapper-colmap-${key}`}
                    >
                      {allowNone && <option value={-1}>— none —</option>}
                      {Array.from({ length: analysis.colCount }).map((_, i) => {
                        const name = header ? (header[i] || `Column ${i + 1}`) : `Column ${i + 1}`;
                        const sample = dataRows[0]?.[i];
                        return <option key={i} value={i}>{name}{sample ? ` — e.g. ${String(sample).slice(0, 16)}` : ''}</option>;
                      })}
                    </select>
                  </label>
                ))}
              </div>
            </div>
          )}

          <div className="flex items-center justify-end gap-3 mt-3">
            <Button size="sm" onClick={runAutoMatch} disabled={matching || !analysis || colMap.serial < 0}
              className="bg-violet-600 hover:bg-violet-700 text-white" data-testid="sicon-mapper-automatch-run">
              {matching ? <Loader2 size={12} className="animate-spin mr-1" /> : <Wand2 size={12} className="mr-1" />}
              Match &amp; pre-fill
            </Button>
          </div>
        </Card>
      )}

      {/* Last match summary */}
      {matchStats && !showMatch && (
        <div className="flex items-center gap-2 text-xs text-zinc-600 bg-zinc-50 border border-zinc-200 rounded-md px-3 py-2" data-testid="sicon-mapper-match-summary">
          <CheckCircle2 size={13} className="text-emerald-600" />
          <span>Matched <b>{matchStats.matched}</b> of {matchStats.import_rows} import rows.</span>
          {matchStats.unmatched_import > 0 && (
            <span className="inline-flex items-center gap-1 text-amber-700">
              <AlertTriangle size={12} /> {matchStats.unmatched_import} serial(s) had no machine here.
            </span>
          )}
          {dirtyCount > 0 && <span className="text-violet-700 font-medium">Review the highlighted rows, then Save.</span>}
        </div>
      )}

      {/* Fuzzy / near-miss review — require explicit Apply (riskier matches) */}
      {fuzzyMatches.length > 0 && (
        <Card className="border-amber-200 bg-amber-50/40 overflow-hidden" data-testid="sicon-mapper-fuzzy-card">
          <div className="px-4 py-2.5 flex items-center justify-between gap-3 border-b border-amber-100">
            <p className="text-sm font-semibold text-amber-800 flex items-center gap-1.5">
              <AlertTriangle size={14} className="text-amber-600" />
              {fuzzyMatches.length} near-miss{fuzzyMatches.length > 1 ? 'es' : ''} — review before applying
            </p>
            <Button size="sm" variant="outline" onClick={applyAllFuzzy}
              className="border-amber-300 text-amber-800 hover:bg-amber-100" data-testid="sicon-mapper-fuzzy-apply-all">
              Apply all
            </Button>
          </div>
          <div className="divide-y divide-amber-100">
            {fuzzyMatches.map((fm) => (
              <div key={fm.equipment_id} className="px-4 py-2.5 flex items-center justify-between gap-3 flex-wrap" data-testid={`sicon-mapper-fuzzy-${fm.equipment_id}`}>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-zinc-900">{fm.name}</p>
                  <p className="text-[11px] text-zinc-600 font-mono">
                    yours: <b>{fm.serial_number}</b> <span className="text-zinc-400">↔</span> import: <b>{fm.import_serial}</b>
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge className="bg-amber-100 text-amber-700 border border-amber-200 text-[10px]">{fm.reason}</Badge>
                  <span className="text-xs text-zinc-600">→ Sicon <b>{fm.suggested_sicon_equipment_id ?? '—'}</b>{fm.suggested_sage_item_id != null ? <>, Sage <b>{fm.suggested_sage_item_id}</b></> : null}</span>
                  <Button size="sm" onClick={() => applyFuzzy(fm)}
                    className="h-7 bg-violet-600 hover:bg-violet-700 text-white text-xs" data-testid={`sicon-mapper-fuzzy-apply-${fm.equipment_id}`}>
                    Apply
                  </Button>
                  <button type="button" onClick={() => dismissFuzzy(fm.equipment_id)} className="text-zinc-400 hover:text-zinc-700" data-testid={`sicon-mapper-fuzzy-dismiss-${fm.equipment_id}`}><X size={14} /></button>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Controls */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <Building2 size={14} className="text-zinc-400" />
          <select
            value={orgId}
            onChange={(e) => setOrgId(e.target.value)}
            disabled={loadingOrgs}
            className="h-9 px-2 rounded-md border border-zinc-300 bg-white text-sm text-zinc-800 focus:outline-none focus:border-violet-500"
            data-testid="sicon-mapper-org-select"
          >
            {loadingOrgs && <option>Loading…</option>}
            {orgs.map((o) => (
              <option key={o.organization_id} value={o.organization_id}>
                {o.organization_name} ({o.mapped}/{o.total})
              </option>
            ))}
          </select>
        </div>
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-400" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search name, serial or zone…"
            className="h-9 w-full pl-8 pr-2 rounded-md border border-zinc-300 bg-white text-sm focus:outline-none focus:border-violet-500"
            data-testid="sicon-mapper-search"
          />
        </div>
        {meta.total > 0 && (
          <Badge className={`border ${coveragePct >= 100 ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-amber-50 text-amber-700 border-amber-200'}`} data-testid="sicon-mapper-coverage">
            {coveragePct >= 100 ? <CheckCircle2 size={12} className="mr-1" /> : null}
            {meta.mapped}/{meta.total} mapped ({coveragePct}%)
          </Badge>
        )}
      </div>

      {/* Table */}
      <Card className="border-zinc-200 overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="animate-spin text-zinc-400" size={20} />
          </div>
        ) : filtered.length === 0 ? (
          <div className="p-10 text-center text-sm text-zinc-500">No equipment found.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-zinc-50 border-b border-zinc-200">
                <tr className="text-left text-[10px] uppercase tracking-wider text-zinc-500">
                  <th className="px-4 py-2.5 font-semibold">Machine</th>
                  <th className="px-4 py-2.5 font-semibold">Zone / Site</th>
                  <th className="px-4 py-2.5 font-semibold w-[180px]">Sicon Asset ID</th>
                  <th className="px-4 py-2.5 font-semibold w-[180px]">Sage Item ID <span className="normal-case text-zinc-400">(optional)</span></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((row) => {
                  const isDirty = !!edits[row.id];
                  return (
                    <tr key={row.id} className={`border-b border-zinc-100 ${isDirty ? 'bg-violet-50/40' : 'hover:bg-zinc-50'}`} data-testid={`sicon-mapper-row-${row.id}`}>
                      <td className="px-4 py-2.5">
                        <p className="text-sm font-medium text-zinc-900">{row.name || '—'}</p>
                        {row.serial_number && <p className="text-[10px] font-mono text-zinc-400">S/N {row.serial_number}</p>}
                        {row.manufacturer && <p className="text-[10px] text-zinc-400">{row.manufacturer}</p>}
                      </td>
                      <td className="px-4 py-2.5 text-xs text-zinc-600">
                        <span className="inline-flex items-center gap-1">
                          <MapPin size={11} className="text-zinc-400" />
                          {row.location || <span className="text-zinc-400 italic">Unassigned</span>}
                        </span>
                        {row.site_name && <p className="text-[10px] text-zinc-400 mt-0.5">{row.site_name}</p>}
                      </td>
                      <td className="px-4 py-2.5">
                        <input
                          inputMode="numeric"
                          value={valueFor(row, 'sicon_equipment_id')}
                          onChange={(e) => setField(row.id, 'sicon_equipment_id', e.target.value)}
                          placeholder="e.g. 4021"
                          className="h-8 w-full px-2 rounded border border-zinc-300 bg-white text-sm focus:outline-none focus:border-violet-500"
                          data-testid={`sicon-mapper-sicon-${row.id}`}
                        />
                      </td>
                      <td className="px-4 py-2.5">
                        <input
                          inputMode="numeric"
                          value={valueFor(row, 'sage_item_id')}
                          onChange={(e) => setField(row.id, 'sage_item_id', e.target.value)}
                          placeholder="—"
                          className="h-8 w-full px-2 rounded border border-zinc-300 bg-white text-sm focus:outline-none focus:border-violet-500"
                          data-testid={`sicon-mapper-sage-${row.id}`}
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <p className="text-[11px] text-zinc-400">
        The Sicon asset ID populates <code className="text-zinc-500">case.Equipments[].SiconEquipmentID</code> on every fault pushed to Sicon,
        so tickets attach to the correct machine. Leave blank to clear a mapping.
      </p>
    </div>
  );
}
