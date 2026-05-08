import React, { useState } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { AlertCircle, AlertTriangle, Calendar, ExternalLink } from 'lucide-react';
import IssueDetailPanel from '../IssueDetailPanel';
import PPMSubTab from '../PPMSubTab';
import { useAuth } from '@/App';
import PageHeader from '@/components/shared/PageHeader';

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
  const { user } = useAuth();
  const ppmEnabled = user?.features?.ppm_engine !== false;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Faults"
        subtitle="Reactive faults and planned maintenance"
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
          <AlertCircle size={14} /> Reactive Faults
        </button>
        {ppmEnabled && (
          <button type="button"
            className={`subtab-pill ${faultView === 'ppm' ? 'is-active' : ''}`}
            onClick={() => setFaultView('ppm')} data-testid="lite-faults-view-ppm">
            <Calendar size={14} /> Planned Maintenance (PPM)
          </button>
        )}
      </div>

      {faultView === 'ppm' && ppmEnabled && <PPMSubTab />}

      {faultView === 'reactive' && (
      <>
      <div className="flex flex-col sm:flex-row gap-3">
        <Button onClick={onLogFault} className="bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white" data-testid="log-fault-btn">
          <AlertCircle className="mr-2" size={18} /> Log New Fault
        </Button>
        <Select value={faultFilterStatus} onValueChange={onFilterStatus}>
          <SelectTrigger className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] w-full sm:w-48" data-testid="fault-filter-status">
            <SelectValue placeholder="All Statuses" />
          </SelectTrigger>
          <SelectContent className="bg-[var(--theme-surface)] border-[var(--theme-border)]">
            <SelectItem value="all" className="text-white">All Statuses</SelectItem>
            <SelectItem value="open" className="text-white">Open</SelectItem>
            <SelectItem value="in_progress" className="text-white">In Progress</SelectItem>
            <SelectItem value="resolved" className="text-white">Resolved</SelectItem>
          </SelectContent>
        </Select>
        <Select value={faultFilterSeverity} onValueChange={onFilterSeverity}>
          <SelectTrigger className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] w-full sm:w-48" data-testid="fault-filter-severity">
            <SelectValue placeholder="All Severities" />
          </SelectTrigger>
          <SelectContent className="bg-[var(--theme-surface)] border-[var(--theme-border)]">
            <SelectItem value="all" className="text-white">All Severities</SelectItem>
            <SelectItem value="operational_minor" className="text-white">Minor Issue</SelectItem>
            <SelectItem value="operational_fault" className="text-white">Fault Present</SelectItem>
            <SelectItem value="limited_use" className="text-white">Limited Use</SelectItem>
            <SelectItem value="out_of_order" className="text-white">Out of Order</SelectItem>
            <SelectItem value="safety_critical" className="text-white">Safety Critical</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Fault List */}
      <div className="grid grid-cols-1 gap-4">
        {filteredIssues.map(issue => (
          <Card key={issue.id} className="overflow-hidden" style={{ background: 'var(--theme-surface, var(--color-surface-dark-alt))', borderLeft: `4px solid ${STATUS_BORDER_COLOR[issue.status] || 'var(--color-text-faint-alt)'}`, borderColor: STATUS_BORDER_COLOR[issue.status] || 'var(--theme-border, rgba(255,255,255,0.1))' }} data-testid={`issue-card-${issue.id}`}>
            <div className="p-5 cursor-pointer hover:bg-white/[0.02] transition-colors" onClick={() => onSelectIssue(selectedIssue?.id === issue.id ? null : issue)}>
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center flex-wrap gap-2 mb-2">
                    <h3 className="text-lg font-semibold text-white">{issue.serial_number}</h3>
                    <Badge className={getSeverityStyle(issue.severity)} data-testid={`issue-severity-${issue.id}`}>{getSeverityLabel(issue.severity)}</Badge>
                    <Badge className={getStatusColor(issue.status)} data-testid={`issue-status-${issue.id}`}>{issue.status === 'in_progress' ? 'In Progress' : issue.status?.charAt(0).toUpperCase() + issue.status?.slice(1)}</Badge>
                  </div>
                  <p className="text-[var(--color-text-muted)] text-sm">{issue.machine_type}{issue.supplier ? ` | ${issue.supplier}` : ''} | {issue.created_at ? new Date(issue.created_at).toLocaleDateString() : ''}</p>
                  <p className="text-white text-sm mt-1">{issue.issue_description?.substring(0, 100)}{issue.issue_description?.length > 100 ? '...' : ''}</p>
                  {/* Job Card summary — shown when Sicon-backed */}
                  {issue.sicon_case_id && (
                    <div className="flex items-center flex-wrap gap-x-3 gap-y-1 mt-2 text-[11px]"
                         data-testid={`job-card-summary-${issue.id}`}>
                      <span className="inline-flex items-center gap-1 text-[var(--color-brand-blue)]">
                        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="8" y="2" width="8" height="4" rx="1" ry="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/></svg>
                        <span className="font-semibold">Job Card</span>
                        <span className="font-mono text-[var(--color-text-muted)]">{issue.sicon_case_number || `#${issue.sicon_case_id}`}</span>
                      </span>
                      {issue.sicon_assigned_to && (
                        <span className="text-[var(--color-text-muted)]">· <span className="text-white">{issue.sicon_assigned_to}</span></span>
                      )}
                      {(() => {
                        const next = (issue.sicon_appointments || []).find(a => !a.appointment_complete) || (issue.sicon_appointments || []).slice(-1)[0];
                        return next?.scheduled_start ? (
                          <span className="text-[var(--color-text-muted)]">· <span className="text-white">{new Date(next.scheduled_start).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })} {new Date(next.scheduled_start).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}</span></span>
                        ) : null;
                      })()}
                      {issue.sicon_status && (
                        <Badge className="bg-[rgb(var(--rgb-brand-blue)/0.15)] text-[var(--color-brand-blue)] text-[9px] border border-[rgb(var(--rgb-brand-blue)/0.3)] px-1.5 py-0">{issue.sicon_status}</Badge>
                      )}
                    </div>
                  )}
                  {/* Supplier case quick info (hidden when Job Card present) */}
                  {issue.supplier_case?.scheduled_date && !issue.sicon_case_id && (
                    <div className="flex items-center gap-2 mt-2">
                      <Badge className="bg-purple-500/20 text-purple-400 text-[10px]">
                        Engineer: {new Date(issue.supplier_case.scheduled_date).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}
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
                        <ExternalLink size={11} /> View supplier card
                      </button>
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-2 ml-4" onClick={(e) => e.stopPropagation()}>
                  {issue.status === 'open' && (
                    <Button size="sm" onClick={() => onUpdateIssueStatus(issue.id, 'in_progress')} className="bg-yellow-500 hover:bg-yellow-600 text-white text-xs" data-testid={`issue-progress-btn-${issue.id}`}>
                      In Progress
                    </Button>
                  )}
                  {issue.status === 'in_progress' && (
                    <Button size="sm" onClick={() => onUpdateIssueStatus(issue.id, 'resolved')} className="bg-green-500 hover:bg-green-600 text-white text-xs" data-testid={`issue-resolve-btn-${issue.id}`}>
                      Resolved
                    </Button>
                  )}
                  {issue.status === 'resolved' && (
                    <Badge className="bg-green-500/20 text-green-400 text-xs">Closed</Badge>
                  )}
                </div>
              </div>
            </div>
            {/* Full Detail Panel — same as GymAxis dashboard */}
            {selectedIssue?.id === issue.id && (
              <IssueDetailPanel issue={issue} onUpdate={onUpdateIssueStatus} suppliers={suppliers} />
            )}
          </Card>
        ))}
        {filteredIssues.length === 0 && (
          <Card className="bg-[var(--theme-surface)] border-[var(--theme-border)] p-8 text-center">
            <AlertTriangle size={32} className="text-[var(--color-text-muted)] mx-auto mb-3" />
            <p className="text-[var(--color-text-muted)] text-sm">No faults match your filters</p>
          </Card>
        )}
      </div>
      </>
      )}
    </div>
  );
};

export default LiteFaultsTab;
