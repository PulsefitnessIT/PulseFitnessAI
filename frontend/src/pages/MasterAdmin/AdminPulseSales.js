/**
 * AdminPulseSales — Pulse Fitness internal CAPEX-sourced opportunity board.
 *
 * STRICT TENANT SEPARATION: only GymAxis Master Admin + Pulse Master Admins
 * can see this view. Customers (Third Space, MOD HQ, MOD sites) are 403'd
 * at the backend level — this UI never renders for them.
 *
 * Iter 216h128 — `routes/pulse_sales.py`.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  TrendingUp, Briefcase, ShieldCheck, RefreshCcw, Loader2,
  CheckCircle2, XCircle, Clock, Send, Sparkles,
  Building2, Cpu, MessageSquare, AlertTriangle,
} from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useAuth } from '@/App';
import { notify } from '@/components/notifications';

const STATUS_OPTIONS = [
  { id: 'new',       label: 'New',       icon: Sparkles,     color: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30' },
  { id: 'contacted', label: 'Contacted', icon: Send,         color: 'bg-blue-500/15 text-blue-300 border-blue-500/30' },
  { id: 'qualified', label: 'Qualified', icon: CheckCircle2, color: 'bg-violet-500/15 text-violet-300 border-violet-500/30' },
  { id: 'won',       label: 'Won',       icon: CheckCircle2, color: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30' },
  { id: 'lost',      label: 'Lost',      icon: XCircle,      color: 'bg-zinc-500/15 text-zinc-300 border-zinc-500/30' },
  { id: 'dismissed', label: 'Dismissed', icon: Clock,        color: 'bg-zinc-700/40 text-zinc-400 border-zinc-700/40' },
];
const STATUS_MAP = Object.fromEntries(STATUS_OPTIONS.map(s => [s.id, s]));

const SEVERITY_COLORS = {
  urgent: 'bg-red-500/20 text-red-300 border-red-500/40',
  high:   'bg-orange-500/20 text-orange-300 border-orange-500/40',
  medium: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/40',
  low:    'bg-zinc-500/15 text-zinc-300 border-zinc-500/30',
};

const fmt = (n) => n != null ? `£${Number(n).toLocaleString()}` : '—';
const fmtDate = (s) => s ? new Date(s).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }) : '—';

export default function AdminPulseSales() {
  const { API } = useAuth();
  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const [summary, setSummary] = useState(null);
  const [opps, setOpps] = useState([]);
  const [loading, setLoading] = useState(true);
  const [sweeping, setSweeping] = useState(false);
  const [statusFilter, setStatusFilter] = useState('active');  // active = not dismissed
  const [activeOpp, setActiveOpp] = useState(null);
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [sumRes, listRes] = await Promise.all([
        axios.get(`${API}/pulse-sales/summary`, { headers }),
        axios.get(`${API}/pulse-sales/opportunities`, {
          headers,
          params: {
            status: statusFilter === 'active' ? undefined : statusFilter,
            include_dismissed: statusFilter === 'dismissed',
            limit: 300,
          },
        }),
      ]);
      setSummary(sumRes.data);
      setOpps(listRes.data.opportunities || []);
    } catch (err) {
      if (err.response?.status === 403) {
        notify.error('Pulse Sales is restricted to Master Admins');
      } else {
        notify.error('Failed to load Pulse Sales opportunities');
      }
    } finally {
      setLoading(false);
    }
  }, [API, statusFilter]);

  useEffect(() => { loadData(); }, [loadData]);

  const runSweep = async () => {
    setSweeping(true);
    try {
      const r = await axios.post(`${API}/pulse-sales/sweep-capex`, {}, { headers });
      const res = r.data?.result || {};
      notify.success(
        `Sweep complete · ${res.orgs_scanned || 0} orgs · +${res.created || 0} new · ${res.updated || 0} updated`
      );
      loadData();
    } catch {
      notify.error('Sweep failed');
    } finally {
      setSweeping(false);
    }
  };

  const updateOpp = async (id, patch) => {
    setSaving(true);
    try {
      const r = await axios.patch(`${API}/pulse-sales/opportunities/${id}`, patch, { headers });
      setActiveOpp(r.data.opportunity);
      setOpps(prev => prev.map(o => o.id === id ? r.data.opportunity : o));
      notify.success('Opportunity updated');
    } catch {
      notify.error('Update failed');
    } finally {
      setSaving(false);
    }
  };

  const grouped = useMemo(() => {
    const buckets = {};
    STATUS_OPTIONS.forEach(s => { buckets[s.id] = []; });
    opps.forEach(o => {
      if (buckets[o.status]) buckets[o.status].push(o);
    });
    return buckets;
  }, [opps]);

  if (loading) {
    return (
      <div className="text-[var(--color-text-muted)] text-center py-16">
        <Loader2 className="animate-spin mx-auto mb-2" size={24} />
        Loading Pulse Sales pipeline...
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="admin-pulse-sales">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h2 className="text-2xl font-semibold text-white flex items-center gap-2">
            <Briefcase size={22} className="text-cyan-400" />
            Pulse Sales — CAPEX Opportunities
          </h2>
          <p className="text-[var(--color-text-muted)] text-sm">
            Internal sales pipeline auto-generated from customer CAPEX state. Tenant-restricted.
          </p>
        </div>
        <Button
          size="sm"
          onClick={runSweep}
          disabled={sweeping}
          className="bg-cyan-500 text-white hover:bg-cyan-600"
          data-testid="pulse-sales-sweep-btn"
        >
          {sweeping ? <Loader2 className="animate-spin mr-2" size={14} /> : <RefreshCcw size={14} className="mr-2" />}
          Refresh CAPEX scan
        </Button>
      </div>

      {/* Separation banner */}
      <Card className="bg-amber-500/10 border-amber-500/30 p-4 flex items-start gap-3" data-testid="pulse-sales-separation-banner">
        <ShieldCheck size={20} className="text-amber-300 flex-shrink-0 mt-0.5" />
        <div className="text-sm">
          <p className="text-amber-200 font-semibold mb-1">Internal-only view</p>
          <p className="text-amber-100/80">
            These opportunities are visible to Pulse Fitness staff (GymAxis + Pulse Master Admins) only.
            Customers — Third Space, MOD HQ, MOD sites — cannot see this view.
            Inactive opportunities auto-dismiss after 60 days.
          </p>
        </div>
      </Card>

      {/* Summary KPIs */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3" data-testid="pulse-sales-kpis">
          <Card className="bg-[var(--theme-surface)] border-white/10 p-4">
            <p className="text-[var(--color-text-muted)] text-xs mb-1">Active pipeline £</p>
            <p className="text-2xl font-bold text-white">{fmt(summary.active_pipeline_value)}</p>
          </Card>
          {STATUS_OPTIONS.filter(s => s.id !== 'dismissed').map(s => {
            const Ico = s.icon;
            return (
              <Card key={s.id} className="bg-[var(--theme-surface)] border-white/10 p-4">
                <div className="flex items-center justify-between mb-1">
                  <p className="text-[var(--color-text-muted)] text-xs">{s.label}</p>
                  <Ico size={14} className="text-[var(--color-text-muted)]" />
                </div>
                <p className="text-2xl font-bold text-white" data-testid={`pulse-sales-kpi-${s.id}`}>
                  {summary.by_status[s.id] || 0}
                </p>
              </Card>
            );
          })}
        </div>
      )}

      {/* Top orgs */}
      {summary?.top_orgs?.length > 0 && (
        <Card className="bg-[var(--theme-surface)] border-white/10 p-6" data-testid="pulse-sales-top-orgs">
          <h3 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
            <TrendingUp size={16} className="text-cyan-400" /> Top opportunity orgs
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[var(--color-text-muted)] border-b border-white/10">
                  <th className="text-left py-2 pr-4">Org</th>
                  <th className="text-left py-2 pr-4">Type</th>
                  <th className="text-right py-2 pr-4">Active opps</th>
                  <th className="text-right py-2">Pipeline £</th>
                </tr>
              </thead>
              <tbody>
                {summary.top_orgs.slice(0, 10).map(o => (
                  <tr key={o.organization_id} className="border-b border-white/5">
                    <td className="py-2 pr-4 text-white font-medium">{o.organization_name}</td>
                    <td className="py-2 pr-4">
                      <Badge className="bg-white/5 text-[var(--color-text-muted)] border-white/10 capitalize">
                        {o.account_type?.replace(/_/g, ' ')}
                      </Badge>
                    </td>
                    <td className="py-2 pr-4 text-right text-white">{o.active_opportunities}</td>
                    <td className="py-2 text-right text-white font-mono">{fmt(o.pipeline_value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Status filter chips */}
      <div className="flex gap-2 flex-wrap" data-testid="pulse-sales-filter-bar">
        {[
          { id: 'active', label: 'All active' },
          ...STATUS_OPTIONS,
        ].map(s => (
          <button
            key={s.id}
            onClick={() => setStatusFilter(s.id)}
            className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
              statusFilter === s.id
                ? 'bg-cyan-500/25 text-cyan-200 border-cyan-500/50'
                : 'bg-white/5 text-[var(--color-text-muted)] border-white/10 hover:bg-white/10'
            }`}
            data-testid={`pulse-sales-filter-${s.id}`}
          >
            {s.label}
          </button>
        ))}
      </div>

      {/* Opportunity list */}
      <Card className="bg-[var(--theme-surface)] border-white/10 p-0 overflow-hidden" data-testid="pulse-sales-opp-list">
        {opps.length === 0 ? (
          <div className="text-center py-16 text-[var(--color-text-muted)]">
            <AlertTriangle size={24} className="mx-auto mb-2 opacity-50" />
            No opportunities for this filter. Click "Refresh CAPEX scan" to recheck.
          </div>
        ) : (
          <div className="divide-y divide-white/5">
            {opps.map(o => {
              const sev = SEVERITY_COLORS[o.severity_signal] || SEVERITY_COLORS.low;
              const status = STATUS_MAP[o.status] || STATUS_OPTIONS[0];
              const Ico = status.icon;
              return (
                <button
                  key={o.id}
                  onClick={() => { setActiveOpp(o); setNote(''); }}
                  className="w-full text-left px-5 py-4 hover:bg-white/5 transition-colors flex items-center gap-4"
                  data-testid={`pulse-sales-opp-${o.id}`}
                >
                  <div className="flex-shrink-0 w-10 h-10 rounded-lg bg-white/5 flex items-center justify-center">
                    <Cpu size={18} className="text-[var(--color-text-muted)]" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap mb-1">
                      <p className="text-white font-medium truncate">{o.equipment_name}</p>
                      <span className={`text-[10px] uppercase tracking-wide px-2 py-0.5 rounded border ${sev}`}>
                        {o.severity_signal}
                      </span>
                      <span className={`text-[10px] uppercase tracking-wide px-2 py-0.5 rounded border flex items-center gap-1 ${status.color}`}>
                        <Ico size={10} /> {status.label}
                      </span>
                    </div>
                    <p className="text-xs text-[var(--color-text-muted)] flex items-center gap-2 flex-wrap">
                      <Building2 size={11} /> {o.organization_name}
                      <span className="opacity-60">·</span>
                      {o.equipment_type}
                      <span className="opacity-60">·</span>
                      CAPEX {o.capex_status?.replace('_', ' ')}
                      <span className="opacity-60">·</span>
                      Score {o.capex_score}/100
                    </p>
                  </div>
                  <div className="text-right flex-shrink-0">
                    <p className="text-white font-mono text-sm">{fmt(o.replacement_cost)}</p>
                    <p className="text-[10px] text-[var(--color-text-muted)]">
                      Auto-dismiss {fmtDate(o.auto_dismiss_at)}
                    </p>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </Card>

      {/* Detail drawer */}
      {activeOpp && (
        <div
          className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-end md:items-center justify-end"
          onClick={() => setActiveOpp(null)}
          data-testid="pulse-sales-detail-drawer"
        >
          <div
            onClick={e => e.stopPropagation()}
            className="bg-[var(--color-surface-dark-2)] w-full md:max-w-xl md:h-full p-6 overflow-y-auto border-l border-white/10"
          >
            <div className="flex items-start justify-between mb-4">
              <div>
                <h3 className="text-xl font-semibold text-white">{activeOpp.equipment_name}</h3>
                <p className="text-sm text-[var(--color-text-muted)]">
                  {activeOpp.organization_name} · {activeOpp.equipment_type}
                </p>
              </div>
              <button onClick={() => setActiveOpp(null)} className="text-[var(--color-text-muted)] hover:text-white" data-testid="pulse-sales-close-drawer">✕</button>
            </div>

            <div className="grid grid-cols-2 gap-3 mb-5">
              <div className="bg-white/5 rounded-lg p-3">
                <p className="text-[10px] text-[var(--color-text-muted)] uppercase mb-1">CAPEX status</p>
                <p className="text-white font-medium capitalize">{activeOpp.capex_status?.replace('_', ' ')}</p>
              </div>
              <div className="bg-white/5 rounded-lg p-3">
                <p className="text-[10px] text-[var(--color-text-muted)] uppercase mb-1">CAPEX score</p>
                <p className="text-white font-medium">{activeOpp.capex_score}/100</p>
              </div>
              <div className="bg-white/5 rounded-lg p-3">
                <p className="text-[10px] text-[var(--color-text-muted)] uppercase mb-1">Replacement cost</p>
                <p className="text-white font-medium">{fmt(activeOpp.replacement_cost)}</p>
              </div>
              <div className="bg-white/5 rounded-lg p-3">
                <p className="text-[10px] text-[var(--color-text-muted)] uppercase mb-1">Auto-dismiss</p>
                <p className="text-white font-medium">{fmtDate(activeOpp.auto_dismiss_at)}</p>
              </div>
            </div>

            {/* Status pill picker */}
            <p className="text-[var(--color-text-muted)] text-xs uppercase tracking-wide mb-2">Pipeline stage</p>
            <div className="grid grid-cols-3 gap-2 mb-5">
              {STATUS_OPTIONS.map(s => (
                <button
                  key={s.id}
                  onClick={() => updateOpp(activeOpp.id, { status: s.id })}
                  disabled={saving || activeOpp.status === s.id}
                  className={`px-3 py-2 rounded border text-xs font-medium transition-colors ${
                    activeOpp.status === s.id ? s.color : 'bg-white/5 text-[var(--color-text-muted)] border-white/10 hover:bg-white/10'
                  } disabled:opacity-50`}
                  data-testid={`pulse-sales-stage-${s.id}`}
                >
                  {s.label}
                </button>
              ))}
            </div>

            {/* Add note */}
            <p className="text-[var(--color-text-muted)] text-xs uppercase tracking-wide mb-2">Add a note</p>
            <textarea
              value={note}
              onChange={e => setNote(e.target.value)}
              placeholder="e.g. Spoke with Daniel — interested in trade-in package."
              rows={3}
              className="w-full bg-black/30 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-[var(--color-text-muted)] focus:outline-none focus:border-cyan-500/50 mb-2"
              data-testid="pulse-sales-note-input"
            />
            <Button
              size="sm"
              onClick={() => {
                if (!note.trim()) return;
                updateOpp(activeOpp.id, { note: note.trim() }).then(() => setNote(''));
              }}
              disabled={saving || !note.trim()}
              className="bg-cyan-500 text-white hover:bg-cyan-600"
              data-testid="pulse-sales-add-note-btn"
            >
              <MessageSquare size={14} className="mr-2" /> Add note
            </Button>

            {/* Notes timeline */}
            {activeOpp.notes?.length > 0 && (
              <div className="mt-6">
                <p className="text-[var(--color-text-muted)] text-xs uppercase tracking-wide mb-3">
                  Notes ({activeOpp.notes.length})
                </p>
                <div className="space-y-3">
                  {[...activeOpp.notes].reverse().map(n => (
                    <div key={n.id} className="bg-white/5 rounded-lg p-3">
                      <div className="flex items-center justify-between mb-1">
                        <p className="text-xs font-semibold text-cyan-300">{n.author_name || n.author_email}</p>
                        <p className="text-[10px] text-[var(--color-text-muted)]">{fmtDate(n.created_at)}</p>
                      </div>
                      <p className="text-sm text-white whitespace-pre-wrap">{n.text}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
