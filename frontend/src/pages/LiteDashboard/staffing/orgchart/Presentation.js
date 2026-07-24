/** Org Chart — presentation mode (clean, full-screen, section-by-section). */
import { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { X, ChevronLeft, ChevronRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { deptColor, humanize } from './api';

function PCard({ n }) {
  const { t } = useTranslation();
  const accent = n.type === 'vacancy' ? '#fb923c' : deptColor(n.department);
  return (
    <div className="rounded-2xl px-4 py-3 min-w-[180px]" style={{ background: 'rgba(255,255,255,0.06)', borderLeft: `4px solid ${accent}`, backdropFilter: 'blur(8px)' }}>
      <div className="text-sm font-bold" style={{ color: '#ffffff' }}>{n.full_name}</div>
      <div className="text-xs" style={{ color: 'rgba(255,255,255,0.65)' }}>{humanize(n.job_title) || (n.type === 'vacancy' ? t('orgchart.open_role', 'Open role') : '')}</div>
      {n.department && <div className="text-[10px] mt-1 font-semibold" style={{ color: accent }}>{n.department}</div>}
    </div>
  );
}

export default function Presentation({ nodes, byId, onClose }) {
  const { t } = useTranslation();
  const [i, setI] = useState(0);

  const slides = useMemo(() => {
    const roots = nodes.filter((n) => !n.manager_node_id);
    const depts = [...new Set(nodes.map((n) => n.department).filter(Boolean))].sort();
    const vacancies = nodes.filter((n) => n.type === 'vacancy');
    const out = [{ title: t('orgchart.present_org', 'Organisation'), subtitle: t('orgchart.present_people_depts', '{{people}} people · {{depts}} departments', { people: nodes.length, depts: depts.length }), nodes: roots }];
    depts.forEach((d) => out.push({ title: d, subtitle: t('orgchart.present_department', 'Department'), nodes: nodes.filter((n) => n.department === d) }));
    if (vacancies.length) out.push({ title: t('orgchart.present_open_roles', 'Open roles'), subtitle: t('orgchart.present_vacancies', '{{count}} vacancies', { count: vacancies.length }), nodes: vacancies });
    return out;
  }, [nodes, t]);

  useEffect(() => {
    const h = (e) => {
      if (e.key === 'Escape') onClose();
      if (e.key === 'ArrowRight') setI((x) => Math.min(slides.length - 1, x + 1));
      if (e.key === 'ArrowLeft') setI((x) => Math.max(0, x - 1));
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [slides.length, onClose]);

  const slide = slides[Math.min(i, slides.length - 1)];

  return createPortal(
    <div className="fixed inset-0 z-[2000] flex flex-col" style={{ background: 'linear-gradient(160deg, #0a1530 0%, #0f1f3d 100%)' }} data-testid="orgchart-presentation">
      <div className="flex items-center justify-between px-8 py-5">
        <div>
          <div className="text-2xl font-bold pulse-font-heading" style={{ color: '#ffffff' }}>{slide?.title}</div>
          <div className="text-sm" style={{ color: 'rgba(255,255,255,0.55)' }}>{slide?.subtitle}</div>
        </div>
        <button onClick={onClose} className="w-10 h-10 rounded-xl inline-flex items-center justify-center" style={{ background: 'rgba(255,255,255,0.08)', color: 'rgba(255,255,255,0.8)' }} data-testid="orgchart-present-close"><X size={20} /></button>
      </div>

      <div className="flex-1 overflow-auto px-8 pb-8">
        <div className="flex flex-wrap gap-3 content-start">
          {(slide?.nodes || []).map((n) => <PCard key={n.id} n={n} />)}
          {!slide?.nodes?.length && <div className="text-sm" style={{ color: 'rgba(255,255,255,0.45)' }}>{t('orgchart.present_no_cards', 'No cards in this section.')}</div>}
        </div>
      </div>

      <div className="flex items-center justify-center gap-4 py-5">
        <button onClick={() => setI((x) => Math.max(0, x - 1))} disabled={i === 0} className="w-10 h-10 rounded-full inline-flex items-center justify-center disabled:opacity-30" style={{ background: 'rgba(255,255,255,0.1)', color: '#ffffff' }} data-testid="orgchart-present-prev"><ChevronLeft size={20} /></button>
        <div className="flex gap-1.5">
          {slides.map((_, idx) => <span key={idx} className="w-2 h-2 rounded-full" style={{ background: idx === i ? 'var(--color-brand-cyan, #19cdff)' : 'rgba(255,255,255,0.25)' }} />)}
        </div>
        <button onClick={() => setI((x) => Math.min(slides.length - 1, x + 1))} disabled={i === slides.length - 1} className="w-10 h-10 rounded-full inline-flex items-center justify-center disabled:opacity-30" style={{ background: 'rgba(255,255,255,0.1)', color: '#ffffff' }} data-testid="orgchart-present-next"><ChevronRight size={20} /></button>
      </div>
    </div>, document.body,
  );
}
