/** Tidy-tree layout for the org chart canvas.
 *
 * Positions are returned in chart-space (px). Cards are CARD_W wide and
 * stacked by depth. Multiple roots (people with no manager) are laid out
 * side by side with a gap between trees. */
export const CARD_W = 196;
export const CARD_H = 116;
const X_GAP = 224;
const Y_GAP = 168;
const V_INDENT = 56;            // horizontal indent per depth (vertical layout)
const V_ROW = CARD_H + 28;      // row pitch (vertical layout)

export function computeLayout(nodes, dir = 'top-down') {
  const byId = {};
  nodes.forEach((n) => { byId[n.id] = n; });
  const children = {};
  nodes.forEach((n) => {
    const m = n.manager_node_id && byId[n.manager_node_id] ? n.manager_node_id : '__root__';
    (children[m] = children[m] || []).push(n.id);
  });
  const roots = children.__root__ || [];

  // ── Vertical (stacked) — indented tree: every report stacks below its
  // manager and indents right; sibling teams stack on top of each other.
  // Produces a tall, narrow, print-friendly chart (matches the Pulse style).
  if (dir === 'vertical') {
    const posV = {};
    const seenV = new Set();
    let row = 0;
    const visit = (id, depth) => {
      if (seenV.has(id)) return;
      seenV.add(id);
      posV[id] = { x: depth * V_INDENT, y: row * V_ROW };
      row += 1;
      (children[id] || []).forEach((k) => visit(k, depth + 1));
    };
    roots.forEach((r) => visit(r, 0));
    nodes.forEach((n) => { if (!posV[n.id]) { posV[n.id] = { x: 0, y: row * V_ROW }; row += 1; } });
    return nodes.map((n) => ({ ...n, x: posV[n.id].x, y: posV[n.id].y }));
  }

  const pos = {};
  let cursor = 0;
  const seen = new Set();

  const place = (id, depth) => {
    if (seen.has(id)) { pos[id] = { lane: cursor, depth }; cursor += 1; return cursor - 1; }
    seen.add(id);
    const kids = (children[id] || []).filter((k) => !seen.has(k));
    if (!kids.length) {
      pos[id] = { lane: cursor, depth };
      cursor += 1;
      return pos[id].lane;
    }
    const lanes = kids.map((k) => place(k, depth + 1));
    const lane = (lanes[0] + lanes[lanes.length - 1]) / 2;
    pos[id] = { lane, depth };
    return lane;
  };

  roots.forEach((r) => { place(r, 0); cursor += 0.6; });
  // Any node not reached (orphan cycle) — drop into a fresh lane.
  nodes.forEach((n) => { if (!pos[n.id]) { pos[n.id] = { lane: cursor, depth: 0 }; cursor += 1; } });

  return nodes.map((n) => {
    const p = pos[n.id];
    if (dir === 'left-right') {
      return { ...n, x: p.depth * (CARD_W + 80), y: p.lane * (CARD_H + 30) };
    }
    return { ...n, x: p.lane * X_GAP, y: p.depth * Y_GAP };
  });
}

/** Bounding box of all cards in chart-space. */
export function bounds(nodes) {
  if (!nodes.length) return { minX: 0, minY: 0, maxX: 800, maxY: 600 };
  let minX = Infinity; let minY = Infinity; let maxX = -Infinity; let maxY = -Infinity;
  nodes.forEach((n) => {
    minX = Math.min(minX, n.x);
    minY = Math.min(minY, n.y);
    maxX = Math.max(maxX, n.x + CARD_W);
    maxY = Math.max(maxY, n.y + CARD_H);
  });
  return { minX, minY, maxX, maxY };
}
