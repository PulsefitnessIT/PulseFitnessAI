/** Org Chart Builder — orchestrator (Operations → Staffing → Org Chart).
 *
 * Sub-tabs: Org Chart (canvas) · List View · Vacancies · Import/Export · Settings.
 * Links to existing staff_members; never duplicates them. */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { toPng } from 'html-to-image';
import jsPDF from 'jspdf';
import {
  Network, List, UserPlus, FileUp, Settings as SettingsIcon, Search,
  Loader2, RefreshCw, Plus, Users, Building2, AlertTriangle, X, Sparkles, LayoutTemplate, History, Presentation as PresentIcon, Share2,
} from 'lucide-react';
import { ocApi } from './api';
import { computeLayout } from './layout';
import Canvas from './Canvas';
import ListView from './ListView';
import Vacancies from './Vacancies';
import ImportExport from './ImportExport';
import Settings from './Settings';
import AIPanel from './AIPanel';
import HistoryTab from './HistoryTab';
import Templates from './Templates';
import PresentationMode from './Presentation';
import ShareModal from './ShareModal';
import { AddNodeModal, NodeDrawer, MoveConfirmModal } from './panels';

const STAFF_API = `${process.env.REACT_APP_BACKEND_URL}/api/staffing/staff`;
const SUBTABS = [
  { id: 'chart', label: 'Org Chart', icon: Network },
  { id: 'list', label: 'List View', icon: List },
  { id: 'vacancies', label: 'Vacancies', icon: UserPlus },
  { id: 'ai', label: 'AI Assist', icon: Sparkles },
  { id: 'templates', label: 'Templates', icon: LayoutTemplate },
  { id: 'history', label: 'History', icon: History },
  { id: 'import', label: 'Import / Export', icon: FileUp },
  { id: 'settings', label: 'Settings', icon: SettingsIcon },
];

function StatChip({ label, value, warn }) {
  return (
    <div className="rounded-xl border px-3 py-2 min-w-[88px]" style={{ borderColor: warn && value > 0 ? '#fcd34d' : 'var(--theme-border)', background: warn && value > 0 ? '#fffbeb' : 'transparent' }} data-testid={`orgchart-stat-${label}`}>
      <div className="text-lg font-bold leading-none" style={{ color: warn && value > 0 ? '#b45309' : 'var(--theme-text)' }}>{value}</div>
      <div className="text-[9px] uppercase tracking-wide mt-1" style={{ color: 'var(--theme-text-muted)' }}>{label}</div>
    </div>
  );
}

