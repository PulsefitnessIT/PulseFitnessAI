/**
 * Pulse Fitness AI — Comms Centre.
 *
 * The central, merged campaign system. One shared record set
 * (`/api/comms/campaigns`) surfaced through module-context views:
 *   • All  • Marketing  • Memberships (member emails)  • CRM & B2B
 * Each view is a filter into the SAME campaigns — no duplicate records.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  Megaphone, Mail, Users, Briefcase, Plus, Send, Copy, Archive, Pencil,
  BarChart3, MousePointerClick, Eye, X,
} from 'lucide-react';

import { useAuth } from '@/App';
import Navbar from '@/components/shared/Navbar';
import ModuleSwitcher from '@/components/shared/ModuleSwitcher';
import PillTabBar from '@/components/shared/PillTabBar';
import EmailBuilder from './EmailBuilder';

const CYAN = '#19CDFF';

const VIEWS = [
  { id: 'all', label: 'All campaigns', icon: Megaphone, module: 'all' },
  { id: 'marketing', label: 'Marketing', icon: Mail, module: 'marketing' },
  { id: 'memberships', label: 'Member emails', icon: Users, module: 'memberships' },
  { id: 'crm', label: 'CRM & B2B', icon: Briefcase, module: 'crm' },
];

const STATUS_STYLE = {
  draft: 'bg-slate-100 text-slate-600',
  in_review: 'bg-amber-100 text-amber-700',
  changes_requested: 'bg-orange-100 text-orange-700',
  approved: 'bg-blue-100 text-blue-700',
  scheduled: 'bg-violet-100 text-violet-700',
  sending: 'bg-cyan-100 text-cyan-700',
  sent: 'bg-emerald-100 text-emerald-700',
  paused: 'bg-yellow-100 text-yellow-700',
  cancelled: 'bg-rose-100 text-rose-700',
  archived: 'bg-slate-100 text-slate-400',
};
const MODULE_BADGE = {
  marketing: 'bg-fuchsia-50 text-fuchsia-700',
  memberships: 'bg-cyan-50 text-cyan-700',
  crm: 'bg-indigo-50 text-indigo-700',
};

function StatCard({ label, value, icon: Icon, suffix }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4" data-testid={`stat-${label.toLowerCase().replace(/\s+/g, '-')}`}>
      <div className="flex items-center gap-2 text-slate-400 mb-1"><Icon size={15} /><span className="text-xs font-bold uppercase tracking-wide">{label}</span></div>
      <p className="text-2xl font-extrabold text-slate-900 pulse-font-heading">{value}{suffix}</p>
    </div>
  );
}

export default function CommsCentre() {
  const { user, logout, theme, toggleTheme } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const API = process.env.REACT_APP_BACKEND_URL;
  const token = useMemo(() => localStorage.getItem('token'), []);
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);

  const initialView = (() => {
    const sp = new URLSearchParams(location.search);
    const v = sp.get('view');
    return VIEWS.some((x) => x.id === v) ? v : 'all';
  })();
  const [view, setView] = useState(initialView);
  const [meta, setMeta] = useState(null);
  const [dash, setDash] = useState(null);
  const [campaigns, setCampaigns] = useState([]);
  const [statusFilter, setStatusFilter] = useState('');
  const [q, setQ] = useState('');
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [editing, setEditing] = useState(null);

  const moduleParam = VIEWS.find((v) => v.id === view)?.module || 'all';

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [d, c] = await Promise.all([
        axios.get(`${API}/api/comms/dashboard`, { params: { module: moduleParam }, headers }),
        axios.get(`${API}/api/comms/campaigns`, { params: { module: moduleParam, status: statusFilter || undefined, q: q || undefined }, headers }),
      ]);
      setDash(d.data);
      setCampaigns(c.data.campaigns || []);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to load Comms Centre');
    } finally { setLoading(false); }
  }, [API, headers, moduleParam, statusFilter, q]);

  useEffect(() => { axios.get(`${API}/api/comms/meta`, { headers }).then((r) => setMeta(r.data)).catch(() => {}); }, [API, headers]);
  useEffect(() => { load(); }, [load]);

  const typeLabel = (id) => meta?.campaign_types.find((t) => t.id === id)?.label || id;

  const duplicate = async (c) => {
    try { await axios.post(`${API}/api/comms/campaigns/${c.id}/duplicate`, {}, { headers }); toast.success('Campaign duplicated'); load(); }
    catch { toast.error('Duplicate failed'); }
  };
  const archive = async (c) => {
    try { await axios.delete(`${API}/api/comms/campaigns/${c.id}`, { headers }); toast.success('Archived'); load(); }
    catch { toast.error('Archive failed'); }
  };

  if (!user) { navigate('/'); return null; }

  return (
    <div className="min-h-screen" style={{ background: 'var(--theme-bg)', color: 'var(--theme-text)' }} data-testid="comms-centre">
      <Navbar user={user} logout={logout} theme={theme} toggleTheme={toggleTheme} />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-24 pb-24 md:pb-8 module-fade-in">
        <div className="mb-6">
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div className="min-w-0">
              <h1 className="text-3xl sm:text-4xl tracking-tight font-bold mb-1 pulse-font-heading leading-tight" style={{ color: 'var(--theme-text)' }}>
                Comms <span style={{ color: CYAN }}>Centre</span>
              </h1>
              <p className="text-sm text-slate-500">One connected campaign system across Marketing, Memberships and CRM.</p>
            </div>
            <ModuleSwitcher user={user} current="comms" />
          </div>
        </div>

        {/* Context views */}
        <PillTabBar activeId={view} testId="comms-views" ariaLabel="Comms views" className="mb-5">
          <div className="inline-flex items-center gap-1.5 p-1 rounded-full border border-slate-200 bg-white">
            {VIEWS.map((v) => {
              const Icon = v.icon;
              const on = view === v.id;
              return (
                <button
                  key={v.id}
                  data-pill-id={v.id}
                  data-testid={`comms-view-${v.id}`}
                  onClick={() => { setView(v.id); setStatusFilter(''); navigate(`/comms?view=${v.id}`, { replace: true }); }}
                  className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-[12px] font-bold whitespace-nowrap transition-all ${on ? 'text-[#03212b]' : 'text-slate-500 hover:text-slate-800'}`}
                  style={on ? { background: CYAN } : {}}
                >
                  <Icon size={13} />{v.label}
                </button>
              );
            })}
          </div>
        </PillTabBar>

        {/* Dashboard */}
        {dash && (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
            <StatCard label="Campaigns" value={dash.total_campaigns} icon={Megaphone} />
            <StatCard label="Emails sent" value={dash.totals.sent} icon={Send} />
            <StatCard label="Open rate" value={dash.open_rate} suffix="%" icon={Eye} />
            <StatCard label="Click rate" value={dash.click_rate} suffix="%" icon={MousePointerClick} />
          </div>
        )}

        {/* Toolbar */}
        <div className="flex items-center justify-between gap-3 flex-wrap mb-3">
          <div className="flex items-center gap-2">
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search campaigns…"
              className="px-3 py-2 rounded-full border border-slate-200 text-sm bg-white focus:border-[#19CDFF] focus:outline-none"
              data-testid="comms-search"
            />
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="px-3 py-2 rounded-full border border-slate-200 text-sm bg-white" data-testid="comms-status-filter">
              <option value="">All statuses</option>
              {(meta?.statuses || []).map((s) => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
            </select>
          </div>
          <button onClick={() => setShowCreate(true)} className="flex items-center gap-1.5 px-4 py-2 rounded-full text-sm font-bold text-[#03212b]" style={{ background: CYAN }} data-testid="comms-create-btn">
            <Plus size={15} />New campaign
          </button>
        </div>

        {/* List */}
        <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden" data-testid="comms-campaign-list">
          {loading ? (
            <div className="p-10 text-center text-slate-400 text-sm">Loading…</div>
          ) : campaigns.length === 0 ? (
            <div className="p-12 text-center">
              <Megaphone size={28} className="mx-auto text-slate-300 mb-2" />
              <p className="text-slate-500 font-semibold">No campaigns yet</p>
              <p className="text-sm text-slate-400 mb-4">Create your first {view === 'all' ? '' : VIEWS.find((v) => v.id === view)?.label.toLowerCase()} campaign.</p>
              <button onClick={() => setShowCreate(true)} className="px-4 py-2 rounded-full text-sm font-bold text-[#03212b]" style={{ background: CYAN }} data-testid="comms-empty-create">Create campaign</button>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wide">
                <tr>
                  <th className="text-left font-bold px-4 py-3">Campaign</th>
                  <th className="text-left font-bold px-4 py-3 hidden md:table-cell">Type</th>
                  <th className="text-left font-bold px-4 py-3">Status</th>
                  <th className="text-left font-bold px-4 py-3 hidden sm:table-cell">Sent</th>
                  <th className="text-right font-bold px-4 py-3">Actions</th>
                </tr>
              </thead>
              <tbody>
                {campaigns.map((c) => (
                  <tr key={c.id} className="border-t border-slate-100 hover:bg-slate-50/60" data-testid={`campaign-row-${c.id}`}>
                    <td className="px-4 py-3">
                      <div className="font-semibold text-slate-900">{c.name}</div>
                      <span className={`inline-block mt-1 text-[10px] font-bold px-2 py-0.5 rounded-full ${MODULE_BADGE[c.related_module] || 'bg-slate-100 text-slate-600'}`}>{c.related_module}</span>
                    </td>
                    <td className="px-4 py-3 hidden md:table-cell text-slate-600">{typeLabel(c.campaign_type)}</td>
                    <td className="px-4 py-3"><span className={`text-[11px] font-bold px-2 py-1 rounded-full ${STATUS_STYLE[c.status] || 'bg-slate-100'}`}>{(c.status || 'draft').replace(/_/g, ' ')}</span></td>
                    <td className="px-4 py-3 hidden sm:table-cell text-slate-600">{c.metrics?.sent || 0}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-1">
                        <button onClick={() => setEditing(c)} title="Edit" className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-500" data-testid={`campaign-edit-${c.id}`}><Pencil size={15} /></button>
                        <button onClick={() => duplicate(c)} title="Duplicate" className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-500" data-testid={`campaign-dup-${c.id}`}><Copy size={15} /></button>
                        <button onClick={() => archive(c)} title="Archive" className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400" data-testid={`campaign-archive-${c.id}`}><Archive size={15} /></button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </main>

      {showCreate && meta && (
        <CreateModal
          API={API} headers={headers} meta={meta} defaultModule={moduleParam}
          onClose={() => setShowCreate(false)}
          onCreated={(c) => { setShowCreate(false); load(); setEditing(c); }}
        />
      )}

      {editing && (
        <EmailBuilder
          campaign={editing} API={API} headers={headers}
          onClose={() => { setEditing(null); load(); }}
          onSaved={(c) => setEditing(c)}
        />
      )}
    </div>
  );
}

function CreateModal({ API, headers, meta, defaultModule, onClose, onCreated }) {
  const [name, setName] = useState('');
  const types = meta.campaign_types.filter((t) => defaultModule === 'all' || t.module === defaultModule);
  const [type, setType] = useState(types[0]?.id || 'regular');
  const [goal, setGoal] = useState('');
  const [busy, setBusy] = useState(false);

  const grouped = useMemo(() => {
    const g = {};
    types.forEach((t) => { (g[t.group] = g[t.group] || []).push(t); });
    return g;
  }, [types]);

  const create = async () => {
    if (!name.trim()) { toast.error('Give your campaign a name'); return; }
    setBusy(true);
    try {
      const r = await axios.post(`${API}/api/comms/campaigns`, { name, campaign_type: type, conversion_goal: goal }, { headers });
      toast.success('Campaign created');
      onCreated(r.data.campaign);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Create failed');
    } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-[150] bg-black/40 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl p-6 w-full max-w-lg" onClick={(e) => e.stopPropagation()} data-testid="comms-create-modal">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-bold text-xl text-slate-900 pulse-font-heading">New campaign</h3>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400"><X size={18} /></button>
        </div>
        <label className="block text-[11px] uppercase tracking-wider font-bold text-slate-400 mb-1">Name</label>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. October member newsletter" className="w-full px-4 py-3 rounded-xl border border-slate-200 mb-4 focus:border-[#19CDFF] focus:outline-none" data-testid="create-name" autoFocus />
        <label className="block text-[11px] uppercase tracking-wider font-bold text-slate-400 mb-1">Campaign type</label>
        <select value={type} onChange={(e) => setType(e.target.value)} className="w-full px-4 py-3 rounded-xl border border-slate-200 mb-4 bg-white" data-testid="create-type">
          {Object.entries(grouped).map(([g, items]) => (
            <optgroup key={g} label={g}>
              {items.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
            </optgroup>
          ))}
        </select>
        <label className="block text-[11px] uppercase tracking-wider font-bold text-slate-400 mb-1">Conversion goal (optional)</label>
        <input value={goal} onChange={(e) => setGoal(e.target.value)} placeholder="e.g. renewals, bookings, quote approvals" className="w-full px-4 py-3 rounded-xl border border-slate-200 mb-5 focus:border-[#19CDFF] focus:outline-none" data-testid="create-goal" />
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 rounded-full text-sm font-semibold text-slate-600 hover:bg-slate-100">Cancel</button>
          <button onClick={create} disabled={busy} className="px-5 py-2 rounded-full text-sm font-bold text-[#03212b] disabled:opacity-50" style={{ background: CYAN }} data-testid="create-confirm">{busy ? 'Creating…' : 'Create & build'}</button>
        </div>
      </div>
    </div>
  );
}
