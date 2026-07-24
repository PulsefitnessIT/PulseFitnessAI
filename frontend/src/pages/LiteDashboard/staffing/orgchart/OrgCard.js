/** A single org-chart card (person / vacancy / placeholder / contractor). */
import { Briefcase, MapPin, Mail, Phone, Users, Wrench, UserX, UserPlus, Pencil } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { CARD_W, CARD_H } from './layout';
import { deptColor, humanize } from './api';

const TYPE_META = {
  staff: { icon: Users, label: 'Staff' },
  contractor: { icon: Briefcase, label: 'Contractor' },
  vacancy: { icon: UserPlus, label: 'Open role' },
  placeholder: { icon: UserX, label: 'Placeholder' },
};

function initials(name) {
  return (name || '?').split(' ').filter(Boolean).slice(0, 2).map((p) => p[0]).join('').toUpperCase();
}

export default function OrgCard({
  node, toggles, reportsCount, selected, dragging, onPointerDown, onOpen,
}) {
  const { t } = useTranslation();
  const isVacancy = node.type === 'vacancy';
  const isPlaceholder = node.type === 'placeholder';
  const Meta = TYPE_META[node.type] || TYPE_META.staff;
  const accent = isVacancy ? '#ea580c' : deptColor(node.department);
  const dashed = isVacancy || isPlaceholder;

  return (
    <div
      className="absolute select-none rounded-2xl"
      style={{
        left: node.x, top: node.y, width: CARD_W, minHeight: CARD_H,
        cursor: dragging ? 'grabbing' : 'grab',
        background: 'var(--theme-surface, #fff)',
        border: `1.5px ${dashed ? 'dashed' : 'solid'} ${selected ? 'var(--color-brand-cyan, #19cdff)' : 'var(--theme-border, #e2e8f0)'}`,
        borderLeft: `4px solid ${accent}`,
        boxShadow: selected ? '0 8px 28px rgba(2,12,40,0.18)' : '0 2px 10px rgba(2,12,40,0.08)',
        transition: dragging ? 'none' : 'box-shadow .15s, border-color .15s',
        zIndex: selected ? 20 : 10,
      }}
      onPointerDown={onPointerDown}
      onDoubleClick={() => onOpen(node)}
      data-testid={`orgcard-${node.id}`}
      data-orgcard="1"
      data-node-id={node.id}
    >
      <button
        type="button"
        onPointerDown={(e) => e.stopPropagation()}
        onClick={(e) => { e.stopPropagation(); onOpen(node); }}
        className="absolute top-1.5 right-1.5 z-10 w-6 h-6 rounded-md inline-flex items-center justify-center"
        style={{ background: 'rgba(2,12,40,0.04)', color: 'var(--theme-text-muted, #64748b)' }}
        title="Edit card"
        data-testid={`orgcard-open-${node.id}`}      >
        <Pencil size={12} />
      </button>
      <div className="p-3 pr-9 flex items-start gap-2.5">
        {toggles.photo && (
          <div
            className="flex-shrink-0 rounded-xl flex items-center justify-center text-xs font-bold"
            style={{
              width: 38, height: 38, color: '#fff',
              background: isVacancy ? '#fb923c' : accent,
            }}
          >
            {node.is_engineer ? <Wrench size={16} /> : initials(node.full_name)}
          </div>
        )}
        <div className="min-w-0 flex-1">
          <div className="text-[13px] font-bold truncate pulse-font-heading" style={{ color: 'var(--theme-text, #0f1f3d)' }} title={node.full_name}>
            {node.full_name}
          </div>
          <div className="text-[11px] truncate" style={{ color: 'var(--theme-text-muted, #64748b)' }} title={humanize(node.job_title)}>
            {humanize(node.job_title) || (isVacancy ? t('orgchart.open_role', 'Open role') : '—')}
          </div>
          {toggles.department && node.department && (
            <div className="mt-1 inline-flex items-center gap-1 text-[9px] font-semibold px-1.5 py-0.5 rounded-full"
              style={{ background: `${accent}1a`, color: accent }}>
              {node.department}
            </div>
          )}
        </div>
        <Meta.icon size={13} style={{ color: 'var(--theme-text-muted, #94a3b8)', flexShrink: 0 }} />
      </div>

      <div className="px-3 pb-2 -mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-0.5 text-[10px]" style={{ color: 'var(--theme-text-muted, #64748b)' }}>
        {toggles.site && node.site_name && (
          <span className="inline-flex items-center gap-0.5 truncate" style={{ maxWidth: 90 }}><MapPin size={9} /> {node.site_name}</span>
        )}
        {toggles.email && node.email && (
          <span className="inline-flex items-center gap-0.5 truncate" style={{ maxWidth: 110 }}><Mail size={9} /> {node.email}</span>
        )}
        {toggles.phone && node.phone && (
          <span className="inline-flex items-center gap-0.5"><Phone size={9} /> {node.phone}</span>
        )}
        {toggles.employment_type && node.employment_type && (
          <span>{humanize(node.employment_type)}</span>
        )}
        {toggles.reports_count && reportsCount > 0 && (
          <span className="inline-flex items-center gap-0.5 font-semibold" style={{ color: accent }}><Users size={9} /> {reportsCount}</span>
        )}
        {isVacancy && node.recruitment_stage && (
          <span className="font-semibold" style={{ color: '#ea580c' }}>{node.recruitment_stage}</span>
        )}
      </div>
    </div>
  );
}
