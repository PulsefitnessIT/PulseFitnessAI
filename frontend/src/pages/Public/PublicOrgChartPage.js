/** Public read-only org chart — viewable via a share link (no login). */
import { useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { Network, Loader2, MapPin, Mail, Phone, Wrench } from 'lucide-react';
import { computeLayout, bounds, CARD_W, CARD_H } from '@/pages/LiteDashboard/staffing/orgchart/layout';
import { deptColor, humanize } from '@/pages/LiteDashboard/staffing/orgchart/api';

const initials = (n) => (n || '?').split(' ').filter(Boolean).slice(0, 2).map((p) => p[0]).join('').toUpperCase();

function ROCard({ n, showContact }) {
  const isVac = n.type === 'vacancy';
  const accent = isVac ? '#ea580c' : deptColor(n.department);
  return (
    <div className="absolute rounded-2xl bg-white" style={{
      left: n.x, top: n.y, width: CARD_W, minHeight: CARD_H,
      border: `1.5px ${isVac ? 'dashed' : 'solid'} #e2e8f0`, borderLeft: `4px solid ${accent}`,
      boxShadow: '0 2px 10px rgba(2,12,40,0.08)',
    }}>
      <div className="p-3 flex items-start gap-2.5">
        <div className="flex-shrink-0 rounded-xl flex items-center justify-center text-xs font-bold" style={{ width: 38, height: 38, color: '#fff', background: isVac ? '#fb923c' : accent }}>
          {n.is_engineer ? <Wrench size={16} /> : initials(n.full_name)}
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-[13px] font-bold truncate" style={{ color: '#0f1f3d' }}>{n.full_name}</div>
          <div className="text-[11px] truncate text-slate-500">{humanize(n.job_title) || (isVac ? 'Open role' : '—')}</div>
          {n.department && <div className="mt-1 inline-block text-[9px] font-semibold px-1.5 py-0.5 rounded-full" style={{ background: `${accent}1a`, color: accent }}>{n.department}</div>}
        </div>
      </div>
      <div className="px-3 pb-2 -mt-1 flex flex-wrap gap-x-2.5 gap-y-0.5 text-[10px] text-slate-500">
        {n.site_name && <span className="inline-flex items-center gap-0.5"><MapPin size={9} /> {n.site_name}</span>}
        {showContact && n.email && <span className="inline-flex items-center gap-0.5 truncate" style={{ maxWidth: 120 }}><Mail size={9} /> {n.email}</span>}
        {showContact && n.phone && <span className="inline-flex items-center gap-0.5"><Phone size={9} /> {n.phone}</span>}
        {isVac && n.recruitment_stage && <span className="font-semibold" style={{ color: '#ea580c' }}>{n.recruitment_stage}</span>}
      </div>
    </div>
  );
}

export default function PublicOrgChartPage() {
  const { token } = useParams();
  const wrapRef = useRef(null);
  const [data, setData] = useState(null);
  const [status, setStatus] = useState('loading');
  const [scale, setScale] = useState(1);

  useEffect(() => {
    axios.get(`${process.env.REACT_APP_BACKEND_URL}/api/staffing/orgchart/public/${token}`)
      .then((r) => { setData(r.data); setStatus('ok'); })
      .catch(() => setStatus('gone'));
  }, [token]);

  const laid = useMemo(() => (data ? computeLayout(data.nodes || [], 'top-down') : []), [data]);
  const byId = useMemo(() => Object.fromEntries(laid.map((n) => [n.id, n])), [laid]);
  const b = useMemo(() => bounds(laid), [laid]);

  useEffect(() => {
    if (status !== 'ok' || !wrapRef.current) return;
    const w = b.maxX - b.minX;
    const cw = wrapRef.current.clientWidth - 48;
    setScale(Math.min(1, cw / w || 1));
  }, [status, b]);

  const paths = useMemo(() => laid.map((n) => {
    const m = byId[n.manager_node_id]; if (!m) return null;
    const sx = m.x + CARD_W / 2; const sy = m.y + CARD_H; const ex = n.x + CARD_W / 2; const ey = n.y;
    const midY = (sy + ey) / 2;
    return { id: n.id, d: `M ${sx} ${sy} C ${sx} ${midY}, ${ex} ${midY}, ${ex} ${ey}` };
  }).filter(Boolean), [laid, byId]);

  if (status === 'loading') {
    return <div className="min-h-screen flex items-center justify-center bg-slate-50"><Loader2 className="animate-spin text-slate-400" /></div>;
  }
  if (status === 'gone') {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-slate-50 px-6 text-center" data-testid="public-orgchart-gone">
        <Network size={32} className="text-slate-300 mb-3" />
        <h1 className="text-lg font-bold text-slate-800">This org chart link is no longer available</h1>
        <p className="text-sm text-slate-500 mt-1">The owner may have stopped sharing or generated a new link.</p>
        <a href="/" className="mt-4 text-sm font-semibold" style={{ color: '#19cdff' }}>Go to GymAxis →</a>
      </div>
    );
  }

  const contentW = b.maxX - b.minX; const contentH = b.maxY - b.minY;
  return (
    <div className="min-h-screen bg-slate-50" data-testid="public-orgchart-page">
      <header className="bg-white border-b border-slate-200 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ background: '#0f1f3d' }}><Network size={17} className="text-white" /></div>
          <div>
            <h1 className="text-base font-bold text-slate-900 leading-tight">{data.name}</h1>
            <p className="text-[11px] text-slate-500">Organisation chart · {(data.nodes || []).length} people · read-only</p>
          </div>
        </div>
        <a href="/" className="text-xs font-semibold text-slate-400 hover:text-slate-600">Powered by GymAxis</a>
      </header>

      <div ref={wrapRef} className="overflow-auto p-6" style={{ height: 'calc(100vh - 69px)' }}>
        <div style={{ width: contentW * scale, height: contentH * scale, position: 'relative', margin: '0 auto' }}>
          <div style={{ position: 'absolute', left: 0, top: 0, transform: `translate(${-b.minX}px, ${-b.minY}px) scale(${scale})`, transformOrigin: '0 0' }}>
            <svg style={{ position: 'absolute', left: 0, top: 0, overflow: 'visible', width: 1, height: 1, pointerEvents: 'none' }}>
              {paths.map((p) => <path key={p.id} d={p.d} fill="none" stroke="#94a3b8" strokeWidth={1.6} strokeOpacity={0.6} />)}
            </svg>
            {laid.map((n) => <ROCard key={n.id} n={n} showContact={data.show_contact} />)}
          </div>
        </div>
      </div>
    </div>
  );
}
