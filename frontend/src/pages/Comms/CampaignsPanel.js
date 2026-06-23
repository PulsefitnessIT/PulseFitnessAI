/**
 * CampaignsPanel — the shared Comms campaign surface, themed with the
 * platform design tokens so it looks identical whether it's mounted as the
 * Comms Centre module, the Memberships → Emails tab, or the CRM →
 * Communications view. Pass a fixed `module` to scope it to that context;
 * all three read the SAME `/api/comms/campaigns` records.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import {
  Megaphone, Send, Copy, Archive, Pencil, Plus, Eye, MousePointerClick, X, BarChart3,
} from 'lucide-react';
import EmailBuilder from './EmailBuilder';
import CampaignAnalytics from './CampaignAnalytics';

const STATUS_STYLE = {
  draft: 'bg-slate-500/15 text-slate-500',
  in_review: 'bg-amber-500/15 text-amber-600',
  changes_requested: 'bg-orange-500/15 text-orange-600',
  approved: 'bg-blue-500/15 text-blue-600',
  scheduled: 'bg-violet-500/15 text-violet-600',
  sending: 'bg-cyan-500/15 text-cyan-600',
  sent: 'bg-emerald-500/15 text-emerald-600',
  paused: 'bg-yellow-500/15 text-yellow-700',
  cancelled: 'bg-rose-500/15 text-rose-600',
  archived: 'bg-slate-500/10 text-slate-400',
};
const MODULE_BADGE = {
  marketing: 'bg-fuchsia-500/12 text-fuchsia-600',
  memberships: 'bg-cyan-500/12 text-cyan-700',
  crm: 'bg-indigo-500/12 text-indigo-600',
};

function StatCard({ label, value, icon: Icon, suffix }) {
  return (
    <div
      className="rounded-2xl p-4 border"
      style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}
      data-testid={`stat-${label.toLowerCase().replace(/\s+/g, '-')}`}
    >
      <div className="flex items-center gap-2 mb-1" style={{ color: 'var(--theme-text-muted)' }}>
        <Icon size={15} /><span className="text-xs font-bold uppercase tracking-wide">{label}</span>
      </div>
      <p className="text-2xl font-extrabold pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{value}{suffix}</p>
    </div>
  );
}

export default function CampaignsPanel({ API, headers, module = 'all', testIdPrefix = 'comms' }) {
  // Callers pass either a bare backend URL (Comms Centre / CRM) or the
  // useAuth().API which already includes "/api" (Memberships). Normalise so
  // we always hit "<root>/api/comms/*" exactly once.
  const apiRoot = useMemo(() => (API || process.env.REACT_APP_BACKEND_URL || '').replace(/\/api\/?$/, ''), [API]);
  const [meta, setMeta] = useState(null);
  const [dash, setDash] = useState(null);
  const [campaigns, setCampaigns] = useState([]);
  const [statusFilter, setStatusFilter] = useState('');
  const [q, setQ] = useState('');
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [editing, setEditing] = useState(null);
  const [analytics, setAnalytics] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [d, c] = await Promise.all([
        axios.get(`${apiRoot}/api/comms/dashboard`, { params: { module }, headers }),
        axios.get(`${apiRoot}/api/comms/campaigns`, { params: { module, status: statusFilter || undefined, q: q || undefined }, headers }),
      ]);
      setDash(d.data);
      setCampaigns(c.data.campaigns || []);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to load campaigns');
    } finally { setLoading(false); }
  }, [apiRoot, headers, module, statusFilter, q]);

  useEffect(() => { axios.get(`${apiRoot}/api/comms/meta`, { headers }).then((r) => setMeta(r.data)).catch(() => {}); }, [apiRoot, headers]);
  useEffect(() => { load(); }, [load]);

  const typeLabel = (id) => meta?.campaign_types.find((t) => t.id === id)?.label || id;

  const duplicate = async (c) => {
    try { await axios.post(`${apiRoot}/api/comms/campaigns/${c.id}/duplicate`, {}, { headers }); toast.success('Campaign duplicated'); load(); }
    catch { toast.error('Duplicate failed'); }
  };
  const archive = async (c) => {
    try { await axios.delete(`${apiRoot}/api/comms/campaigns/${c.id}`, { headers }); toast.success('Archived'); load(); }
    catch { toast.error('Archive failed'); }
  };

  return (
    <div data-testid={`${testIdPrefix}-panel`}>
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
            className="px-3 py-2 rounded-full text-sm border focus:outline-none"
            style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
            data-testid={`${testIdPrefix}-search`}
          />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-2 rounded-full text-sm border"
            style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
            data-testid={`${testIdPrefix}-status-filter`}
          >
            <option value="">All statuses</option>
            {(meta?.statuses || []).map((s) => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
          </select>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-1.5 px-4 py-2 rounded-full text-sm font-bold"
          style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink, #03212b)' }}
          data-testid={`${testIdPrefix}-create-btn`}
        >
          <Plus size={15} />New campaign
        </button>
      </div>

      {/* List */}
      <div className="rounded-2xl border overflow-hidden" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }} data-testid={`${testIdPrefix}-campaign-list`}>
        {loading ? (
          <div className="p-10 text-center text-sm" style={{ color: 'var(--theme-text-muted)' }}>Loading…</div>
        ) : campaigns.length === 0 ? (
          <div className="p-12 text-center">
            <Megaphone size={28} className="mx-auto mb-2" style={{ color: 'var(--theme-text-muted)' }} />
            <p className="font-semibold" style={{ color: 'var(--theme-text)' }}>No campaigns yet</p>
            <p className="text-sm mb-4" style={{ color: 'var(--theme-text-muted)' }}>Create your first campaign.</p>
            <button onClick={() => setShowCreate(true)} className="px-4 py-2 rounded-full text-sm font-bold" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink, #03212b)' }} data-testid={`${testIdPrefix}-empty-create`}>Create campaign</button>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead style={{ background: 'var(--theme-bg)', color: 'var(--theme-text-muted)' }} className="text-xs uppercase tracking-wide">
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
                <tr key={c.id} className="border-t" style={{ borderColor: 'var(--theme-border)' }} data-testid={`campaign-row-${c.id}`}>
                  <td className="px-4 py-3">
                    <div className="font-semibold" style={{ color: 'var(--theme-text)' }}>{c.name}</div>
                    {module === 'all' && (
                      <span className={`inline-block mt-1 text-[10px] font-bold px-2 py-0.5 rounded-full ${MODULE_BADGE[c.related_module] || 'bg-slate-500/12 text-slate-500'}`}>{c.related_module}</span>
                    )}
                  </td>
                  <td className="px-4 py-3 hidden md:table-cell" style={{ color: 'var(--theme-text-muted)' }}>{typeLabel(c.campaign_type)}</td>
                  <td className="px-4 py-3"><span className={`text-[11px] font-bold px-2 py-1 rounded-full ${STATUS_STYLE[c.status] || 'bg-slate-500/15'}`}>{(c.status || 'draft').replace(/_/g, ' ')}</span></td>
                  <td className="px-4 py-3 hidden sm:table-cell" style={{ color: 'var(--theme-text-muted)' }}>{c.metrics?.sent || 0}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-1">
                      <button onClick={() => setEditing(c)} title="Edit" className="p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/5" style={{ color: 'var(--theme-text-muted)' }} data-testid={`campaign-edit-${c.id}`}><Pencil size={15} /></button>
                      <button onClick={() => setAnalytics(c)} title="Analytics" className="p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/5" style={{ color: 'var(--theme-text-muted)' }} data-testid={`campaign-analytics-${c.id}`}><BarChart3 size={15} /></button>
                      <button onClick={() => duplicate(c)} title="Duplicate" className="p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/5" style={{ color: 'var(--theme-text-muted)' }} data-testid={`campaign-dup-${c.id}`}><Copy size={15} /></button>
                      <button onClick={() => archive(c)} title="Archive" className="p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/5" style={{ color: 'var(--theme-text-muted)' }} data-testid={`campaign-archive-${c.id}`}><Archive size={15} /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showCreate && meta && (
        <CreateModal
          API={apiRoot} headers={headers} meta={meta} defaultModule={module}
          onClose={() => setShowCreate(false)}
          onCreated={(c) => { setShowCreate(false); load(); setEditing(c); }}
        />
      )}

      {editing && (
        <EmailBuilder
          campaign={editing} API={apiRoot} headers={headers}
          onClose={() => { setEditing(null); load(); }}
          onSaved={(c) => setEditing(c)}
        />
      )}

      {analytics && (
        <CampaignAnalytics campaign={analytics} API={apiRoot} headers={headers} onClose={() => setAnalytics(null)} />
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

  const inputStyle = { background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' };
  return (
    <div className="fixed inset-0 z-[150] bg-black/50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="rounded-2xl p-6 w-full max-w-lg border" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }} onClick={(e) => e.stopPropagation()} data-testid="comms-create-modal">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-bold text-xl pulse-font-heading" style={{ color: 'var(--theme-text)' }}>New campaign</h3>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/5" style={{ color: 'var(--theme-text-muted)' }}><X size={18} /></button>
        </div>
        <label className="block text-[11px] uppercase tracking-wider font-bold mb-1" style={{ color: 'var(--theme-text-muted)' }}>Name</label>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. October member newsletter" className="w-full px-4 py-3 rounded-xl border mb-4 focus:outline-none" style={inputStyle} data-testid="create-name" autoFocus />
        <label className="block text-[11px] uppercase tracking-wider font-bold mb-1" style={{ color: 'var(--theme-text-muted)' }}>Campaign type</label>
        <select value={type} onChange={(e) => setType(e.target.value)} className="w-full px-4 py-3 rounded-xl border mb-4" style={inputStyle} data-testid="create-type">
          {Object.entries(grouped).map(([g, items]) => (
            <optgroup key={g} label={g}>
              {items.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
            </optgroup>
          ))}
        </select>
        <label className="block text-[11px] uppercase tracking-wider font-bold mb-1" style={{ color: 'var(--theme-text-muted)' }}>Conversion goal (optional)</label>
        <input value={goal} onChange={(e) => setGoal(e.target.value)} placeholder="e.g. renewals, bookings, quote approvals" className="w-full px-4 py-3 rounded-xl border mb-5 focus:outline-none" style={inputStyle} data-testid="create-goal" />
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 rounded-full text-sm font-semibold hover:bg-black/5 dark:hover:bg-white/5" style={{ color: 'var(--theme-text-muted)' }}>Cancel</button>
          <button onClick={create} disabled={busy} className="px-5 py-2 rounded-full text-sm font-bold disabled:opacity-50" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink, #03212b)' }} data-testid="create-confirm">{busy ? 'Creating…' : 'Create & build'}</button>
        </div>
      </div>
    </div>
  );
}
