import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import axios from 'axios';
import {
  Users, Building2, GitBranch, Inbox, Zap, FileText, Target,
  TrendingUp, MessageSquare, Brain, RefreshCw, ArrowUpRight,
  ArrowDownRight, Minus, Clock, Link2, CheckCircle, AlertTriangle
} from 'lucide-react';

const fmt = (v) => typeof v === 'number' ? (v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v.toLocaleString()) : v;
const gbp = (v) => `£${(v || 0).toLocaleString('en-GB', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;

const StatCard = ({ icon: Icon, label, value, sub, color = 'text-blue-400', bgColor = 'bg-blue-500/10' }) => (
  <Card className="p-5 bg-white border-zinc-200 hover:shadow-sm transition-shadow" data-testid={`crm-stat-${label.toLowerCase().replace(/\s+/g, '-')}`}>
    <div className="flex items-start justify-between">
      <div className={`w-9 h-9 rounded-lg ${bgColor} flex items-center justify-center`}>
        <Icon size={18} className={color} />
      </div>
      {sub && <span className="text-[10px] text-zinc-400 font-medium">{sub}</span>}
    </div>
    <p className="text-2xl font-bold text-zinc-900 mt-3">{value}</p>
    <p className="text-xs text-zinc-500 mt-0.5">{label}</p>
  </Card>
);

const AdminCRMAnalytics = () => {
  const { API } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/master-admin/crm-analytics`, { headers });
      setData(res.data);
    } catch (err) {
      console.error('CRM analytics load failed', err);
    }
    setLoading(false);
  }, [API]);

  useEffect(() => { load(); }, [load]);

  if (loading || !data) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="animate-spin text-zinc-400" size={24} />
      </div>
    );
  }

  const { overview, growth, pipeline, quotes, contacts, inbox, users, workflows, integrations, activity_types, recent_deals, recent_activities, deals_at_risk = [], renewals_due = { count: 0, items: [], total_value: 0, weighted_value: 0, window_days: 30 }, ai_usage = { autopilot_drafts: 0, win_intel_hits: 0, copilot_sessions: 0, total: 0 } } = data;
  const sageStatus = integrations?.sage200?.status;

  return (
    <div className="space-y-6" data-testid="admin-crm-analytics">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-zinc-900">CRM Intelligence</h2>
          <p className="text-xs text-zinc-400 mt-0.5">Real-time analytics across your entire sales operation</p>
        </div>
        <button onClick={load} className="p-2 hover:bg-zinc-100 rounded-lg transition-colors" data-testid="crm-analytics-refresh">
          <RefreshCw size={16} className="text-zinc-500" />
        </button>
      </div>

      {/* KPI Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        <StatCard icon={Users} label="Total Contacts" value={fmt(overview.total_contacts)} sub={`+${growth.new_contacts_30d} (30d)`} color="text-blue-500" bgColor="bg-blue-500/10" />
        <StatCard icon={Building2} label="Companies" value={fmt(overview.total_companies)} color="text-violet-500" bgColor="bg-violet-500/10" />
        <StatCard icon={GitBranch} label="Active Deals" value={fmt(overview.total_deals)} sub={`+${growth.new_deals_30d} (30d)`} color="text-amber-500" bgColor="bg-amber-500/10" />
        <StatCard icon={TrendingUp} label="Win Rate" value={`${pipeline.win_rate}%`} sub={`${pipeline.won_deals}W / ${pipeline.lost_deals}L`} color="text-emerald-500" bgColor="bg-emerald-500/10" />
        <StatCard icon={Target} label="Revenue Won" value={gbp(pipeline.total_won_value)} color="text-emerald-600" bgColor="bg-emerald-500/10" />
      </div>

      {/* Iter 215br — Pipeline value · Renewal countdown · AI usage */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3" data-testid="crm-business-row">
        {/* Pipeline value & weighted forecast */}
        <Card className="p-5 bg-white border-zinc-200" data-testid="crm-pipeline-value-card">
          <div className="flex items-start justify-between">
            <div className="w-9 h-9 rounded-lg bg-cyan-500/10 flex items-center justify-center">
              <GitBranch size={18} className="text-cyan-500" />
            </div>
            <span className="text-[10px] text-zinc-400 font-medium uppercase tracking-wider">Open pipeline</span>
          </div>
          <p className="text-2xl font-bold text-zinc-900 mt-3">{gbp(overview.pipeline_value)}</p>
          <p className="text-xs text-zinc-500 mt-0.5">across {overview.active_opportunities} active deals</p>
          <div className="mt-3 pt-3 border-t border-zinc-100 flex items-center justify-between">
            <span className="text-[11px] text-zinc-500">Weighted forecast</span>
            <span className="text-sm font-semibold text-zinc-800">{gbp(overview.weighted_forecast)}</span>
          </div>
        </Card>

        {/* Renewal countdown */}
        <Card className="p-5 bg-white border-zinc-200" data-testid="crm-renewals-card">
          <div className="flex items-start justify-between">
            <div className="w-9 h-9 rounded-lg bg-amber-500/10 flex items-center justify-center">
              <Clock size={18} className="text-amber-500" />
            </div>
            <span className="text-[10px] text-zinc-400 font-medium uppercase tracking-wider">{renewals_due.window_days}d horizon</span>
          </div>
          <p className="text-2xl font-bold text-zinc-900 mt-3">{renewals_due.count}</p>
          <p className="text-xs text-zinc-500 mt-0.5">deals closing · {gbp(renewals_due.total_value)} total</p>
          <div className="mt-3 space-y-1.5 max-h-32 overflow-y-auto pr-1">
            {renewals_due.items.length === 0 ? (
              <p className="text-[11px] text-zinc-400 italic">Nothing in the next 30 days</p>
            ) : renewals_due.items.slice(0, 4).map((r, i) => {
              const days = Math.max(0, Math.round((new Date(r.close_date) - new Date()) / 86400000));
              return (
                <div key={i} className="flex items-center justify-between text-[11px]" data-testid={`crm-renewal-row-${i}`}>
                  <span className="truncate text-zinc-700 mr-2">{r.title}</span>
                  <span className={`font-bold ${days <= 7 ? 'text-red-600' : days <= 14 ? 'text-amber-600' : 'text-zinc-600'}`}>{days}d</span>
                </div>
              );
            })}
          </div>
        </Card>

        {/* AI usage */}
        <Card className="p-5 bg-white border-zinc-200" data-testid="crm-ai-usage-card">
          <div className="flex items-start justify-between">
            <div className="w-9 h-9 rounded-lg bg-purple-500/10 flex items-center justify-center">
              <Brain size={18} className="text-purple-500" />
            </div>
            <span className="text-[10px] text-zinc-400 font-medium uppercase tracking-wider">CRM AI</span>
          </div>
          <p className="text-2xl font-bold text-zinc-900 mt-3">{fmt(ai_usage.total)}</p>
          <p className="text-xs text-zinc-500 mt-0.5">total AI interactions</p>
          <div className="mt-3 pt-3 border-t border-zinc-100 grid grid-cols-3 gap-2 text-center">
            <div>
              <p className="text-sm font-semibold text-zinc-900">{ai_usage.autopilot_drafts}</p>
              <p className="text-[10px] text-zinc-500 leading-tight mt-0.5">Autopilot drafts</p>
            </div>
            <div>
              <p className="text-sm font-semibold text-zinc-900">{ai_usage.win_intel_hits}</p>
              <p className="text-[10px] text-zinc-500 leading-tight mt-0.5">Win-intel hits</p>
            </div>
            <div>
              <p className="text-sm font-semibold text-zinc-900">{ai_usage.copilot_sessions}</p>
              <p className="text-[10px] text-zinc-500 leading-tight mt-0.5">Copilot sessions</p>
            </div>
          </div>
        </Card>
      </div>

      {/* Iter 215br — Top deals at risk */}
      {deals_at_risk.length > 0 && (
        <Card className="p-5 bg-white border-zinc-200" data-testid="crm-deals-at-risk">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-zinc-900 flex items-center gap-2">
              <AlertTriangle size={16} className="text-rose-500" /> Top deals at risk
            </h3>
            <span className="text-[10px] uppercase tracking-wider text-zinc-400">Stale &middot; low-prob &middot; overdue</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-2">
            {deals_at_risk.map((d, i) => (
              <div key={d.id || i} className="p-3 rounded-lg border border-rose-100 bg-rose-50/40" data-testid={`crm-risk-deal-${i}`}>
                <p className="text-xs font-semibold text-zinc-800 truncate" title={d.title}>{d.title || 'Untitled deal'}</p>
                <p className="text-[10px] text-zinc-500 truncate mt-0.5">{d.company_name || '—'}</p>
                <div className="flex items-center justify-between mt-2">
                  <span className="text-sm font-bold text-zinc-900">{gbp(d.value)}</span>
                  <span className="text-[10px] font-bold text-rose-600">{Math.round(d.probability || 0)}%</span>
                </div>
                <div className="flex flex-wrap gap-1 mt-2">
                  {(d.risk_reasons || []).map(r => (
                    <span key={r} className="text-[9px] bg-rose-100 text-rose-700 px-1.5 py-0.5 rounded font-medium uppercase tracking-wide">{r.replace(/_/g, ' ')}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Pipeline + Quotes Row */}
      <div className="grid lg:grid-cols-3 gap-4">
        {/* Pipeline Breakdown */}
        <Card className="lg:col-span-2 p-5 bg-white border-zinc-200" data-testid="crm-pipeline-breakdown">
          <h3 className="text-sm font-semibold text-zinc-900 mb-4 flex items-center gap-2">
            <GitBranch size={16} className="text-blue-500" /> Pipeline Breakdown
          </h3>
          <div className="space-y-3">
            {pipeline.stages.map(stage => {
              const maxVal = Math.max(...pipeline.stages.map(s => s.value), 1);
              const pct = (stage.value / maxVal) * 100;
              return (
                <div key={stage.id} className="flex items-center gap-3" data-testid={`pipeline-stage-${stage.id}`}>
                  <div className="w-24 text-xs text-zinc-600 font-medium truncate">{stage.name}</div>
                  <div className="flex-1 bg-zinc-100 rounded-full h-6 relative overflow-hidden">
                    <div className="h-full rounded-full transition-all duration-500" style={{ width: `${Math.max(pct, 2)}%`, backgroundColor: stage.color }} />
                    <span className="absolute inset-0 flex items-center justify-center text-[10px] font-bold text-zinc-700">
                      {stage.count} deals &middot; {gbp(stage.value)}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </Card>

        {/* Quotes Summary */}
        <Card className="p-5 bg-white border-zinc-200" data-testid="crm-quotes-summary">
          <h3 className="text-sm font-semibold text-zinc-900 mb-4 flex items-center gap-2">
            <FileText size={16} className="text-indigo-500" /> Quotes (CPQ)
          </h3>
          <div className="space-y-3">
            <div className="flex items-center justify-between p-3 bg-zinc-50 rounded-lg">
              <span className="text-xs text-zinc-500">Draft</span>
              <span className="text-sm font-bold text-zinc-700">{quotes.draft}</span>
            </div>
            <div className="flex items-center justify-between p-3 bg-amber-50 rounded-lg">
              <span className="text-xs text-amber-600">Sent</span>
              <span className="text-sm font-bold text-amber-700">{quotes.sent}</span>
            </div>
            <div className="flex items-center justify-between p-3 bg-emerald-50 rounded-lg">
              <span className="text-xs text-emerald-600">Accepted</span>
              <span className="text-sm font-bold text-emerald-700">{quotes.accepted}</span>
            </div>
            <div className="mt-3 pt-3 border-t border-zinc-100">
              <p className="text-xs text-zinc-400">Total Accepted Value</p>
              <p className="text-xl font-bold text-zinc-900">{gbp(quotes.total_value)}</p>
            </div>
          </div>
        </Card>
      </div>

      {/* Second Row: Lead Scoring + Sources + Inbox + Integrations */}
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Lead Scores */}
        <Card className="p-5 bg-white border-zinc-200" data-testid="crm-lead-scores">
          <h3 className="text-sm font-semibold text-zinc-900 mb-3 flex items-center gap-2">
            <Target size={16} className="text-rose-500" /> Lead Scores
          </h3>
          <div className="space-y-2">
            {[
              { label: 'Hot (70+)', value: contacts.lead_scores.hot, color: 'bg-red-500', text: 'text-red-700' },
              { label: 'Warm (40-69)', value: contacts.lead_scores.warm, color: 'bg-amber-400', text: 'text-amber-700' },
              { label: 'Cold (<40)', value: contacts.lead_scores.cold, color: 'bg-blue-400', text: 'text-blue-700' },
              { label: 'Unscored', value: contacts.lead_scores.unscored, color: 'bg-zinc-300', text: 'text-zinc-600' },
            ].map(s => (
              <div key={s.label} className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className={`w-2.5 h-2.5 rounded-full ${s.color}`} />
                  <span className="text-xs text-zinc-500">{s.label}</span>
                </div>
                <span className={`text-sm font-bold ${s.text}`}>{s.value}</span>
              </div>
            ))}
          </div>
        </Card>

        {/* Contact Sources */}
        <Card className="p-5 bg-white border-zinc-200" data-testid="crm-contact-sources">
          <h3 className="text-sm font-semibold text-zinc-900 mb-3 flex items-center gap-2">
            <ArrowUpRight size={16} className="text-teal-500" /> Contact Sources
          </h3>
          <div className="space-y-2">
            {Object.entries(contacts.source_breakdown).length > 0 ? (
              Object.entries(contacts.source_breakdown)
                .sort((a, b) => b[1] - a[1])
                .slice(0, 6)
                .map(([source, count]) => (
                  <div key={source} className="flex items-center justify-between">
                    <span className="text-xs text-zinc-500 capitalize">{source.replace(/_/g, ' ')}</span>
                    <span className="text-sm font-bold text-zinc-700">{count}</span>
                  </div>
                ))
            ) : (
              <p className="text-xs text-zinc-400 text-center py-4">No contacts yet</p>
            )}
          </div>
        </Card>

        {/* Inbox */}
        <Card className="p-5 bg-white border-zinc-200" data-testid="crm-inbox-stats">
          <h3 className="text-sm font-semibold text-zinc-900 mb-3 flex items-center gap-2">
            <Inbox size={16} className="text-blue-500" /> Inbox
          </h3>
          <div className="space-y-4">
            <div>
              <p className="text-3xl font-bold text-zinc-900">{overview.total_conversations}</p>
              <p className="text-xs text-zinc-400">Total Conversations</p>
            </div>
            <div className="flex gap-3">
              <div className="flex-1 p-2.5 bg-amber-50 rounded-lg text-center">
                <p className="text-lg font-bold text-amber-700">{inbox.open_conversations}</p>
                <p className="text-[10px] text-amber-600">Open</p>
              </div>
              <div className="flex-1 p-2.5 bg-red-50 rounded-lg text-center">
                <p className="text-lg font-bold text-red-700">{inbox.high_priority}</p>
                <p className="text-[10px] text-red-600">High Priority</p>
              </div>
            </div>
          </div>
        </Card>

        {/* Integrations & System */}
        <Card className="p-5 bg-white border-zinc-200" data-testid="crm-system-health">
          <h3 className="text-sm font-semibold text-zinc-900 mb-3 flex items-center gap-2">
            <Link2 size={16} className="text-emerald-500" /> System Health
          </h3>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs text-zinc-500">CRM Users</span>
              <span className="text-sm font-bold text-zinc-700">{overview.total_users}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-zinc-500">User Roles</span>
              <div className="flex gap-1.5">
                {Object.entries(users.by_role).map(([role, count]) => (
                  <span key={role} className="text-[10px] bg-zinc-100 text-zinc-600 px-1.5 py-0.5 rounded font-medium">
                    {count} {role}
                  </span>
                ))}
              </div>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-zinc-500">Sage 200</span>
              <span className={`text-[10px] font-medium px-2 py-0.5 rounded ${
                sageStatus === 'connected' ? 'bg-emerald-100 text-emerald-700' :
                sageStatus === 'configured' ? 'bg-amber-100 text-amber-700' :
                'bg-zinc-100 text-zinc-500'
              }`}>
                {sageStatus === 'connected' ? 'Connected' : sageStatus === 'configured' ? 'Pending Keys' : 'Not Set Up'}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-zinc-500">Workflows</span>
              <span className="text-sm font-bold text-zinc-700">{workflows.total_executions} runs</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-zinc-500">Meetings Logged</span>
              <span className="text-sm font-bold text-zinc-700">{overview.total_meetings}</span>
            </div>
          </div>
        </Card>
      </div>

      {/* Operational Row: Workflows + Activity Types */}
      <div className="grid sm:grid-cols-2 gap-4">
        <Card className="p-5 bg-white border-zinc-200" data-testid="crm-workflows-card">
          <h3 className="text-sm font-semibold text-zinc-900 mb-3 flex items-center gap-2">
            <Zap size={16} className="text-purple-500" /> Automation
          </h3>
          <div className="grid grid-cols-3 gap-3 mb-4">
            <div className="text-center p-3 bg-purple-50 rounded-lg">
              <p className="text-xl font-bold text-purple-700">{overview.total_workflows}</p>
              <p className="text-[10px] text-purple-500">Total</p>
            </div>
            <div className="text-center p-3 bg-emerald-50 rounded-lg">
              <p className="text-xl font-bold text-emerald-700">{overview.active_workflows}</p>
              <p className="text-[10px] text-emerald-500">Active</p>
            </div>
            <div className="text-center p-3 bg-blue-50 rounded-lg">
              <p className="text-xl font-bold text-blue-700">{workflows.total_executions}</p>
              <p className="text-[10px] text-blue-500">Executions</p>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="p-2.5 bg-zinc-50 rounded-lg text-center">
              <p className="text-lg font-bold text-zinc-700">{overview.total_quotes}</p>
              <p className="text-[10px] text-zinc-500">Total Quotes</p>
            </div>
            <div className="p-2.5 bg-zinc-50 rounded-lg text-center">
              <p className="text-lg font-bold text-zinc-700">{overview.total_meetings}</p>
              <p className="text-[10px] text-zinc-500">AI Meetings</p>
            </div>
          </div>
        </Card>

        <Card className="p-5 bg-white border-zinc-200" data-testid="crm-activity-types">
          <h3 className="text-sm font-semibold text-zinc-900 mb-3 flex items-center gap-2">
            <MessageSquare size={16} className="text-orange-500" /> Activity Breakdown
          </h3>
          <div className="mb-3">
            <p className="text-xs text-zinc-400">Total Activities</p>
            <p className="text-2xl font-bold text-zinc-900">{overview.total_activities}</p>
            <p className="text-[10px] text-zinc-400">{growth.recent_activities_30d} in last 30 days</p>
          </div>
          <div className="space-y-2">
            {Object.entries(activity_types).length > 0 ? (
              Object.entries(activity_types)
                .sort((a, b) => b[1] - a[1])
                .map(([type, count]) => (
                  <div key={type} className="flex items-center justify-between">
                    <span className="text-xs text-zinc-500 capitalize">{type.replace(/_/g, ' ')}</span>
                    <span className="text-sm font-bold text-zinc-700">{count}</span>
                  </div>
                ))
            ) : (
              <p className="text-xs text-zinc-400 text-center py-2">No activities logged</p>
            )}
          </div>
        </Card>
      </div>

      {/* Recent Deals + Recent Activities */}
      <div className="grid lg:grid-cols-2 gap-4">
        <Card className="p-5 bg-white border-zinc-200" data-testid="crm-recent-deals">
          <h3 className="text-sm font-semibold text-zinc-900 mb-4 flex items-center gap-2">
            <TrendingUp size={16} className="text-emerald-500" /> Recent Deals
          </h3>
          {recent_deals.length > 0 ? (
            <div className="space-y-2">
              {recent_deals.map((deal, i) => (
                <div key={i} className="flex items-center justify-between p-2.5 bg-zinc-50 rounded-lg">
                  <div className="min-w-0">
                    <p className="text-xs font-medium text-zinc-800 truncate">{deal.title}</p>
                    <p className="text-[10px] text-zinc-400">{deal.contact_name}</p>
                  </div>
                  <div className="text-right flex-shrink-0 ml-3">
                    <p className="text-xs font-bold text-zinc-800">{gbp(deal.value)}</p>
                    <p className="text-[10px] text-zinc-400 capitalize">{deal.stage?.replace(/_/g, ' ')}</p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-zinc-400 text-center py-8">No deals yet</p>
          )}
        </Card>

        <Card className="p-5 bg-white border-zinc-200" data-testid="crm-recent-activity">
          <h3 className="text-sm font-semibold text-zinc-900 mb-4 flex items-center gap-2">
            <Clock size={16} className="text-blue-500" /> Recent Activity
          </h3>
          {recent_activities.length > 0 ? (
            <div className="space-y-2">
              {recent_activities.map((act, i) => (
                <div key={i} className="flex items-start gap-3 p-2.5 bg-zinc-50 rounded-lg">
                  <div className="w-6 h-6 rounded-full bg-blue-100 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <MessageSquare size={12} className="text-blue-600" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs text-zinc-700 truncate">{act.description}</p>
                    <p className="text-[10px] text-zinc-400">{act.created_by_name} &middot; {new Date(act.created_at).toLocaleDateString()}</p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-zinc-400 text-center py-8">No activity yet</p>
          )}
        </Card>
      </div>
    </div>
  );
};

export default AdminCRMAnalytics;
