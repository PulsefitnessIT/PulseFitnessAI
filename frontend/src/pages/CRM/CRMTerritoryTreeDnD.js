/**
 * Drag-and-drop territory tree (Iter 216h226).
 *
 * Flattens the tree iteratively (no recursive JSX) — keeps Babel's
 * visitor stack shallow. Drag a territory onto another to re-parent;
 * drop on the top bar to detach.
 */
import { useMemo, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { MapPin, ChevronDown, ChevronRight, GripVertical } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => { const _t = localStorage.getItem('crm_token'); return { headers: _t ? { Authorization: `Bearer ${_t}` } : {} }; };

// Build root nodes (each with `children: []`) from a flat list.
function buildRoots(rows) {
  const byId = {};
  rows.forEach(r => { byId[r.id] = { ...r, children: [] }; });
  const roots = [];
  rows.forEach(r => {
    const node = byId[r.id];
    if (r.parent_id && byId[r.parent_id]) byId[r.parent_id].children.push(node);
    else roots.push(node);
  });
  return roots;
}

// True when candidateParent is in nodeId's subtree (cycle prevention).
function wouldCycle(rows, nodeId, candidateParentId) {
  if (!candidateParentId) return false;
  if (nodeId === candidateParentId) return true;
  const byId = Object.fromEntries(rows.map(r => [r.id, r]));
  let cur = byId[candidateParentId];
  while (cur && cur.parent_id) {
    if (cur.parent_id === nodeId) return true;
    cur = byId[cur.parent_id];
  }
  return false;
}

// Iteratively flatten roots → rows of {node, depth, hasKids} honouring collapsed set.
function flattenVisible(roots, collapsedIds) {
  const rows = [];
  const walk = (n, depth) => {
    const kids = n.children || [];
    rows.push({ node: n, depth, hasKids: kids.length > 0 });
    if (kids.length > 0 && !collapsedIds.has(n.id)) {
      kids.forEach(k => walk(k, depth + 1));
    }
  };
  roots.forEach(r => walk(r, 0));
  return rows;
}

export default function TerritoryTreeDnD({ territories, onReparented }) {
  const roots = useMemo(() => buildRoots(territories || []), [territories]);
  const [collapsedIds, setCollapsedIds] = useState(() => new Set());
  const [draggingId, setDraggingId] = useState(null);
  const [dragOverId, setDragOverId] = useState(null);
  const [saving, setSaving] = useState(false);

  const flat = useMemo(() => flattenVisible(roots, collapsedIds), [roots, collapsedIds]);

  const toggle = (id) => {
    const next = new Set(collapsedIds);
    if (next.has(id)) next.delete(id); else next.add(id);
    setCollapsedIds(next);
  };

  const reparent = async (nodeId, newParentId) => {
    if (!nodeId) return;
    if (wouldCycle(territories, nodeId, newParentId)) {
      toast.error('Cannot drop a territory onto its own descendant');
      setDraggingId(null);
      setDragOverId(null);
      return;
    }
    const current = territories.find(t => t.id === nodeId);
    if (current?.parent_id === newParentId) {
      setDraggingId(null);
      setDragOverId(null);
      return;
    }
    setSaving(true);
    try {
      await axios.put(`${API}/crm/territories/${nodeId}`, { parent_id: newParentId || null }, auth());
      toast.success(newParentId ? 'Territory re-parented' : 'Territory moved to top-level');
      onReparented?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to re-parent');
    } finally {
      setSaving(false);
      setDraggingId(null);
      setDragOverId(null);
    }
  };

  return (
    <div className="rounded-xl border border-[color:var(--theme-border)] p-2 bg-[color:var(--theme-surface)]" data-testid="territory-tree-dnd">
      <div
        className="text-[11px] uppercase tracking-wider font-bold py-2 px-3 rounded-md mb-1"
        style={{
          color: 'var(--theme-text-muted)',
          background: dragOverId === '__root__' ? 'var(--theme-surface-hover)' : 'transparent',
          boxShadow: dragOverId === '__root__' ? 'inset 0 0 0 2px var(--color-brand-blue)' : 'none',
        }}
        onDragOver={(e) => { e.preventDefault(); setDragOverId('__root__'); }}
        onDragLeave={() => setDragOverId((cur) => (cur === '__root__' ? null : cur))}
        onDrop={(e) => { e.preventDefault(); reparent(draggingId, null); }}
      >
        ↑ Drop here to move to top-level
      </div>
      {flat.length === 0 && <p className="text-sm text-[color:var(--theme-text-muted)] py-4 px-3">No territories yet.</p>}
      {flat.map(({ node, depth, hasKids }) => {
        const isOver = dragOverId === node.id;
        const isDragging = draggingId === node.id;
        const collapsed = collapsedIds.has(node.id);
        return (
          <div
            key={node.id}
            className={`group flex items-center gap-2 py-1.5 px-2 rounded-md transition-colors ${isDragging ? 'opacity-40' : ''}`}
            style={{
              paddingLeft: `${depth * 18 + 8}px`,
              background: isOver ? 'var(--theme-surface-hover)' : 'transparent',
              boxShadow: isOver ? 'inset 0 0 0 2px var(--color-brand-blue)' : 'none',
            }}
            draggable
            onDragStart={(e) => { e.dataTransfer.effectAllowed = 'move'; setDraggingId(node.id); setDragOverId(null); }}
            onDragOver={(e) => { e.preventDefault(); setDragOverId(node.id); }}
            onDragLeave={() => setDragOverId((cur) => (cur === node.id ? null : cur))}
            onDrop={(e) => { e.preventDefault(); reparent(draggingId, node.id); }}
            data-testid={`territory-tree-node-${node.id}`}
          >
            <GripVertical size={12} className="text-[color:var(--theme-text-muted)] opacity-0 group-hover:opacity-100 cursor-grab" />
            {hasKids ? (
              <button onClick={() => toggle(node.id)} className="h-5 w-5 flex items-center justify-center" type="button" aria-label={collapsed ? 'Expand' : 'Collapse'}>
                {collapsed ? <ChevronRight size={13} /> : <ChevronDown size={13} />}
              </button>
            ) : <div className="h-5 w-5" />}
            <div className="h-6 w-6 rounded-full flex items-center justify-center" style={{ background: 'var(--color-brand-blue)', color: 'white' }}>
              <MapPin size={11} />
            </div>
            <span className="text-sm font-semibold truncate flex-1" style={{ color: 'var(--theme-text)' }}>{node.name}</span>
            {node.assigned_rep_ids?.length ? (
              <span className="text-[10px] uppercase tracking-wider text-[color:var(--theme-text-muted)]">
                {node.assigned_rep_ids.length} rep{node.assigned_rep_ids.length === 1 ? '' : 's'}
              </span>
            ) : null}
          </div>
        );
      })}
      {saving && <p className="text-[10px] text-[color:var(--theme-text-muted)] py-2 px-3">Saving…</p>}
      <p className="text-[10px] text-[color:var(--theme-text-muted)] px-3 py-2">Tip: drag a territory onto another to nest. Drop on the top bar to detach.</p>
    </div>
  );
}
