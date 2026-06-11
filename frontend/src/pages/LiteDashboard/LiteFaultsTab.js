import { useState } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { AlertCircle, AlertTriangle, Calendar, ExternalLink, ChevronDown, ChevronRight, CheckCircle, Layers } from 'lucide-react';
import IssueDetailPanel from '../IssueDetailPanel';
import PPMSubTab from '../PPMSubTab';
import { useAuth } from '@/App';
import { useTranslation } from 'react-i18next';
import PageHeader from '@/components/shared/PageHeader';
import EmptyState from '@/components/shared/EmptyState';
import { groupIssuesByJob } from './groupIssuesByJob';

const STATUS_BORDER_COLOR = {
  open: 'var(--color-danger)',           // Red
  in_progress: 'var(--color-warning)',    // Orange/Amber
  resolved: 'var(--color-success-alt-2)',       // Green
};

const LiteFaultsTab = ({
  filteredIssues, faultFilterStatus, faultFilterSeverity,
  selectedIssue, onSelectIssue,
  onLogFault, onFilterStatus, onFilterSeverity,
  onUpdateIssueStatus, suppliers = [],
  getSeverityStyle, getSeverityLabel, getStatusColor
}) => {
  const [faultView, setFaultView] = useState('reactive');
  // Iter 216d — multi-machine fault jobs collapse into a single
  // expandable parent row by default; the user clicks to fan out.
  const [expandedJobs, setExpandedJobs] = useState({});
  const toggleJob = (jobId) =>
    setExpandedJobs(prev => ({ ...prev, [jobId]: !prev[jobId] }));
  const { user } = useAuth();
  const { t } = useTranslation();
  const ppmEnabled = user?.features?.ppm_engine !== false;

  // Reusable single-issue card body (also rendered as children of an
  // expanded job group). Extracted as a thunk so the JSX below stays
  // readable without yet another component file.
  const renderIssueCard = (issue, opts = {}) => (
    <Card key={issue.id} className="overflow-hidden" style={{ background: 'var(--theme-surface, var(--color-surface-dark-alt))', borderLeft: `4px solid ${STATUS_BORDER_COLOR[issue.status] || 'var(--color-text-faint-alt)'}`, borderColor: STATUS_BORDER_COLOR[issue.status] || 'var(--theme-border, rgba(255,255,255,0.1))' }} data-testid={`issue-card-${issue.id}`}>
      <div className="p-5 cursor-pointer hover:bg-white/[0.02] transition-colors" onClick={() => onSelectIssue(selectedIssue?.id === issue.id ? null : issue)}>
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <div className="flex items-center flex-wrap gap-2 mb-2">
              <h3 className={`font-semibold text-white ${opts.nested ? 'text-base' : 'text-lg'}`}>{issue.serial_number}</h3>
              <Badge className={getSeverityStyle(issue.severity)} data-testid={`issue-severity-${issue.id}`}>{getSeverityLabel(issue.severity)}</Badge>
              <Badge className={getStatusColor(issue.status)} data-testid={`issue-status-${issue.id}`}>{t(`status.${issue.status}`, issue.status === 'in_progress' ? 'In Progress' : (issue.status?.charAt(0).toUpperCase() + issue.status?.slice(1)))}</Badge>
              {issue.supplier_case?.supplier_name && (
                <Badge className="bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 inline-flex items-center gap-1" data-testid={`issue-supplier-sent-${issue.id}`} title={`Fault sent to ${issue.supplier_case.supplier_name}${issue.supplier_case.supplier_email ? ` (${issue.supplier_case.supplier_email})` : ''}`}>
                  <CheckCircle size={11} /> {t('faults.sent_to', 'Sent to')} {issue.supplier_case.supplier_name}
                </Badge>
              )}
            </div>
            <p className="text-[var(--color-text-muted)] text-sm">{issue.machine_type}{issue.supplier ? ` | ${issue.supplier}` : ''} | {issue.created_at ? new Date(issue.created_at).toLocaleDateString() : ''}{issue.supplier_ref ? ` | Ref: ${issue.supplier_ref}` : ''}</p>
            <p className="text-white text-sm mt-1">{issue.issue_description?.substring(0, 100)}{issue.issue_description?.length > 100 ? '...' : ''}</p>
            {issue.sicon_case_id && (
              <div className="flex items-center flex-wrap gap-x-3 gap-y-1 mt-2 text-[11px]" data-testid={`job-card-summary-${issue.id}`}>
                <span className="inline-flex items-center gap-1 text-[var(--color-brand-blue)]">
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="8" y="2" width="8" height="4" rx="1" ry="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/></svg>
                  <span className="font-semibold">Job Card</span>
                  <span className="font-mono text-[var(--color-text-muted)]">{issue.sicon_case_number || `#${issue.sicon_case_id}`}</span>
                </span>
                {issue.sicon_assigned_to && <span className="text-[var(--color-text-muted)]">· <span className="text-white">{issue.sicon_assigned_to}</span></span>}
                {(() => {
                  const next = (issue.sicon_appointments || []).find(a => !a.appointment_complete) || (issue.sicon_appointments || []).slice(-1)[0];
                  return next?.scheduled_start ? (
                    <span className="text-[var(--color-text-muted)]">· <span className="text-white">{new Date(next.scheduled_start).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })} {new Date(next.scheduled_start).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}</span></span>
                  ) : null;
                })()}
                {issue.sicon_status && <Badge className="bg-[rgb(var(--rgb-brand-blue)/0.15)] text-[var(--color-brand-blue)] text-[9px] border border-[rgb(var(--rgb-brand-blue)/0.3)] px-1.5 py-0">{issue.sicon_status}</Badge>}
              </div>
            )}
            {issue.supplier_case?.scheduled_date && !issue.sicon_case_id && (
              <div className="flex items-center gap-2 mt-2">
                <Badge className="bg-purple-500/20 text-purple-400 text-[10px]">
                  {t('faults.engineer', 'Engineer')}: {new Date(issue.supplier_case.scheduled_date).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}
                </Badge>
              </div>
            )}
            {issue.supplier_case?.token && (
              <div className="mt-2" onClick={(e) => e.stopPropagation()}>
                <button
                  type="button"
                  onClick={() => window.open(`/supplier/case/${issue.supplier_case.token}`, '_blank', 'noopener')}
                  className="inline-flex items-center gap-1.5 text-[11px] font-medium text-[var(--color-brand-cyan-hover)] hover:text-white hover:underline transition-colors"
                  data-testid={`supplier-card-link-${issue.id}`}
                  title="See exactly what the supplier sees for this job"
                >
                  <ExternalLink size={11} /> {t('faults.view_supplier_card', 'View supplier card')}
                </button>
              </div>
            )}
          </div>
          <div className="flex items-center gap-2 ml-4" onClick={(e) => e.stopPropagation()}>
            {issue.status === 'open' && (
              <Button size="sm" onClick={() => onUpdateIssueStatus(issue.id, 'in_progress')} className="bg-yellow-500 hover:bg-yellow-600 text-white text-xs" data-testid={`issue-progress-btn-${issue.id}`}>{t('status.in_progress', 'In Progress')}</Button>
            )}
            {issue.status === 'in_progress' && (
              <Button size="sm" onClick={() => onUpdateIssueStatus(issue.id, 'resolved')} className="bg-green-500 hover:bg-green-600 text-white text-xs" data-testid={`issue-resolve-btn-${issue.id}`}>{t('status.resolved', 'Resolved')}</Button>
            )}
            {issue.status === 'resolved' && (
              <Badge className="bg-green-500/20 text-green-400 text-xs">{t('status.closed', 'Closed')}</Badge>
            )}
          </div>
        </div>
      </div>
      {selectedIssue?.id === issue.id && (
        <IssueDetailPanel issue={issue} onUpdate={onUpdateIssueStatus} suppliers={suppliers} />
      )}
    </Card>
  );

  return (
    <div className="space-y-4">
      <PageHeader
        title={t('dashboard.faults', 'Faults')}
        subtitle={t('faults.subtitle', 'Reactive faults and planned maintenance')}
        icon={AlertCircle}
        helpId={faultView === 'ppm' ? 'service-warranty-tracking' : 'service-log-fault'}
        testId="lite-faults-header"
      />

      {/* Reactive / PPM toggle — uses canonical .subtab-bar/pill,
          identical to GymAxis FaultsTab. */}
      <div className="subtab-bar mb-2" role="tablist">
        <button type="button"
          className={`subtab-pill ${faultView === 'reactive' ? 'is-active' : ''}`}
          onClick={() => setFaultView('reactive')} data-testid="lite-faults-view-reactive">
          <AlertCircle size={14} /> {t('faults.reactive', 'Reactive Faults')}
        </button>
        {ppmEnabled && (
          <button type="button"
            className={`subtab-pill ${faultView === 'ppm' ? 'is-active' : ''}`}
            onClick={() => setFaultView('ppm')} data-testid="lite-faults-view-ppm">
            <Calendar size={14} /> {t('faults.ppm', 'Planned Maintenance (PPM)')}
          </button>
        )}
      </div>

      {faultView === 'ppm' && ppmEnabled && <PPMSubTab />}

      {faultView === 'reactive' && (
      <>
      <div className="flex flex-col sm:flex-row gap-3">
        <Button onClick={onLogFault} className="bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white" data-testid="log-fault-btn">
          <AlertCircle className="mr-2" size={18} /> {t('faults.log_new', 'Log New Fault')}
        </Button>
        <Select value={faultFilterStatus} onValueChange={onFilterStatus}>
          <SelectTrigger className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] w-full sm:w-48" data-testid="fault-filter-status">
            <SelectValue placeholder={t('status.all_statuses', 'All Statuses')} />
          </SelectTrigger>
          <SelectContent className="bg-[var(--theme-surface)] border-[var(--theme-border)]">
            <SelectItem value="all" className="text-white">{t('status.all_statuses', 'All Statuses')}</SelectItem>
            <SelectItem value="open" className="text-white">{t('status.open', 'Open')}</SelectItem>
            <SelectItem value="in_progress" className="text-white">{t('status.in_progress', 'In Progress')}</SelectItem>
            <SelectItem value="resolved" className="text-white">{t('status.resolved', 'Resolved')}</SelectItem>
          </SelectContent>
        </Select>
        <Select value={faultFilterSeverity} onValueChange={onFilterSeverity}>
          <SelectTrigger className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] w-full sm:w-48" data-testid="fault-filter-severity">
            <SelectValue placeholder={t('status.all_severities', 'All Severities')} />
          </SelectTrigger>
          <SelectContent className="bg-[var(--theme-surface)] border-[var(--theme-border)]">
            <SelectItem value="all" className="text-white">{t('status.all_severities', 'All Severities')}</SelectItem>
            <SelectItem value="operational_minor" className="text-white">{t('severity.operational_minor', 'Minor Issue')}</SelectItem>
            <SelectItem value="operational_fault" className="text-white">{t('severity.operational_fault', 'Fault Present')}</SelectItem>
            <SelectItem value="limited_use" className="text-white">{t('severity.limited_use', 'Limited Use')}</SelectItem>
            <SelectItem value="out_of_order" className="text-white">{t('severity.out_of_order', 'Out of Order')}</SelectItem>
            <SelectItem value="safety_critical" className="text-white">{t('severity.safety_critical', 'Safety Critical')}</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Fault List — iter 216d: grouped by job_id with expandable parent rows. */}
      <div className="grid grid-cols-1 gap-4">
        {groupIssuesByJob(filteredIssues).map(row => {
          if (row.type === 'single') return renderIssueCard(row.issue);
          // Job parent row — collapsible. Shows aggregate progress; the
          // user expands to operate on individual machines (each child
          // keeps its own SLA + Resolve button).
          const jobId = row.job_id;
          const open = !!expandedJobs[jobId];
          const parent = row.primary;
          return (
            <Card
              key={`job-${jobId}`}
              className="overflow-hidden"
              style={{
                background: 'var(--theme-surface, var(--color-surface-dark-alt))',
                borderLeft: `4px solid ${row.all_resolved ? 'var(--color-success-alt-2)' : 'var(--color-brand-blue)'}`,
                borderColor: 'var(--theme-border, rgba(255,255,255,0.1))',
              }}
              data-testid={`job-card-${jobId}`}
            >
              <button
                type="button"
                onClick={() => toggleJob(jobId)}
                className="w-full text-left p-5 hover:bg-white/[0.02] transition-colors"
                data-testid={`job-toggle-${jobId}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center flex-wrap gap-2 mb-1">
                      {open
                        ? <ChevronDown size={16} className="text-[var(--color-brand-cyan-hover)] shrink-0" />
                        : <ChevronRight size={16} className="text-[var(--color-brand-cyan-hover)] shrink-0" />}
                      <Layers size={14} className="text-[var(--color-brand-cyan-hover)] shrink-0" />
                      <h3 className="text-base font-semibold text-white">
                        {t('faults.multi_job', 'Multi-machine fault job')}
                      </h3>
                      <Badge
                        className={
                          row.all_resolved
                            ? 'bg-green-500/20 text-green-400 text-xs'
                            : 'bg-[rgb(var(--rgb-brand-blue)/0.15)] text-[var(--color-brand-blue)] text-xs border border-[rgb(var(--rgb-brand-blue)/0.3)]'
                        }
                        data-testid={`job-progress-${jobId}`}
                      >
                        {row.all_resolved
                          ? <><CheckCircle size={11} className="inline mr-1" /> {t('faults.all_fixed', { count: row.issues.length, defaultValue: 'All {{count}} fixed' })}</>
                          : t('faults.of_fixed', { done: row.resolved_count, total: row.issues.length, defaultValue: '{{done}} of {{total}} fixed' })}
                      </Badge>
                    </div>
                    <p className="text-[var(--color-text-muted)] text-xs">
                      {parent.machine_type}{parent.supplier ? ` · ${parent.supplier}` : ''}
                      {parent.created_at ? ` · ${t('faults.logged', 'Logged')} ${new Date(parent.created_at).toLocaleDateString()}` : ''}
                    </p>
                    <p className="text-white text-sm mt-1 truncate">
                      {parent.issue_description?.substring(0, 100)}{parent.issue_description?.length > 100 ? '…' : ''}
                    </p>
                    <p className="text-[var(--color-text-muted)] text-xs mt-1">
                      {t('faults.job_id', 'Job ID')} <span className="font-mono">{jobId.slice(0, 8)}</span> · {open ? t('faults.click_collapse', 'click to collapse') : t('faults.click_expand', 'click to expand')}
                    </p>
                  </div>
                </div>
              </button>
              {open && (
                <div className="border-t border-[var(--theme-border,rgba(255,255,255,0.1))] bg-black/20 p-3 space-y-3" data-testid={`job-children-${jobId}`}>
                  {row.issues.map(child => renderIssueCard(child, { nested: true }))}
                </div>
              )}
            </Card>
          );
        })}
        {filteredIssues.length === 0 && (() => {
          const filtersActive = (faultFilterStatus && faultFilterStatus !== 'all') || (faultFilterSeverity && faultFilterSeverity !== 'all');
          return filtersActive ? (
            <EmptyState
              icon={AlertTriangle}
              title={t('faults.no_match_title', 'No faults match these filters')}
              hint={t('faults.no_match_hint', 'Try clearing one filter — or switch to Planned Maintenance to see PPM jobs.')}
              testId="lite-faults-filter-empty"
            />
          ) : (
            <EmptyState
              icon={AlertCircle}
              title={t('faults.empty_title', 'No faults logged — nice')}
              hint={t('faults.empty_hint', 'When equipment goes down, log a fault here so the right engineer is auto-paged and the timeline is captured for compliance.')}
              primaryAction={{ label: t('faults.log_first', 'Log first fault'), onClick: onLogFault, testId: 'lite-faults-empty-log' }}
              testId="lite-faults-empty-state"
            />
          );
        })()}
      </div>
      </>
      )}
    </div>
  );
};

export default LiteFaultsTab;
