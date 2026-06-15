/** Org Chart visual canvas — pan, zoom, drag, reporting lines. */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ZoomIn, ZoomOut, Maximize2, RotateCcw, Wand2, Plus, Crosshair,
} from 'lucide-react';
import OrgCard from './OrgCard';
import { CARD_W, CARD_H, computeLayout, bounds } from './layout';
import { deptColor, EDGE_TYPES } from './api';

const EDGE_COLOR = Object.fromEntries(EDGE_TYPES.map((e) => [e.id, e.color]));
const MIN_SCALE = 0.25;
const MAX_SCALE = 2;

function ToolBtn({ onClick, title, children, testId }) {
  return (
    <button onClick={onClick} title={title} data-testid={testId}
      className="w-9 h-9 rounded-lg inline-flex items-center justify-center border transition-colors"
      style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}>
      {children}
    </button>
  );
}

export default function Canvas({
  nodes, edges, settings, dimmedIds, focusId, onMoveNode, onRequestSetManager, onOpenNode, onAutoLayout, onAddCard,
}) {
  const wrapRef = useRef(null);
  const [scale, setScale] = useState(0.8);
  const [tx, setTx] = useState(80);
  const [ty, setTy] = useState(40);
  const [pos, setPos] = useState({});
  const [selected, setSelected] = useState(null);
  const drag = useRef(null);
  const pan = useRef(null);
  const [hoverTarget, setHoverTarget] = useState(null);
  const [, force] = useState(0);

  const toggles = settings?.field_toggles || {};

  // Sync local positions from props.
  useEffect(() => {
    setPos((prev) => {
      const next = {};
      nodes.forEach((n) => { next[n.id] = prev[n.id] && drag.current?.id === n.id ? prev[n.id] : { x: n.x || 0, y: n.y || 0 }; });
      return next;
    });
  }, [nodes]);

  const reportsCount = useMemo(() => {
    const m = {};
    nodes.forEach((n) => { if (n.manager_node_id) m[n.manager_node_id] = (m[n.manager_node_id] || 0) + 1; });
    return m;
  }, [nodes]);

  const byId = useMemo(() => Object.fromEntries(nodes.map((n) => [n.id, n])), [nodes]);

  const toChart = useCallback((clientX, clientY) => {
    const r = wrapRef.current.getBoundingClientRect();
    return { x: (clientX - r.left - tx) / scale, y: (clientY - r.top - ty) / scale };
  }, [tx, ty, scale]);

  const fit = useCallback(() => {
    if (!wrapRef.current || !nodes.length) return;
    const b = bounds(nodes.map((n) => ({ ...n, ...(pos[n.id] || {}) })));
    const r = wrapRef.current.getBoundingClientRect();
    const w = b.maxX - b.minX; const h = b.maxY - b.minY;
    const s = Math.min((r.width - 80) / w, (r.height - 80) / h, MAX_SCALE);
    const ns = Math.max(MIN_SCALE, s || 0.8);
    setScale(ns);
    setTx((r.width - w * ns) / 2 - b.minX * ns);
    setTy((r.height - h * ns) / 2 - b.minY * ns + 10);
  }, [nodes, pos]);

  // Fit once when node count goes from 0→n.
  const fitKey = nodes.length;
  useEffect(() => { const t = setTimeout(fit, 60); return () => clearTimeout(t); /* eslint-disable-next-line */ }, [fitKey]);

  // Focus a node (from search).
  useEffect(() => {
    if (!focusId || !pos[focusId] || !wrapRef.current) return;
    const r = wrapRef.current.getBoundingClientRect();
    const p = pos[focusId];
    setScale(1);
    setTx(r.width / 2 - (p.x + CARD_W / 2));
    setTy(r.height / 2 - (p.y + CARD_H / 2));
    setSelected(focusId);
  }, [focusId]); // eslint-disable-line

  // ─── pointer handlers ───
  const onCardPointerDown = (e, node) => {
    e.stopPropagation();
    wrapRef.current.setPointerCapture?.(e.pointerId);
    drag.current = { id: node.id, startX: e.clientX, startY: e.clientY, origX: pos[node.id]?.x || 0, origY: pos[node.id]?.y || 0, moved: false, pointerId: e.pointerId };
    setSelected(node.id);
  };

  const onBgPointerDown = (e) => {
    if (e.target.closest('[data-orgcard]')) return;
    pan.current = { startX: e.clientX, startY: e.clientY, tx, ty };
    setSelected(null);
  };

  const onPointerMove = (e) => {
    if (drag.current) {
      const dx = (e.clientX - drag.current.startX) / scale;
      const dy = (e.clientY - drag.current.startY) / scale;
      if (Math.abs(dx) > 2 || Math.abs(dy) > 2) drag.current.moved = true;
      setPos((p) => ({ ...p, [drag.current.id]: { x: drag.current.origX + dx, y: drag.current.origY + dy } }));
      // hover detection for manager drop
      const c = toChart(e.clientX, e.clientY);
      let hit = null;
      nodes.forEach((n) => {
        if (n.id === drag.current.id) return;
        const np = pos[n.id]; if (!np) return;
        if (c.x >= np.x && c.x <= np.x + CARD_W && c.y >= np.y && c.y <= np.y + CARD_H) hit = n.id;
      });
      if (hit !== hoverTarget) setHoverTarget(hit);
    } else if (pan.current) {
      setTx(pan.current.tx + (e.clientX - pan.current.startX));
      setTy(pan.current.ty + (e.clientY - pan.current.startY));
    }
  };

  const onPointerUp = (e) => {
    if (drag.current) {
      const d = drag.current;
      const target = hoverTarget;
      drag.current = null;
      setHoverTarget(null);
      if (d.moved && target && target !== d.id) {
        // reset visual position; manager change re-layouts via parent
        setPos((p) => ({ ...p, [d.id]: { x: byId[d.id].x, y: byId[d.id].y } }));
        onRequestSetManager(d.id, target);
      } else if (d.moved) {
        const np = pos[d.id];
        onMoveNode(d.id, { x: Math.round(np.x), y: Math.round(np.y) });
      }
    }
    pan.current = null;
    force((n) => n + 1);
  };

  const onWheel = (e) => {
    e.preventDefault();
    const r = wrapRef.current.getBoundingClientRect();
    const factor = e.deltaY < 0 ? 1.12 : 0.89;
    const ns = Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale * factor));
    const cx = e.clientX - r.left; const cy = e.clientY - r.top;
    setTx(cx - (cx - tx) * (ns / scale));
    setTy(cy - (cy - ty) * (ns / scale));
    setScale(ns);
  };

  const zoom = (factor) => {
    const ns = Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale * factor));
    const r = wrapRef.current.getBoundingClientRect();
    const cx = r.width / 2; const cy = r.height / 2;
    setTx(cx - (cx - tx) * (ns / scale));
    setTy(cy - (cy - ty) * (ns / scale));
    setScale(ns);
  };

  // connection paths
  const paths = useMemo(() => nodes.map((n) => {
    if (!n.manager_node_id || !byId[n.manager_node_id]) return null;
    const m = pos[n.manager_node_id]; const c = pos[n.id];
    if (!m || !c) return null;
    const sx = m.x + CARD_W / 2; const sy = m.y + CARD_H;
    const ex = c.x + CARD_W / 2; const ey = c.y;
    const midY = (sy + ey) / 2;
    const dim = dimmedIds.has(n.id) || dimmedIds.has(n.manager_node_id);
    return { id: n.id, d: `M ${sx} ${sy} C ${sx} ${midY}, ${ex} ${midY}, ${ex} ${ey}`, dim };
  }).filter(Boolean), [nodes, pos, byId, dimmedIds]);

  // dashed secondary-reporting edges
  const edgePaths = useMemo(() => (edges || []).map((e) => {
    const a = pos[e.from_node_id]; const b = pos[e.to_node_id];
    if (!a || !b) return null;
    const sx = a.x + CARD_W / 2; const sy = a.y + CARD_H / 2;
    const ex = b.x + CARD_W / 2; const ey = b.y + CARD_H / 2;
    return { id: e.id, d: `M ${sx} ${sy} C ${(sx + ex) / 2} ${sy}, ${(sx + ex) / 2} ${ey}, ${ex} ${ey}`, color: EDGE_COLOR[e.line_type] || '#7c3aed' };
  }).filter(Boolean), [edges, pos]);

  // department / site grouping frames
  const groupBy = settings?.group_by;
  const frames = useMemo(() => {
    if (groupBy !== 'department' && groupBy !== 'site') return [];
    const groups = {};
    nodes.forEach((n) => {
      const key = groupBy === 'department' ? (n.department || 'Unassigned') : (n.site_name || 'No site');
      const p = pos[n.id]; if (!p) return;
      const g = groups[key] || { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity, count: 0 };
      g.minX = Math.min(g.minX, p.x); g.minY = Math.min(g.minY, p.y);
      g.maxX = Math.max(g.maxX, p.x + CARD_W); g.maxY = Math.max(g.maxY, p.y + CARD_H);
      g.count += 1; groups[key] = g;
    });
    const PAD = 22;
    return Object.entries(groups).filter(([, g]) => g.count > 0 && isFinite(g.minX)).map(([key, g]) => ({
      key, color: deptColor(key),
      x: g.minX - PAD, y: g.minY - PAD - 18, w: g.maxX - g.minX + PAD * 2, h: g.maxY - g.minY + PAD * 2 + 18,
    }));
  }, [groupBy, nodes, pos]);

  return (
    <div className="relative rounded-2xl overflow-hidden border" style={{ borderColor: 'var(--theme-border)', height: '64vh', minHeight: 460 }} data-testid="orgchart-canvas">
      {/* toolbar */}
      <div className="absolute top-3 left-3 z-30 flex gap-1.5">
        <ToolBtn onClick={onAddCard} title="Add card" testId="orgchart-toolbar-add"><Plus size={16} /></ToolBtn>
        <ToolBtn onClick={onAutoLayout} title="Auto-layout" testId="orgchart-toolbar-autolayout"><Wand2 size={16} /></ToolBtn>
      </div>
      <div className="absolute top-3 right-3 z-30 flex gap-1.5">
        <ToolBtn onClick={() => zoom(1.15)} title="Zoom in" testId="orgchart-zoom-in"><ZoomIn size={16} /></ToolBtn>
        <ToolBtn onClick={() => zoom(0.87)} title="Zoom out" testId="orgchart-zoom-out"><ZoomOut size={16} /></ToolBtn>
        <ToolBtn onClick={fit} title="Fit to screen" testId="orgchart-fit"><Maximize2 size={16} /></ToolBtn>
        <ToolBtn onClick={() => { setScale(0.8); setTx(80); setTy(40); }} title="Reset view" testId="orgchart-reset"><RotateCcw size={16} /></ToolBtn>
      </div>
      <div className="absolute bottom-3 right-3 z-30 text-[10px] font-semibold px-2 py-1 rounded-md" style={{ background: 'var(--theme-surface)', color: 'var(--theme-text-muted)', border: '1px solid var(--theme-border)' }}>
        {Math.round(scale * 100)}%
      </div>

      {/* grid + canvas */}
      <div
        ref={wrapRef}
        className="absolute inset-0"
        style={{
          cursor: pan.current ? 'grabbing' : 'default', touchAction: 'none',
          background: settings?.show_grid
            ? 'radial-gradient(circle, rgba(100,116,139,0.18) 1px, transparent 1px)' : 'var(--theme-bg, #fbfcfe)',
          backgroundSize: settings?.show_grid ? `${24 * scale}px ${24 * scale}px` : undefined,
          backgroundPosition: settings?.show_grid ? `${tx}px ${ty}px` : undefined,
          backgroundColor: 'var(--theme-bg, #fbfcfe)',
        }}
        onPointerDown={onBgPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onWheel={onWheel}
      >
        <div style={{ position: 'absolute', left: 0, top: 0, transform: `translate(${tx}px, ${ty}px) scale(${scale})`, transformOrigin: '0 0' }}>
          {frames.map((f) => (
            <div key={f.key} className="absolute rounded-2xl" data-group-frame="1" data-testid={`orgchart-group-frame-${f.key}`} style={{ left: f.x, top: f.y, width: f.w, height: f.h, background: `${f.color}0d`, border: `1.5px dashed ${f.color}55`, zIndex: 1 }}>
              <span className="absolute -top-0.5 left-3 text-[11px] font-bold px-2 py-0.5 rounded-b-md" style={{ background: f.color, color: '#fff' }}>{f.key}</span>
            </div>
          ))}
          <svg style={{ position: 'absolute', left: 0, top: 0, overflow: 'visible', width: 1, height: 1, pointerEvents: 'none', zIndex: 5 }}>
            {paths.map((p) => (
              <path key={p.id} d={p.d} fill="none" stroke="#94a3b8" strokeWidth={1.6} strokeOpacity={p.dim ? 0.15 : 0.6} />
            ))}
            {edgePaths.map((p) => (
              <path key={p.id} d={p.d} fill="none" stroke={p.color} strokeWidth={1.6} strokeDasharray="5 4" strokeOpacity={0.7} />
            ))}
          </svg>
          {nodes.map((n) => {
            const p = pos[n.id] || { x: n.x, y: n.y };
            const dim = dimmedIds.has(n.id);
            return (
              <div key={n.id} style={{ opacity: dim ? 0.22 : 1, pointerEvents: dim ? 'none' : 'auto' }}>
                <OrgCard
                  node={{ ...n, x: p.x, y: p.y }}
                  toggles={toggles}
                  reportsCount={reportsCount[n.id] || 0}
                  selected={selected === n.id || hoverTarget === n.id}
                  dragging={drag.current?.id === n.id}
                  onPointerDown={(e) => onCardPointerDown(e, n)}
                  onOpen={onOpenNode}
                />
              </div>
            );
          })}
        </div>
      </div>

      {!nodes.length && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-center px-6 z-20">
          <Crosshair size={26} style={{ color: 'var(--theme-text-muted)' }} />
          <p className="text-sm font-semibold" style={{ color: 'var(--theme-text)' }}>No cards yet</p>
          <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>Add a card or sync your staff to start building.</p>
        </div>
      )}
    </div>
  );
}
