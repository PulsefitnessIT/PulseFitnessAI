/** Org Chart — table/list view (admin-friendly). */
import { useMemo } from 'react';
import { Link2, Users } from 'lucide-react';
import { humanize, NODE_LABELS } from './api';

export default function ListView({ nodes, byId, onOpen }) {
  const reports = useMemo(() => {
    const m = {};
    nodes.forEach((n) => { if (n.manager_node_id) m[n.manager_node_id] = (m[n.manager_node_id] || 0) + 1; });
    return m;
  }, [nodes]);

  if (!nodes.length) {
    return <div className="rounded-2xl p-10 border text-center text-sm" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }} data-testid="orgchart-list-empty">No cards yet.</div>;
  }

  return (
    <div className="rounded-2xl border overflow-x-auto" style={{ borderColor: 'var(--theme-border)' }} data-testid="orgchart-list-view">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-[10px] uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>
            {['Name', 'Job title', 'Type', 'Department', 'Site', 'Manager', 'Reports', 'Status', 'Linked'].map((h) => (
              <th key={h} className="px-3 py-2.5 font-bold whitespace-nowrap">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {nodes.map((n) => (
            <tr key={n.id} className="border-t cursor-pointer hover:bg-black/[0.02]" style={{ borderColor: 'var(--theme-border)' }} onClick={() => onOpen(n)} data-testid={`orgchart-list-row-${n.id}`}>
              <td className="px-3 py-2.5 font-semibold" style={{ color: 'var(--theme-text)' }}>{n.full_name}</td>
              <td className="px-3 py-2.5" style={{ color: 'var(--theme-text-muted)' }}>{humanize(n.job_title) || '—'}</td>
              <td className="px-3 py-2.5 text-xs">{NODE_LABELS[n.type] || n.type}</td>
              <td className="px-3 py-2.5" style={{ color: 'var(--theme-text-muted)' }}>{n.department || '—'}</td>
              <td className="px-3 py-2.5" style={{ color: 'var(--theme-text-muted)' }}>{n.site_name || '—'}</td>
              <td className="px-3 py-2.5" style={{ color: 'var(--theme-text-muted)' }}>{byId[n.manager_node_id]?.full_name || '—'}</td>
              <td className="px-3 py-2.5">{reports[n.id] ? <span className="inline-flex items-center gap-1 font-semibold" style={{ color: 'var(--color-brand-cyan)' }}><Users size={11} />{reports[n.id]}</span> : '—'}</td>
              <td className="px-3 py-2.5 text-xs">{n.type === 'vacancy' ? (n.recruitment_stage || 'Planned') : (n.status || 'active')}</td>
              <td className="px-3 py-2.5">{n.staff_id ? <Link2 size={13} style={{ color: 'var(--color-brand-cyan)' }} /> : <span className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>—</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
