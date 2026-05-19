import { useState, useEffect, useCallback } from 'react';
import { useCRM } from './CRMApp';
import {
  TrendingUp, Users, Building2, Target, AlertTriangle, CheckCircle, FileText, Phone, Mail, Calendar, DollarSign, Briefcase, Activity, ChevronRight, Zap, Wrench,
  AlertCircle, PieChart, Award, UserCheck
} from 'lucide-react';
import axios from 'axios';
import Button from '@/components/shared/Button';

const fmt = (n) => `£${(n || 0).toLocaleString('en-GB', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;

const STAGE_COLORS = {
  lead: 'var(--color-text-faint-alt)', qualified: 'var(--color-accent-violet)', discovery: 'var(--color-info)', solution: 'var(--color-cyan-500)',
  proposal: 'var(--color-warning)', negotiation: 'var(--color-orange)', verbal_won: 'var(--color-success-alt-2)',
};
const ACT_ICONS = { note: FileText, call: Phone, email: Mail, meeting: Calendar, task: CheckCircle, system: Activity, visit: Wrench };

const timeAgo = (d) => {
  const diff = Date.now() - new Date(d).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
};

function Card({ children, className = '', style = {}, isDark, ...p }) {
  return (
    <div className={`rounded-lg border p-5 ${className}`}
      style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)', ...style }} {...p}>
      {children}
    </div>
  );
}

/* ─── KPI ROW ─── */
function KPIRow({ kpis, isDark, c }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
      {kpis.map((kpi, i) => {
        const Icon = kpi.icon;
        return (
          <div key={i} onClick={kpi.click} className={`p-4 rounded-lg border transition-all ${kpi.click ? 'cursor-pointer hover:scale-[1.02]' : ''}`}
            style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}
            data-testid={`kpi-${kpi.label.toLowerCase().replace(/\s/g, '-')}`}>
            <div className="flex items-center gap-2 mb-2">
              <div className="w-7 h-7 rounded-md flex items-center justify-center" style={{ background: `${kpi.color}15` }}>
                <Icon size={14} style={{ color: kpi.color }} />
              </div>
              <span className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>{kpi.label}</span>
            </div>
            <p className="text-xl font-bold tracking-tight" style={{ color: c.text }}>{kpi.value}</p>
            <p className="text-[11px] mt-0.5" style={{ color: c.textDim }}>{kpi.sub}</p>
          </div>
        );
      })}
    </div>
  );
}

/* ─── PIPELINE BY STAGE ─── */
function PipelineByStage({ data, isDark, c, onViewAll }) {
  return (
    <Card isDark={isDark}>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold" style={{ color: c.text }}>Pipeline by Stage</h3>
        <Button variant="tertiary" size="sm" onClick={onViewAll} iconRight={ChevronRight} data-testid="crm-pipeline-stage-view-all">View all</Button>
      </div>
      {data.stage_breakdown.some(s => s.count > 0) ? (
        <div className="space-y-3">
          {data.stage_breakdown.map(stage => {
            const maxVal = Math.max(...data.stage_breakdown.map(s => s.value), 1);
            const pct = (stage.value / maxVal) * 100;
            return (
              <div key={stage.stage} className="flex items-center gap-3">
                <span className="text-xs w-24 truncate" style={{ color: c.textMuted }}>{stage.name}</span>
                <div className="flex-1 h-6 rounded-sm overflow-hidden" style={{ background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-100)' }}>
                  <div className="h-full rounded-sm flex items-center px-2 transition-all duration-500" style={{ width: `${Math.max(pct, 2)}%`, background: STAGE_COLORS[stage.stage] || 'var(--color-text-faint-alt)' }}>
                    {pct > 15 && <span className="text-[10px] font-bold text-white">{fmt(stage.value)}</span>}
                  </div>
                </div>
                <span className="text-xs font-mono w-8 text-right" style={{ color: c.textDim }}>{stage.count}</span>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="text-center py-8">
          <Briefcase size={32} className="mx-auto mb-2" style={{ color: c.textDim }} />
          <p className="text-sm" style={{ color: c.textDim }}>No active deals yet</p>
        </div>
      )}
    </Card>
  );
}

/* ─── TASKS DUE ─── */
function TasksDue({ tasks, isDark, c, onViewAll }) {
  return (
    <Card isDark={isDark}>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold" style={{ color: c.text }}>Tasks Due</h3>
        <Button variant="tertiary" size="sm" onClick={onViewAll} data-testid="crm-tasks-due-view-all">View all</Button>
      </div>
      {tasks.length > 0 ? (
        <div className="space-y-2">
          {tasks.slice(0, 5).map(task => (
            <div key={task.id} className="flex items-start gap-2 py-1.5" style={{ borderBottom: `1px solid ${isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-neutral-100)'}` }}>
              <CheckCircle size={13} className="mt-0.5 shrink-0" style={{ color: task.priority === 'high' ? 'var(--color-danger-alt)' : 'var(--color-accent-amber)' }} />
              <div className="flex-1 min-w-0">
                <p className="text-xs truncate" style={{ color: c.text }}>{task.subject}</p>
                {task.due_date && <p className="text-[10px]" style={{ color: c.textDim }}>{new Date(task.due_date).toLocaleDateString('en-GB')}</p>}
              </div>
              {task.priority === 'high' && <span className="text-[8px] font-bold uppercase px-1 py-0.5 rounded bg-[rgb(var(--rgb-danger-alt)/0.15)] text-[var(--color-danger-alt)]">High</span>}
            </div>
          ))}
        </div>
      ) : <p className="text-xs text-center py-4" style={{ color: c.textDim }}>No tasks due</p>}
    </Card>
  );
}

