import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import axios from 'axios';
import { notify } from '@/components/notifications';
import {
  Link2, Loader2, Save, Search, Building2, MapPin, RefreshCw, CheckCircle2,
  Wand2, Upload, X, AlertTriangle,
} from 'lucide-react';

// Parse pasted/uploaded CSV or TSV into normalized import rows.
// Auto-detects a header row and common column-name variants; falls back to
// positional order [serial, sicon_equipment_id, sage_item_id] when headerless.
function parseImport(text) {
  const lines = (text || '').split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  if (!lines.length) return { rows: [], columns: null };
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
  const cells0 = splitLine(lines[0]).map((c) => c.toLowerCase());
  const findIdx = (preds) => cells0.findIndex((h) => preds.some((p) => h.includes(p)));
  let serialIdx = findIdx(['serial']);
  let siconIdx = cells0.findIndex((h) => h.includes('sicon') || (h.includes('equip') && h.includes('id')) || h === 'asset id' || h.includes('assetid'));
  let sageIdx = cells0.findIndex((h) => h.includes('sage') || (h.includes('item') && h.includes('id')) || h.includes('stock'));
  const hasHeader = serialIdx !== -1 || siconIdx !== -1 || sageIdx !== -1;
  if (!hasHeader) { serialIdx = 0; siconIdx = 1; sageIdx = 2; }
  const dataLines = hasHeader ? lines.slice(1) : lines;
  const rows = [];
  dataLines.forEach((line) => {
    const cells = splitLine(line);
    const serial = serialIdx >= 0 ? cells[serialIdx] : '';
    if (!serial) return;
    rows.push({
      serial,
      sicon_equipment_id: siconIdx >= 0 ? (cells[siconIdx] || '') : '',
      sage_item_id: sageIdx >= 0 ? (cells[sageIdx] || '') : '',
    });
  });
  return {
    rows,
    columns: { serialIdx, siconIdx, sageIdx, hasHeader, header: hasHeader ? splitLine(lines[0]) : null },
  };
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
  const [matching, setMatching] = useState(false);
  const [matchStats, setMatchStats] = useState(null);

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

  const runAutoMatch = async () => {
    const { rows: importRows } = parseImport(pasteText);
    if (!importRows.length) {
      notify.error('Nothing to match', 'Paste rows with at least a serial number.');
      return;
    }
    setMatching(true);
    try {
      const res = await axios.post(
        `${API}/master-admin/sicon/equipment-mapping/${orgId}/auto-match`,
        { source: 'import', rows: importRows },
        { headers },
      );
      const { matched = [], stats = {} } = res.data || {};
      // Pre-fill only where a suggestion differs from the current value.
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
      const prefilled = Object.keys(next).length;
      notify.success(
        `Matched ${stats.matched || 0} of ${stats.import_rows || 0} import rows — ${prefilled} pre-filled`,
        `${stats.unmatched_import || 0} import row(s) had no matching serial. Review the highlighted rows, then Save.`,
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
            <span className="text-[11px] text-zinc-400">Headers auto-detected (Serial / Sicon / Sage). Headerless = column order Serial, Sicon, Sage.</span>
            <Button size="sm" onClick={runAutoMatch} disabled={matching || !pasteText.trim()}
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
