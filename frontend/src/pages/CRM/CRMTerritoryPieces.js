/**
 * TerritoryRow + TeamNode — list-item components extracted into their
 * own file so Babel's JSX traversal stays shallow on the main page.
 */
import React, { useState } from 'react';
import { MapPin, Users, Pencil, Trash2, ChevronDown, ChevronRight } from 'lucide-react';

const StatPill = ({ label, value }) => (
  <span className="inline-flex items-center gap-1">
    <span className="font-semibold" style={{ color: 'var(--theme-text)' }}>{value ?? 0}</span>
    <span>{label}</span>
  </span>
);

export function TerritoryRow({ territory, onEdit, onArchive }) {
  const t = territory;
  const prefixes = t.postcode_prefixes || [];
  const reps = t.assigned_rep_ids || [];
  return (
    <div className="rounded-xl border border-[color:var(--theme-border)] p-4 flex items-start gap-3" data-testid={`territory-row-${t.id}`}>
      <div className="h-9 w-9 rounded-full flex items-center justify-center" style={{ background: 'var(--color-brand-blue)', color: 'white' }}>
        <MapPin size={16} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <h3 className="font-bold truncate" style={{ color: 'var(--theme-text)' }}>{t.name}</h3>
          {t.priority > 0 ? <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-[color:var(--theme-border)]">P{t.priority}</span> : null}
        </div>
        {t.description ? <p className="text-xs text-[color:var(--theme-text-muted)] mt-0.5 truncate">{t.description}</p> : null}
        <div className="flex flex-wrap gap-1 mt-2">
          {prefixes.slice(0, 6).map((p) => (
            <span key={p} className="text-[11px] font-semibold px-2 py-0.5 rounded-full border border-[color:var(--theme-border)]">{p}</span>
          ))}
          {reps.length > 0 ? (
            <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full ml-auto inline-flex items-center gap-1" style={{ color: 'var(--color-brand-blue)' }}>
              <Users size={10} /> {reps.length} rep{reps.length === 1 ? '' : 's'}
            </span>
          ) : null}
        </div>
        <div className="flex gap-2 mt-3 text-xs text-[color:var(--theme-text-muted)] flex-wrap">
          <StatPill label="Contacts" value={t.contacts} />
          <StatPill label="Companies" value={t.companies} />
          <StatPill label="Pipeline" value={`£${(t.pipeline_value || 0).toLocaleString()}`} />
          <StatPill label="Won" value={`£${(t.won_value || 0).toLocaleString()}`} />
        </div>
      </div>
      <div className="flex flex-col gap-1">
        <button onClick={() => onEdit(t)} className="h-8 w-8 rounded-full border border-[color:var(--theme-border)] flex items-center justify-center" aria-label="Edit" data-testid={`territory-edit-${t.id}`} type="button">
          <Pencil size={13} />
        </button>
        <button onClick={() => onArchive(t)} className="h-8 w-8 rounded-full border border-[color:var(--theme-border)] flex items-center justify-center" aria-label="Archive" data-testid={`territory-archive-${t.id}`} type="button">
          <Trash2 size={13} />
        </button>
      </div>
    </div>
  );
}

export function TeamNode({ node, level = 0 }) {
  // Iter 215dc — flatten the tree iteratively instead of recursing at
  // render time. Babel's JSX visitor was blowing its stack on the
  // self-referential JSX component. Collapsible per-branch state is
  // kept in a plain Set.
  const [collapsed, setCollapsed] = useState(() => new Set());

  const rows = [];
  const walk = (n, depth) => {
    const kids = n.directs || [];
    rows.push({ node: n, depth, hasKids: kids.length > 0 });
    if (kids.length > 0 && !collapsed.has(n.id)) {
      kids.forEach((k) => walk(k, depth + 1));
    }
  };
  walk(node, level);

  const toggle = (id) => {
    const next = new Set(collapsed);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setCollapsed(next);
  };

  return (
    <div>
      {rows.map(({ node: n, depth, hasKids }) => {
        const initial = (n.full_name || n.email || '?').charAt(0).toUpperCase();
        const isCollapsed = collapsed.has(n.id);
        return (
          <div key={n.id} className="flex items-center gap-2 py-1.5" style={{ paddingLeft: `${depth * 20}px` }}>
            {hasKids ? (
              <button onClick={() => toggle(n.id)} className="h-5 w-5 flex items-center justify-center" type="button" aria-label={isCollapsed ? 'Expand' : 'Collapse'}>
                {isCollapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
              </button>
            ) : <div className="h-5 w-5" />}
            <div className="h-7 w-7 rounded-full flex items-center justify-center text-xs font-bold" style={{ background: 'var(--color-brand-blue)', color: 'white' }}>
              {initial}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold truncate" style={{ color: 'var(--theme-text)' }}>{n.full_name || n.email}</p>
              <p className="text-[11px] uppercase tracking-wider text-[color:var(--theme-text-muted)]">{n.role}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