/* ─── STAGNATING DEALS ─── */
function StagnatingDeals({ deals, isDark, c, navigateTo }) {
  return (
    <Card isDark={isDark}>
      <div className="flex items-center gap-2 mb-3">
        <AlertTriangle size={14} style={{ color: 'var(--color-accent-amber)' }} />
        <h3 className="text-sm font-semibold" style={{ color: c.text }}>Stagnating Deals</h3>
      </div>
      {deals.length > 0 ? deals.map(d => {
        const days = d.days_in_stage || 0;
        return (
          <div key={d.id} className="flex items-center gap-2 py-1.5 cursor-pointer hover:opacity-80" onClick={() => navigateTo('opportunity', d.id)}
            style={{ borderBottom: `1px solid ${isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-neutral-100)'}` }} data-testid={`stag-deal-${d.id}`}>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium truncate" style={{ color: c.text }}>{d.title}</p>
              <p className="text-[10px]" style={{ color: c.textDim }}>{d.stage?.replace('_', ' ')} &middot; {fmt(d.value)}</p>
            </div>
            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded" style={{ background: days > 30 ? 'var(--color-danger-alt)20' : 'var(--color-accent-amber)20', color: days > 30 ? 'var(--color-danger-alt)' : 'var(--color-accent-amber)' }}>{days}d</span>
          </div>
        );
      }) : <p className="text-xs text-center py-4" style={{ color: c.textDim }}>No stagnating deals</p>}
    </Card>
  );
}