export default function OrgChartTab() {
  const headers = useMemo(() => ({ Authorization: `Bearer ${localStorage.getItem('token')}` }), []);
  const [loading, setLoading] = useState(true);
  const [charts, setCharts] = useState([]);
  const [chartId, setChartId] = useState(null);
  const [chart, setChart] = useState(null);
  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);
  const [sites, setSites] = useState([]);
  const [insights, setInsights] = useState(null);
  const [staffOptions, setStaffOptions] = useState([]);
  const [sub, setSub] = useState('chart');
  const [search, setSearch] = useState('');
  const [focusId, setFocusId] = useState(null);
  const [presenting, setPresenting] = useState(false);
  const [filter, setFilter] = useState({ department: '', site: '', type: '', flag: '' });
  const [addOpen, setAddOpen] = useState(false);
  const [editNode, setEditNode] = useState(null);
  const [moveData, setMoveData] = useState(null);
  const [sharing, setSharing] = useState(false);

  const byId = useMemo(() => Object.fromEntries(nodes.map((n) => [n.id, n])), [nodes]);
  const departments = useMemo(() => [...new Set(nodes.map((n) => n.department).filter(Boolean))].sort(), [nodes]);

  const loadStaff = useCallback(async () => {
    try {
      const r = await axios.get(STAFF_API, { headers });
      setStaffOptions(r.data.staff || []);
    } catch { /* non-fatal */ }
  }, [headers]);

  const loadChart = useCallback(async (cid) => {
    const data = await ocApi.getChart(cid);
    setChart(data.chart);
    setNodes(data.nodes || []);
    setEdges(data.edges || []);
    setSites(data.sites || []);
    ocApi.insights(cid).then(setInsights).catch(() => {});
  }, []);

  const boot = useCallback(async () => {
    setLoading(true);
    try {
      let { charts: list } = await ocApi.listCharts();
      if (!list.length) {
        const c = await ocApi.createChart({ name: 'Organisation Chart', auto_build: true });
        list = [c];
      }
      setCharts(list);
      const saved = localStorage.getItem('orgchart.activeId');
      const active = list.find((c) => c.id === saved) ? saved : list[0].id;
      setChartId(active);
      await loadChart(active);
      loadStaff();
    } catch (e) {
      toast.error('Could not load org charts');
    } finally { setLoading(false); }
  }, [loadChart, loadStaff]);

  useEffect(() => { boot(); }, [boot]);
  useEffect(() => { if (chartId) localStorage.setItem('orgchart.activeId', chartId); }, [chartId]);

  const reload = useCallback(() => { if (chartId) { loadChart(chartId); loadStaff(); } }, [chartId, loadChart, loadStaff]);

  const switchChart = async (cid) => { setChartId(cid); setLoading(true); await loadChart(cid); setLoading(false); };

  const newChart = async () => {
    const c = await ocApi.createChart({ name: `Chart ${charts.length + 1}`, auto_build: true });
    const { charts: list } = await ocApi.listCharts();
    setCharts(list);
    await switchChart(c.id);
    toast.success('Chart created');
  };

  const syncStaff = async () => {
    const r = await ocApi.syncStaff(chartId);
    await reload();
    toast.success(r.added ? `Added ${r.added} staff` : 'Already up to date');
  };

  // ─── node ops ───
  const createNode = async (body) => { await ocApi.createNode(chartId, body); await reload(); toast.success('Card added'); };
  const updateNode = async (nid, body) => {
    try { const updated = await ocApi.updateNode(chartId, nid, body); setNodes((ns) => ns.map((n) => (n.id === nid ? { ...n, ...updated } : n))); ocApi.insights(chartId).then(setInsights).catch(() => {}); return updated; } catch (e) { toast.error(e?.response?.data?.detail || 'Update failed'); throw e; }
  };
  const moveNode = async (nid, posPatch) => { ocApi.updateNode(chartId, nid, posPatch).catch(() => {}); setNodes((ns) => ns.map((n) => (n.id === nid ? { ...n, ...posPatch } : n))); };
  const deleteNode = async (nid) => { await ocApi.deleteNode(chartId, nid); setEditNode(null); await reload(); toast.success('Card removed'); };

  const requestSetManager = (childId, managerId) => {
    const child = byId[childId]; const mgr = byId[managerId];
    setMoveData({ childId, managerId, childName: child?.full_name, managerName: mgr?.full_name, hasStaffLink: !!child?.staff_id });
  };
  const chooseMove = async (choice) => {
    if (choice === 'cancel') { setMoveData(null); return; }
    const { childId, managerId } = moveData;
    try {
      await updateNode(childId, { manager_node_id: managerId, write_back_staff: choice === 'update' });
      toast.success(choice === 'update' ? 'Reporting line + staff record updated' : 'Reporting line updated');
    } catch { /* handled */ }
    setMoveData(null);
  };

  const autoLayout = async () => {
    const laid = computeLayout(nodes, chart?.settings?.layout || 'vertical');
    setNodes(laid);
    toast.success('Auto-arranged');
    await Promise.all(laid.map((n) => ocApi.updateNode(chartId, n.id, { x: Math.round(n.x), y: Math.round(n.y) }).catch(() => {})));
  };

  const saveSettings = async (settings) => { const r = await ocApi.updateChart(chartId, { settings }); setChart(r); };
  const renameChart = async (name) => { const r = await ocApi.updateChart(chartId, { name }); setChart(r); setCharts((cs) => cs.map((c) => (c.id === chartId ? { ...c, name } : c))); toast.success('Renamed'); };
  const deleteChart = async () => {
    await ocApi.deleteChart(chartId);
    const { charts: list } = await ocApi.listCharts();
    if (!list.length) { await boot(); } else { setCharts(list); await switchChart(list[0].id); }
    setSub('chart');
    toast.success('Chart deleted');
  };

  // ─── export ───
  const captureCanvas = async () => {
    const el = document.querySelector('[data-testid="orgchart-canvas"]');
    if (!el) throw new Error('no canvas');
    return toPng(el, { backgroundColor: '#fbfcfe', pixelRatio: 2 });
  };
  const exportImage = async () => {
    try { const url = await captureCanvas(); const a = document.createElement('a'); a.href = url; a.download = `${chart?.name || 'org-chart'}.png`; a.click(); } catch { toast.error('Export failed'); }
  };
  const exportPdf = async () => {
    try {
      const url = await captureCanvas();
      const img = new Image(); img.src = url;
      await new Promise((res) => { img.onload = res; });
      const pdf = new jsPDF({ orientation: 'landscape', unit: 'pt', format: 'a4' });
      const pw = pdf.internal.pageSize.getWidth(); const ph = pdf.internal.pageSize.getHeight();
      pdf.setFontSize(14); pdf.text(chart?.name || 'Organisation Chart', 30, 30);
      pdf.setFontSize(8); pdf.text(new Date().toLocaleString(), 30, 44);
      const ratio = Math.min((pw - 60) / img.width, (ph - 80) / img.height);
      pdf.addImage(url, 'PNG', 30, 60, img.width * ratio, img.height * ratio);
      pdf.save(`${chart?.name || 'org-chart'}.pdf`);
    } catch { toast.error('Export failed'); }
  };

  // ─── filter / search ───
  const matchesFilter = useCallback((n) => {
    if (filter.department && n.department !== filter.department) return false;
    if (filter.site && n.site_id !== filter.site) return false;
    if (filter.type && n.type !== filter.type) return false;
    if (filter.flag === 'vacancies' && n.type !== 'vacancy') return false;
    if (filter.flag === 'engineers' && !n.is_engineer) return false;
    if (filter.flag === 'no_manager' && (n.manager_node_id || n.type === 'vacancy')) return false;
    if (filter.flag === 'no_site' && n.site_id) return false;
    return true;
  }, [filter]);
  const dimmedIds = useMemo(() => {
    const set = new Set();
    const active = filter.department || filter.site || filter.type || filter.flag;
    if (active) nodes.forEach((n) => { if (!matchesFilter(n)) set.add(n.id); });
    return set;
  }, [nodes, filter, matchesFilter]);

  const runSearch = (e) => {
    e?.preventDefault();
    const q = search.trim().toLowerCase();
    if (!q) return;
    const hit = nodes.find((n) => [n.full_name, n.job_title, n.department, n.site_name, n.email].some((f) => (f || '').toLowerCase().includes(q)));
    if (hit) { setSub('chart'); setFocusId(null); setTimeout(() => setFocusId(hit.id), 30); }
    else toast.error('No match found');
  };

  if (loading) {
    return <div className="py-16 flex items-center justify-center gap-2 text-sm" style={{ color: 'var(--theme-text-muted)' }} data-testid="orgchart-loading"><Loader2 size={16} className="animate-spin" /> Loading org chart…</div>;
  }

  return (
    <div className="space-y-4" data-testid="orgchart-tab">
      {/* chart picker + actions */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <select value={chartId || ''} onChange={(e) => switchChart(e.target.value)} className="px-3 py-2 rounded-lg text-sm font-semibold border outline-none" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-bg,#fff)', color: 'var(--theme-text)' }} data-testid="orgchart-chart-select">
            {charts.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <button onClick={newChart} title="New chart" className="w-9 h-9 rounded-lg inline-flex items-center justify-center border" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }} data-testid="orgchart-new-chart"><Plus size={16} /></button>
        </div>
        <div className="flex items-center gap-2">
          <form onSubmit={runSearch} className="relative">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2" style={{ color: 'var(--theme-text-muted)' }} />
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search people…" className="pl-8 pr-3 py-2 rounded-lg text-sm border outline-none w-44" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-bg,#fff)', color: 'var(--theme-text)' }} data-testid="orgchart-search" />
          </form>
          <button onClick={() => setSharing(true)} className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold border" style={chart?.is_public ? { borderColor: '#16a34a', color: '#16a34a' } : { borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="orgchart-share"><Share2 size={13} /> {chart?.is_public ? 'Shared' : 'Share'}</button>
          <button onClick={() => setPresenting(true)} className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold border" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="orgchart-present"><PresentIcon size={13} /> Present</button>
          <button onClick={syncStaff} className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold border" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="orgchart-sync"><RefreshCw size={13} /> Sync staff</button>
        </div>
      </div>

      {/* insights */}
      {insights && (
        <div className="flex flex-wrap gap-2" data-testid="orgchart-insights">
          <StatChip label="People" value={insights.total_people} />
          <StatChip label="Managers" value={insights.total_managers} />
          <StatChip label="Engineers" value={insights.total_engineers} />
          <StatChip label="Open roles" value={insights.open_vacancies} />
          <StatChip label="Departments" value={insights.departments} />
          <StatChip label="Avg reports" value={insights.avg_direct_reports} />
          <StatChip label="No manager" value={insights.staff_without_manager} warn />
          <StatChip label="No site" value={insights.staff_without_site} warn />
        </div>
      )}

      {/* sub-nav */}
      <div className="flex items-center gap-1.5 flex-wrap border-b pb-2" style={{ borderColor: 'var(--theme-border)' }}>
        {SUBTABS.map(({ id, label, icon: Icon }) => (
          <button key={id} onClick={() => setSub(id)} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors" style={sub === id ? { background: 'rgba(25,205,255,0.12)', color: 'var(--color-brand-cyan)' } : { color: 'var(--theme-text-muted)' }} data-testid={`orgchart-subtab-${id}`}>
            <Icon size={13} /> {label}
          </button>
        ))}
      </div>

      {/* filters (chart + list only) */}
      {(sub === 'chart' || sub === 'list') && (
        <div className="flex flex-wrap items-center gap-2" data-testid="orgchart-filters">
          <select value={filter.department} onChange={(e) => setFilter({ ...filter, department: e.target.value })} className="px-2 py-1.5 rounded-lg text-xs border outline-none" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-bg,#fff)', color: 'var(--theme-text)' }} data-testid="orgchart-filter-dept">
            <option value="">All departments</option>
            {departments.map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
          {!!sites.length && (
            <select value={filter.site} onChange={(e) => setFilter({ ...filter, site: e.target.value })} className="px-2 py-1.5 rounded-lg text-xs border outline-none" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-bg,#fff)', color: 'var(--theme-text)' }} data-testid="orgchart-filter-site">
              <option value="">All sites</option>
              {sites.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          )}
          <select value={filter.flag} onChange={(e) => setFilter({ ...filter, flag: e.target.value })} className="px-2 py-1.5 rounded-lg text-xs border outline-none" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-bg,#fff)', color: 'var(--theme-text)' }} data-testid="orgchart-filter-flag">
            <option value="">Everyone</option>
            <option value="vacancies">Vacancies only</option>
            <option value="engineers">Engineers only</option>
            <option value="no_manager">Missing manager</option>
            <option value="no_site">Missing site</option>
          </select>
          {(filter.department || filter.site || filter.type || filter.flag) && (
            <button onClick={() => setFilter({ department: '', site: '', type: '', flag: '' })} className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-1.5 rounded-lg" style={{ color: 'var(--color-brand-cyan)' }} data-testid="orgchart-filter-clear"><X size={12} /> Clear</button>
          )}
        </div>
      )}

      {/* content */}
      {sub === 'chart' && (
        <Canvas
          nodes={nodes}
          edges={edges}
          settings={chart?.settings}
          dimmedIds={dimmedIds}
          focusId={focusId}
          onMoveNode={moveNode}
          onRequestSetManager={requestSetManager}
          onOpenNode={(n) => setEditNode(n)}
          onAutoLayout={autoLayout}
          onAddCard={() => setAddOpen(true)}
        />
      )}
      {sub === 'list' && <ListView nodes={nodes.filter(matchesFilter)} byId={byId} onOpen={(n) => setEditNode(n)} />}
      {sub === 'vacancies' && <Vacancies nodes={nodes} byId={byId} onOpen={(n) => setEditNode(n)} onAdd={() => setAddOpen(true)} onUpdate={updateNode} />}
      {sub === 'ai' && <AIPanel chartId={chartId} onImported={reload} />}
      {sub === 'templates' && <Templates chartId={chartId} onApplied={reload} />}
      {sub === 'history' && <HistoryTab chartId={chartId} onRestored={reload} />}
      {sub === 'import' && <ImportExport chartId={chartId} onImported={reload} onExportImage={exportImage} onExportPdf={exportPdf} />}
      {sub === 'settings' && chart && <Settings chart={chart} onSave={saveSettings} onRename={renameChart} onDelete={deleteChart} />}

      {/* modals */}
      <AddNodeModal open={addOpen} onClose={() => setAddOpen(false)} onCreate={createNode} staffOptions={staffOptions.filter((s) => !nodes.some((n) => n.staff_id === s.id))} sites={sites} departments={departments} />
      <NodeDrawer node={editNode} onClose={() => setEditNode(null)} onSave={updateNode} onDelete={deleteNode} sites={sites} nodes={nodes} departments={departments} chartId={chartId} edges={edges} onEdgesChanged={reload} />
      <MoveConfirmModal data={moveData} onChoose={chooseMove} onClose={() => setMoveData(null)} />
      {presenting && <PresentationMode nodes={nodes} byId={byId} onClose={() => setPresenting(false)} />}
      {sharing && chart && <ShareModal chart={chart} onClose={() => setSharing(false)} onChanged={reload} />}
    </div>
  );
}
