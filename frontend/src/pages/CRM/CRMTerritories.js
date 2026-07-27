/**
 * CRM Territories settings page (iter 215dc).
 *
 * Enterprise coverage-area management with postcode-based auto-
 * assignment + sales-team hierarchy tree. Split across three files
 * to keep Babel's visitor recursion shallow:
 *   - CRMTerritories.js (this file — shell + data loading).
 *   - CRMTerritoryEditor.js (create/edit modal).
 *   - CRMTerritoryPieces.js (TerritoryRow + TeamNode list items).
 *
 * Iter 216h278 — adds an interactive UK map view alongside the list:
 *   - CRMTerritoryMap.js (visual coverage painter)
 *   Tabs let admins switch between the legacy list-based editor and
 *   the new map. The two views share the same `crm_territories`
 *   collection so changes flow both ways without extra wiring.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { MapPin, Plus, PlayCircle, RefreshCw, Layers, ArrowRightLeft, List, Map as MapIcon } from 'lucide-react';
import TerritoryEditor from './CRMTerritoryEditor';
import TerritoryTreeDnD from './CRMTerritoryTreeDnD';
import { TerritoryRow, TeamNode } from './CRMTerritoryPieces';
import CRMTerritoryMap from './CRMTerritoryMap';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => { const _t = localStorage.getItem('crm_token'); return { headers: _t ? { Authorization: `Bearer ${_t}` } : {} }; };

export default function CRMTerritories() {
  const [view, setView] = useState('map');
  const [territories, setTerritories] = useState([]);
  const [rollup, setRollup] = useState([]);
  const [tree, setTree] = useState([]);
  const [reps, setReps] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editor, setEditor] = useState({ open: false, initial: null });
  const [running, setRunning] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r1, r2, r3] = await Promise.all([
        axios.get(`${API}/crm/territories/rollup`, auth()),
        axios.get(`${API}/crm/territories/team/tree`, auth()),
        axios.get(`${API}/crm/territories`, auth()),
      ]);
      setRollup(r1.data.rows || []);
      setTree(r2.data.tree || []);
      setTerritories(r3.data.territories || []);
      const flat = [];
      const walk = (nodes) => nodes.forEach((n) => { flat.push(n); if (n.directs) walk(n.directs); });
      walk(r2.data.tree || []);
      setReps(flat);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to load territories');
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const rollupById = useMemo(() => {
    const m = {};
    rollup.forEach((r) => { m[r.id] = r; });
    return m;
  }, [rollup]);
  const enriched = useMemo(() => territories.map((t) => ({ ...t, ...(rollupById[t.id] || {}) })), [territories, rollupById]);

  const archive = async (t) => {
    if (!window.confirm(`Archive territory "${t.name}"?`)) return;
    try {
      await axios.delete(`${API}/crm/territories/${t.id}`, auth());
      toast.success('Archived');
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || 'Archive failed'); }
  };

  const runAutoAssign = async (dry) => {
    setRunning(true);
    try {
      const r = await axios.post(
        `${API}/crm/territories/auto-assign`,
        { entity: 'company', dry_run: dry, only_unassigned: true },
        auth(),
      );
      if (dry) toast.success(`Preview: ${r.data.total_proposed} company(s) would be assigned.`);
      else { toast.success(`${r.data.changed} company(s) assigned.`); load(); }
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Auto-assign failed');
    } finally { setRunning(false); }
  };

  const handleEdit = (init) => setEditor({ open: true, initial: init });
  const handleNew = () => setEditor({ open: true, initial: null });
  const handleEditorClose = () => setEditor({ open: false, initial: null });
  const handleEditorSaved = () => { handleEditorClose(); load(); };

  const emptyState = (
    <div className="rounded-xl border border-dashed border-[color:var(--theme-border)] p-6 text-center">
      <MapPin size={24} className="mx-auto text-[color:var(--theme-text-muted)] mb-2" />
      <p className="text-sm text-[color:var(--theme-text-muted)]">No territories yet. Create your first one — start with a wide geography then split into regions.</p>
    </div>
  );

  return (
    <div className="max-w-6xl mx-auto px-4 py-3 space-y-3" data-testid="crm-territories-page">
      {/* Iter 216h278 — Map / List view toggle. The map is the new
          default because it's the more intuitive way to allocate
          coverage; the list view stays one click away for power users
          who'd rather see the audit + rollup data densely tabulated. */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="inline-flex border border-[color:var(--theme-border)] rounded-lg overflow-hidden bg-white dark:bg-zinc-900" data-testid="territories-view-toggle">
          <button
            type="button"
            onClick={() => setView('map')}
            className={`px-3 py-1.5 text-xs font-bold inline-flex items-center gap-1.5 ${view === 'map' ? 'seg-active' : 'text-zinc-900 dark:text-zinc-100 hover:bg-zinc-100 dark:hover:bg-zinc-800/60'}`}
            data-testid="territories-view-map"
          >
            <MapIcon size={12} /> Map
          </button>
          <button
            type="button"
            onClick={() => setView('list')}
            className={`px-3 py-1.5 text-xs font-bold inline-flex items-center gap-1.5 ${view === 'list' ? 'seg-active' : 'text-zinc-900 dark:text-zinc-100 hover:bg-zinc-100 dark:hover:bg-zinc-800/60'}`}
            data-testid="territories-view-list"
          >
            <List size={12} /> List & teams
          </button>
        </div>
        {view === 'list' && (
          <header className="flex flex-wrap items-center justify-end gap-2">
              <button onClick={() => runAutoAssign(true)} disabled={running} className="px-3 py-2 rounded-lg text-sm font-bold border border-[color:var(--theme-border)] inline-flex items-center gap-1.5" data-testid="auto-assign-dry" type="button">
                <PlayCircle size={14} /> Preview
              </button>
              <button onClick={() => runAutoAssign(false)} disabled={running} className="px-3 py-2 rounded-lg text-sm font-extrabold text-white inline-flex items-center gap-1.5" style={{ background: 'var(--color-brand-blue)' }} data-testid="auto-assign-apply" type="button">
                <RefreshCw size={14} className={running ? 'animate-spin' : ''} /> Apply auto-assign
              </button>
              <button onClick={handleNew} className="px-3 py-2 rounded-lg text-sm font-extrabold text-white inline-flex items-center gap-1.5" style={{ background: 'var(--color-brand-blue)' }} data-testid="new-territory" type="button">
                <Plus size={14} /> New territory
              </button>
          </header>
        )}
      </div>

      {view === 'map' ? (
        <CRMTerritoryMap />
      ) : (
        <section className="grid md:grid-cols-2 gap-6">
        <div>
          <h2 className="text-sm font-bold uppercase tracking-[0.18em] text-[color:var(--theme-text-muted)] mb-3 flex items-center gap-2">
            <Layers size={13} /> Territories ({enriched.length})
          </h2>
          <div className="space-y-3">
            {loading ? <p className="text-sm text-[color:var(--theme-text-muted)]">Loading…</p> : null}
            {!loading && enriched.length === 0 ? emptyState : null}
            {enriched.map((t) => (
              <TerritoryRow key={t.id} territory={t} onEdit={handleEdit} onArchive={archive} />
            ))}
          </div>
        </div>

        <div className="space-y-6">
          <div>
            <h2 className="text-sm font-bold uppercase tracking-[0.18em] text-[color:var(--theme-text-muted)] mb-3 flex items-center gap-2">
              <Layers size={13} /> Territory hierarchy (drag to re-parent)
            </h2>
            <TerritoryTreeDnD territories={enriched} onReparented={load} />
          </div>

          <div>
            <h2 className="text-sm font-bold uppercase tracking-[0.18em] text-[color:var(--theme-text-muted)] mb-3 flex items-center gap-2">
              <ArrowRightLeft size={13} /> Sales team hierarchy
            </h2>
            <div className="rounded-xl border border-[color:var(--theme-border)] p-4 bg-[color:var(--theme-surface)]">
              {tree.length === 0 ? (
                <p className="text-sm text-[color:var(--theme-text-muted)]">No reps yet.</p>
              ) : tree.map((n) => <TeamNode key={n.id} node={n} />)}
            </div>
            <p className="text-[11px] text-[color:var(--theme-text-muted)] mt-2">
              Managers see their whole team's pipeline via "My team" filter on Contacts, Companies, and Deals.
            </p>
          </div>
        </div>
        </section>
      )}

      <TerritoryEditor
        open={editor.open}
        initial={editor.initial}
        reps={reps}
        onClose={handleEditorClose}
        onSaved={handleEditorSaved}
      />
    </div>
  );
}