/* ─── RECENT ACTIVITY ─── */
function RecentActivity({ activities, isDark, c, onViewAll }) {
  return (
    <Card isDark={isDark}>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold" style={{ color: c.text }}>Recent Activity</h3>
        <Button variant="tertiary" size="sm" onClick={onViewAll} data-testid="crm-recent-activity-view-all">View all</Button>
      </div>
      {activities.length > 0 ? activities.slice(0, 6).map((act, i) => {
        const Icon = ACT_ICONS[act.type] || Activity;
        return (
          <div key={act.id || i} className="flex items-start gap-2 py-1.5" style={{ borderBottom: `1px solid ${isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-neutral-100)'}` }}>
            <div className="w-6 h-6 rounded-md flex items-center justify-center mt-0.5 shrink-0" style={{ background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-100)' }}>
              <Icon size={11} style={{ color: c.textDim }} />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs truncate" style={{ color: c.text }}>{act.subject}</p>
              {act.body && <p className="text-[10px] truncate" style={{ color: c.textDim }}>{act.body}</p>}
            </div>
            <span className="text-[9px] shrink-0 mt-0.5" style={{ color: c.textDim }}>{timeAgo(act.created_at)}</span>
          </div>
        );
      }) : (
        <div className="text-center py-6">
          <Activity size={24} className="mx-auto mb-2" style={{ color: c.textDim }} />
          <p className="text-xs" style={{ color: c.textDim }}>No activity yet</p>
        </div>
      )}
    </Card>
  );
}

/* ─── WORKFLOW ACTIVITY ─── */
function WorkflowActivity({ wfRuns, isDark, c, onManage }) {
  return (
    <Card isDark={isDark}>
      <div className="flex items-center gap-2 mb-3">
        <Zap size={14} style={{ color: 'var(--color-success-alt)' }} />
        <h3 className="text-sm font-semibold" style={{ color: c.text }}>Workflow Activity</h3>
        <Button variant="tertiary" size="sm" onClick={onManage} className="ml-auto" data-testid="crm-workflow-manage">Manage</Button>
      </div>
      {wfRuns.length > 0 ? wfRuns.map(run => (
        <div key={run.id} className="flex items-start gap-2 py-1.5" style={{ borderBottom: `1px solid ${isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-neutral-100)'}` }}>
          <Zap size={11} className="mt-0.5 shrink-0" style={{ color: 'var(--color-success-alt)' }} />
          <div className="flex-1 min-w-0">
            <p className="text-xs truncate" style={{ color: c.text }}>{run.workflow_name || 'Workflow'}</p>
            <p className="text-[10px]" style={{ color: c.textDim }}>{run.actions_executed?.length || 0} actions &middot; {timeAgo(run.created_at)} ago</p>
          </div>
          <CheckCircle size={11} style={{ color: 'var(--color-success-alt)' }} />
        </div>
      )) : (
        <p className="text-xs text-center py-4" style={{ color: c.textDim }}>
          No workflow runs yet. <Button variant="tertiary" size="sm" onClick={onManage} data-testid="crm-workflow-setup">Set up</Button>
        </p>
      )}
    </Card>
  );
}

/* ─── CASES BY SEVERITY ─── */
function CasesBySeverity({ data, isDark, c }) {
  const items = [
    { label: 'High', count: data.cases_by_severity?.high || 0, color: 'var(--color-danger-alt)' },
    { label: 'Medium', count: data.cases_by_severity?.medium || 0, color: 'var(--color-accent-amber)' },
    { label: 'Low', count: data.cases_by_severity?.low || 0, color: 'var(--color-success-alt)' },
  ];
  const total = items.reduce((s, i) => s + i.count, 0);
  return (
    <Card isDark={isDark}>
      <div className="flex items-center gap-2 mb-3">
        <AlertCircle size={14} style={{ color: 'var(--color-accent-amber)' }} />
        <h3 className="text-sm font-semibold" style={{ color: c.text }}>Open Cases</h3>
        <span className="ml-auto text-lg font-bold" style={{ color: total > 0 ? 'var(--color-accent-amber)' : 'var(--color-success-alt)' }}>{total}</span>
      </div>
      {total > 0 ? (
        <div className="space-y-2">
          {items.map(item => (
            <div key={item.label} className="flex items-center gap-3">
              <span className="text-xs w-16" style={{ color: c.textMuted }}>{item.label}</span>
              <div className="flex-1 h-4 rounded-sm overflow-hidden" style={{ background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-100)' }}>
                <div className="h-full rounded-sm transition-all" style={{ width: `${total > 0 ? (item.count / total * 100) : 0}%`, background: item.color }} />
              </div>
              <span className="text-xs font-bold w-6 text-right" style={{ color: item.color }}>{item.count}</span>
            </div>
          ))}
        </div>
      ) : <p className="text-xs text-center py-3" style={{ color: c.textDim }}>No open cases</p>}
    </Card>
  );
}

/* ═══════════════════════════════════
   ROLE-BASED DASHBOARD VARIANTS
   ═══════════════════════════════════ */

/* ─── SALES MANAGER / DEFAULT ─── */
function SalesManagerDash({ data, serviceRevenue, tasks, stagnating, wfRuns, isDark, c, navigateTo, setActiveTab }) {
  const kpis = [
    { label: 'Pipeline Value', value: fmt(data.pipeline_value), icon: TrendingUp, color: 'var(--color-info-ios)', sub: `${data.active_opportunities} active`, click: () => setActiveTab('pipeline') },
    { label: 'Weighted Forecast', value: fmt(data.weighted_forecast), icon: Target, color: 'var(--color-success-alt)', sub: 'Probability-weighted' },
    { label: 'Won Revenue', value: fmt(data.won_revenue), icon: DollarSign, color: 'var(--color-success-ios)', sub: `${data.win_rate}% win rate` },
    { label: 'Service Revenue YTD', value: fmt(serviceRevenue?.total_net), icon: Wrench, color: 'var(--color-accent-violet)', sub: `${serviceRevenue?.invoice_count || 0} invoices` },
    { label: 'Open Cases', value: data.open_cases, icon: AlertTriangle, color: data.open_cases > 0 ? 'var(--color-accent-amber)' : 'var(--color-success-alt)', sub: 'Service' },
    { label: 'Tasks Due', value: data.tasks_due, icon: CheckCircle, color: data.tasks_due > 0 ? 'var(--color-danger-alt)' : 'var(--color-success-alt)', sub: 'Incomplete', click: () => setActiveTab('inbox') },
  ];
  return (
    <div className="space-y-5">
      <KPIRow kpis={kpis} isDark={isDark} c={c} />
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2"><PipelineByStage data={data} isDark={isDark} c={c} onViewAll={() => setActiveTab('pipeline')} /></div>
        <div className="space-y-4">
          <TasksDue tasks={tasks} isDark={isDark} c={c} onViewAll={() => setActiveTab('inbox')} />
          <Card isDark={isDark}>
            <h3 className="text-sm font-semibold mb-3" style={{ color: c.text }}>Quick Stats</h3>
            <div className="space-y-2.5">
              {[
                { l: 'Win rate', v: `${data.win_rate}%`, col: data.win_rate >= 50 ? 'var(--color-success-alt)' : 'var(--color-accent-amber)' },
                { l: 'Companies', v: data.total_companies, col: c.text },
                { l: 'Assets', v: data.total_assets, col: c.text },
              ].map(s => (
                <div key={s.l} className="flex items-center justify-between">
                  <span className="text-xs" style={{ color: c.textMuted }}>{s.l}</span>
                  <span className="text-sm font-bold" style={{ color: s.col }}>{s.v}</span>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <StagnatingDeals deals={stagnating} isDark={isDark} c={c} navigateTo={navigateTo} />
        <WorkflowActivity wfRuns={wfRuns} isDark={isDark} c={c} onManage={() => setActiveTab('workflows')} />
        <RecentActivity activities={data.recent_activities} isDark={isDark} c={c} onViewAll={() => setActiveTab('inbox')} />
      </div>
    </div>
  );
}

/* ─── SERVICE ADMIN ─── */
function ServiceAdminDash({ data, tasks, wfRuns, isDark, c, setActiveTab }) {
  const kpis = [
    { label: 'Open Cases', value: data.open_cases, icon: AlertTriangle, color: 'var(--color-accent-amber)', sub: 'Active service tickets' },
    { label: 'High Severity', value: data.cases_by_severity?.high || 0, icon: AlertCircle, color: 'var(--color-danger-alt)', sub: 'Urgent' },
    { label: 'Assets', value: data.total_assets, icon: Wrench, color: 'var(--color-info-ios)', sub: 'Installed base' },
    { label: 'Tasks Due', value: data.tasks_due, icon: CheckCircle, color: data.tasks_due > 0 ? 'var(--color-danger-alt)' : 'var(--color-success-alt)', sub: 'Overdue', click: () => setActiveTab('inbox') },
    { label: 'Companies', value: data.total_companies, icon: Building2, color: 'var(--color-accent-magenta)', sub: 'Served', click: () => setActiveTab('companies') },
    { label: 'Contacts', value: data.total_contacts, icon: Users, color: 'var(--color-accent-indigo)', sub: 'Total' },
  ];
  return (
    <div className="space-y-5">
      <KPIRow kpis={kpis} isDark={isDark} c={c} />
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <CasesBySeverity data={data} isDark={isDark} c={c} />
        <TasksDue tasks={tasks} isDark={isDark} c={c} onViewAll={() => setActiveTab('inbox')} />
        <WorkflowActivity wfRuns={wfRuns} isDark={isDark} c={c} onManage={() => setActiveTab('workflows')} />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <RecentActivity activities={data.recent_activities} isDark={isDark} c={c} onViewAll={() => setActiveTab('inbox')} />
        <PipelineByStage data={data} isDark={isDark} c={c} onViewAll={() => setActiveTab('pipeline')} />
      </div>
    </div>
  );
}

/* ─── ENGINEER ─── */
function EngineerDash({ data, isDark, c, setActiveTab }) {
  const myTasks = data.my_tasks || [];
  const meetings = data.upcoming_meetings || [];
  const kpis = [
    { label: 'My Tasks', value: myTasks.length, icon: CheckCircle, color: myTasks.length > 0 ? 'var(--color-accent-amber)' : 'var(--color-success-alt)', sub: 'Assigned to me', click: () => setActiveTab('inbox') },
    { label: 'Open Cases', value: data.open_cases, icon: AlertTriangle, color: 'var(--color-accent-amber)', sub: 'Active' },
    { label: 'Assets', value: data.total_assets, icon: Wrench, color: 'var(--color-info-ios)', sub: 'In field' },
    { label: 'Meetings', value: meetings.length, icon: Calendar, color: 'var(--color-accent-magenta)', sub: 'Upcoming' },
    { label: 'High Cases', value: data.cases_by_severity?.high || 0, icon: AlertCircle, color: 'var(--color-danger-alt)', sub: 'Urgent' },
    { label: 'Companies', value: data.total_companies, icon: Building2, color: 'var(--color-accent-indigo)', sub: 'Served' },
  ];
  return (
    <div className="space-y-5">
      <KPIRow kpis={kpis} isDark={isDark} c={c} />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* My Tasks */}
        <Card isDark={isDark}>
          <div className="flex items-center gap-2 mb-3">
            <UserCheck size={14} style={{ color: 'var(--color-info-ios)' }} />
            <h3 className="text-sm font-semibold" style={{ color: c.text }}>My Tasks</h3>
          </div>
          {myTasks.length > 0 ? myTasks.slice(0, 8).map(task => (
            <div key={task.id} className="flex items-start gap-2 py-2" style={{ borderBottom: `1px solid ${isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-neutral-100)'}` }}>
              <CheckCircle size={13} className="mt-0.5 shrink-0" style={{ color: task.priority === 'high' ? 'var(--color-danger-alt)' : 'var(--color-accent-amber)' }} />
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium truncate" style={{ color: c.text }}>{task.subject}</p>
                {task.body && <p className="text-[10px] truncate mt-0.5" style={{ color: c.textDim }}>{task.body}</p>}
              </div>
              {task.due_date && <span className="text-[10px] shrink-0" style={{ color: c.textDim }}>{new Date(task.due_date).toLocaleDateString('en-GB')}</span>}
            </div>
          )) : <p className="text-xs text-center py-6" style={{ color: c.textDim }}>No tasks assigned</p>}
        </Card>
        {/* Cases + Activity */}
        <div className="space-y-4">
          <CasesBySeverity data={data} isDark={isDark} c={c} />
          <RecentActivity activities={data.recent_activities} isDark={isDark} c={c} onViewAll={() => setActiveTab('inbox')} />
        </div>
      </div>
    </div>
  );
}

/* ─── DIRECTOR ─── */
function DirectorDash({ data, serviceRevenue, stagnating, wfRuns, isDark, c, navigateTo, setActiveTab }) {
  const kpis = [
    { label: 'Pipeline Value', value: fmt(data.pipeline_value), icon: TrendingUp, color: 'var(--color-info-ios)', sub: `${data.active_opportunities} deals`, click: () => setActiveTab('pipeline') },
    { label: 'Weighted Forecast', value: fmt(data.weighted_forecast), icon: Target, color: 'var(--color-success-alt)', sub: 'Expected revenue' },
    { label: 'Won Revenue', value: fmt(data.won_revenue), icon: DollarSign, color: 'var(--color-success-ios)', sub: `${data.won_count || 0} deals won` },
    { label: 'Service Revenue YTD', value: fmt(serviceRevenue?.total_net), icon: Wrench, color: 'var(--color-accent-violet)', sub: `${serviceRevenue?.invoice_count || 0} invoices` },
    { label: 'Win Rate', value: `${data.win_rate}%`, icon: Award, color: data.win_rate >= 50 ? 'var(--color-success-alt)' : 'var(--color-accent-amber)', sub: `${data.lost_count || 0} lost` },
    { label: 'Open Cases', value: data.open_cases, icon: AlertTriangle, color: 'var(--color-accent-amber)', sub: 'Service backlog' },
  ];
  return (
    <div className="space-y-5">
      <KPIRow kpis={kpis} isDark={isDark} c={c} />
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2"><PipelineByStage data={data} isDark={isDark} c={c} onViewAll={() => setActiveTab('pipeline')} /></div>
        <div className="space-y-4">
          {/* Conversion funnel */}
          <Card isDark={isDark}>
            <div className="flex items-center gap-2 mb-3">
              <PieChart size={14} style={{ color: 'var(--color-info-ios)' }} />
              <h3 className="text-sm font-semibold" style={{ color: c.text }}>Conversion</h3>
            </div>
            <div className="space-y-2.5">
              {[
                { l: 'Win Rate', v: `${data.win_rate}%`, col: data.win_rate >= 50 ? 'var(--color-success-alt)' : 'var(--color-accent-amber)' },
                { l: 'Deals Won', v: data.won_count || 0, col: 'var(--color-success-alt)' },
                { l: 'Deals Lost', v: data.lost_count || 0, col: 'var(--color-danger-alt)' },
                { l: 'Active Pipeline', v: data.active_opportunities, col: 'var(--color-info-ios)' },
                { l: 'Avg Deal Size', v: data.active_opportunities > 0 ? fmt(data.pipeline_value / data.active_opportunities) : '£0', col: c.text },
              ].map(s => (
                <div key={s.l} className="flex items-center justify-between">
                  <span className="text-xs" style={{ color: c.textMuted }}>{s.l}</span>
                  <span className="text-sm font-bold" style={{ color: s.col }}>{s.v}</span>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <StagnatingDeals deals={stagnating} isDark={isDark} c={c} navigateTo={navigateTo} />
        <CasesBySeverity data={data} isDark={isDark} c={c} />
        <WorkflowActivity wfRuns={wfRuns} isDark={isDark} c={c} onManage={() => setActiveTab('workflows')} />
      </div>
    </div>
  );
}

/* ═══ MAIN DASHBOARD ═══ */
export default function CRMDashboard() {
  const { API, headers, c, isDark, setActiveTab, navigateTo, user, setStaffFilter: ctxSetStaffFilter } = useCRM();
  const [data, setData] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [stagnating, setStagnating] = useState([]);
  const [wfRuns, setWfRuns] = useState([]);
  const [serviceRevenue, setServiceRevenue] = useState(null);
  const [loading, setLoading] = useState(true);
  // Toolbar staff filter is the source of truth; the dashboard only needs
  // a setter to default managers/owners to "All Staff" on first mount.
  const [localStaff, setLocalStaff] = useState('mine');
  const setStaffFilter = ctxSetStaffFilter ?? setLocalStaff;

  const isManagerOrOwner = ['admin', 'owner', 'manager', 'director'].includes(user?.role);

  const load = useCallback(async () => {
    try {
      const [dashRes, taskRes] = await Promise.all([
        axios.get(`${API}/crm/v2/dashboard`, { headers: headers() }),
        axios.get(`${API}/crm/v2/activities?type=task&limit=15`, { headers: headers() }),
      ]);
      setData(dashRes.data);
      setTasks(taskRes.data.activities.filter(t => !t.completed_at));
      setStagnating(dashRes.data.stagnating_deals || []);
      // Iter 216h152 — service revenue YTD tile (best-effort).
      try {
        const srRes = await axios.get(`${API}/crm/v2/service-revenue/ytd`, { headers: headers() });
        setServiceRevenue(srRes.data);
      } catch (e) { /* non-critical */ }
      try {
        const wfRes = await axios.get(`${API}/crm/v2/workflows`, { headers: headers() });
        const allRuns = [];
        for (const wf of (wfRes.data.workflows || []).slice(0, 5)) {
          if (wf.execution_count > 0) {
            const runsRes = await axios.get(`${API}/crm/v2/workflows/${wf.id}/runs?limit=3`, { headers: headers() });
            allRuns.push(...(runsRes.data.runs || []).map(r => ({ ...r, workflow_name: wf.name })));
          }
        }
        allRuns.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
        setWfRuns(allRuns.slice(0, 5));
      } catch (e) { /* non-critical */ }
    } catch (e) { console.error(e); }
    setLoading(false);
  }, [API, headers]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (isManagerOrOwner) setStaffFilter('all'); }, [isManagerOrOwner]);  // eslint-disable-line react-hooks/exhaustive-deps

  if (loading || !data) return (
    <div className="flex items-center justify-center h-64">
      <div className="w-5 h-5 border-2 border-[var(--color-info-ios)] border-t-transparent rounded-full animate-spin" />
    </div>
  );

  return (
    <div data-testid="crm-v2-dashboard">
      <SalesManagerDash data={data} serviceRevenue={serviceRevenue} tasks={tasks} stagnating={stagnating} wfRuns={wfRuns} isDark={isDark} c={c} navigateTo={navigateTo} setActiveTab={setActiveTab} />
    </div>
  );
}
