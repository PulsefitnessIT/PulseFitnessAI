import React from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { AlertCircle, CheckCircle, Clock, MessageSquare, Upload, Shield } from 'lucide-react';

const OverviewTab = ({
 healthScore, issues, auditHistory, maintenanceTasks,
 urgentExpiryAlerts, onLogIssue, onNavigateTab, onViewExpiryAlerts,
 getStatusColor, t
}) => {
 return (
 <>
 {/* Iter 216c — `<ActivationMilestonesCard />` moved to the Start tab
     (`OperationsStartTab`). Once every milestone fires, Start auto-hides
     and Dashboard becomes the default first tab. */}

 {/* Log Issue CTA at top */}
 <div className="mb-6">
 <Button onClick={onLogIssue} className="px-6 py-3 text-base" data-testid="overview-log-issue-btn">
 <AlertCircle className="mr-2" size={20} />
 {t('faults.log_fault')}
 </Button>
 </div>

 {/* Expiry Alerts Banner */}
 {urgentExpiryAlerts.length > 0 && (
 <div className="mb-6 p-4 bg-amber-500/10 border border-amber-500/30 rounded-lg flex items-center justify-between" data-testid="overview-expiry-banner">
 <div className="flex items-center gap-3">
 <Shield size={20} className="text-amber-400" />
 <div>
 <p className="text-amber-400 font-semibold text-sm">
 {t('dashboard.machines_expiring', { count: urgentExpiryAlerts.length })}
 </p>
 <p className="text-[var(--color-text-muted)] text-xs">
 {urgentExpiryAlerts.map(a => `${a.equipment_name} (${a.days_remaining}d)`).join(', ')}
 </p>
 </div>
 </div>
 <Button size="sm" variant="outline" className="border-amber-500/30 text-amber-400 hover:bg-amber-500/10" onClick={onViewExpiryAlerts} data-testid="view-expiry-alerts-btn">
 {t('dashboard.view_alerts')}
 </Button>
 </div>
 )}

 <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
 {/* Gym Health Score Widget — shows a gated placeholder until onboarding is complete */}
 {healthScore?.not_ready ? (
 <Card
 className="bg-[var(--theme-surface)] border-[var(--theme-border)] p-6 md:row-span-2 flex flex-col"
 data-testid="gym-health-score-not-ready"
 >
 <h3 className="text-lg font-semibold text-white mb-4">{t('dashboard.gym_health_score')}</h3>
 <div className="flex-1 flex flex-col items-center justify-center text-center py-6">
 <div className="w-28 h-28 rounded-full border-2 border-dashed border-[var(--theme-border)] flex items-center justify-center mb-4">
 <span className="text-[var(--color-text-muted)] text-xs px-3">Awaiting data</span>
 </div>
 <p className="text-white text-sm font-medium mb-1">Score not available yet</p>
 <p className="text-[var(--color-text-muted)] text-xs leading-snug max-w-[220px] mb-4">
 {healthScore.message ||"Your Gym Health Score will be calculated once you've added equipment and started logging activity."}
 </p>
 <button
 type="button"
 onClick={() => onNavigateTab('equipment')}
 className="text-xs text-[var(--color-brand-blue)] hover:underline font-medium"
 data-testid="gym-health-score-start-onboarding"
 >
 Start by adding your equipment →
 </button>
 </div>
 </Card>
 ) : healthScore && (
 <Card className="bg-[var(--theme-surface)] border-[var(--theme-border)] p-6 md:row-span-2" data-testid="gym-health-score">
 <h3 className="text-lg font-semibold text-white mb-4">{t('dashboard.gym_health_score')}</h3>
 <div className="flex flex-col items-center mb-4">
 <div className="relative w-28 h-28">
 <svg viewBox="0 0 36 36" className="w-28 h-28 -rotate-90">
 <circle cx="18" cy="18" r="15.915" fill="none" stroke="var(--color-surface-dark-2)" strokeWidth="3" />
 <circle cx="18" cy="18" r="15.915" fill="none" stroke={healthScore.color} strokeWidth="3"
 strokeDasharray={`${healthScore.score} ${100 - healthScore.score}`} strokeLinecap="round" />
 </svg>
 <div className="absolute inset-0 flex flex-col items-center justify-center">
 <span className="text-3xl font-bold text-white">{healthScore.score}</span>
 <span className="text-xs" style={{ color: healthScore.color }}>{healthScore.rating}</span>
 </div>
 </div>
 </div>
 <div className="space-y-2">
 {Object.entries(healthScore.breakdown || {}).map(([key, val]) => (
 <div key={key}>
 <div className="flex justify-between text-xs mb-0.5">
 <span className="text-[var(--color-text-muted)] capitalize">{key.replace(/_/g, ' ')}</span>
 <span className="text-white">{val.score}/{val.max}</span>
 </div>
 <div className="w-full bg-[var(--theme-surface)] rounded-full h-1.5">
 <div className="h-1.5 rounded-full transition-all" style={{ width: `${(val.score / val.max) * 100}%`, backgroundColor: healthScore.color }} />
 </div>
 </div>
 ))}
 </div>
 </Card>
 )}

 <Card className="bg-[var(--theme-surface)] border-[var(--theme-border)] p-6 cursor-pointer hover:border-[rgb(var(--rgb-brand-blue)/0.5)] transition-colors" data-testid="stat-issues" onClick={() => onNavigateTab('issues')}>
 <div className="flex items-center justify-between">
 <div>
 <p className="text-[var(--color-text-muted)] text-sm">{t('dashboard.open_faults')}</p>
 <p className="text-3xl font-bold text-white mt-2">{issues.filter(i => i.status === 'open').length}</p>
 </div>
 <AlertCircle className="text-[var(--color-brand-blue)]" size={32} />
 </div>
 </Card>

 <Card className="bg-[var(--theme-surface)] border-[var(--theme-border)] p-6 cursor-pointer hover:border-[rgb(var(--rgb-brand-blue)/0.5)] transition-colors" data-testid="stat-audits" onClick={() => onNavigateTab('equipment')}>
 <div className="flex items-center justify-between">
 <div>
 <p className="text-[var(--color-text-muted)] text-sm">{t('dashboard.audits_completed')}</p>
 <p className="text-3xl font-bold text-white mt-2">{auditHistory.length}</p>
 </div>
 <CheckCircle className="text-[var(--color-brand-blue)]" size={32} />
 </div>
 </Card>

 <Card className="bg-[var(--theme-surface)] border-[var(--theme-border)] p-6 cursor-pointer hover:border-[rgb(var(--rgb-brand-blue)/0.5)] transition-colors" data-testid="stat-tasks" onClick={() => onNavigateTab('maintenance')}>
 <div className="flex items-center justify-between">
 <div>
 <p className="text-[var(--color-text-muted)] text-sm">{t('dashboard.maintenance_tasks')}</p>
 <p className="text-3xl font-bold text-white mt-2">{maintenanceTasks.length}</p>
 </div>
 <Clock className="text-[var(--color-brand-blue)]" size={32} />
 </div>
 </Card>
 </div>

 {/* Charts Row */}
 <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
 <Card className="bg-[var(--theme-surface)] border-[var(--theme-border)] p-6" data-testid="issue-status-chart">
 <h3 className="text-lg font-semibold text-white mb-4">{t('dashboard.issue_status')}</h3>
 {issues.length > 0 ? (
 <div className="flex items-center gap-8">
 <div className="relative w-32 h-32">
 <svg viewBox="0 0 36 36" className="w-32 h-32 -rotate-90">
 {(() => {
 const open = issues.filter(i => i.status === 'open').length;
 const inProgress = issues.filter(i => i.status === 'in_progress').length;
 const total = issues.length || 1;
 const openDash = (open / total) * 100;
 const progressDash = (inProgress / total) * 100;
 const resolvedDash = ((issues.length - open - inProgress) / total) * 100;
 return (
 <>
 <circle cx="18" cy="18" r="15.915" fill="none" stroke="var(--color-ink-navy)" strokeWidth="3" />
 <circle cx="18" cy="18" r="15.915" fill="none" stroke="var(--color-danger)" strokeWidth="3" strokeDasharray={`${openDash} ${100 - openDash}`} strokeDashoffset="0" />
 <circle cx="18" cy="18" r="15.915" fill="none" stroke="var(--color-yellow)" strokeWidth="3" strokeDasharray={`${progressDash} ${100 - progressDash}`} strokeDashoffset={`${-openDash}`} />
 <circle cx="18" cy="18" r="15.915" fill="none" stroke="var(--color-success-alt-2)" strokeWidth="3" strokeDasharray={`${resolvedDash} ${100 - resolvedDash}`} strokeDashoffset={`${-(openDash + progressDash)}`} />
 </>
 );
 })()}
 </svg>
 <div className="absolute inset-0 flex items-center justify-center">
 <span className="text-2xl font-bold text-white">{issues.length}</span>
 </div>
 </div>
 <div className="space-y-2">
 <div className="flex items-center gap-2"><span className="w-3 h-3 rounded-full bg-red-500"></span><span className="text-[var(--color-text-muted)] text-sm">{t('faults.open')} ({issues.filter(i => i.status === 'open').length})</span></div>
 <div className="flex items-center gap-2"><span className="w-3 h-3 rounded-full bg-yellow-500"></span><span className="text-[var(--color-text-muted)] text-sm">{t('faults.in_progress')} ({issues.filter(i => i.status === 'in_progress').length})</span></div>
 <div className="flex items-center gap-2"><span className="w-3 h-3 rounded-full bg-green-500"></span><span className="text-[var(--color-text-muted)] text-sm">{t('faults.resolved')} ({issues.filter(i => i.status === 'resolved').length})</span></div>
 </div>
 </div>
 ) : (
 <p className="text-[var(--color-text-muted)] text-center py-6">{t('dashboard.no_issues_display')}</p>
 )}
 </Card>

 <Card className="bg-[var(--theme-surface)] border-[var(--theme-border)] p-6" data-testid="severity-chart">
 <h3 className="text-lg font-semibold text-white mb-4">{t('dashboard.severity_dist')}</h3>
 {issues.length > 0 ? (
 <div className="space-y-3">
 {[
 { key: 'safety_critical', label: 'Safety Critical', color: 'bg-red-700', legacy: null },
 { key: 'out_of_order', label: 'Out of Order', color: 'bg-red-500', legacy: 'critical' },
 { key: 'limited_use', label: 'Limited Use', color: 'bg-orange-500', legacy: null },
 { key: 'operational_fault', label: 'Operational - Fault Present', color: 'bg-yellow-500', legacy: 'medium' },
 { key: 'operational_minor', label: 'Operational - Minor Issue', color: 'bg-green-500', legacy: 'low' },
 ].map(sev => {
 const count = issues.filter(i => i.severity === sev.key || (sev.legacy && i.severity === sev.legacy)).length;
 const pct = (count / issues.length) * 100;
 return (
 <div key={sev.key}>
 <div className="flex justify-between mb-1">
 <span className="text-[var(--color-text-muted)] text-sm">{sev.label}</span>
 <span className="text-white text-sm font-medium">{count}</span>
 </div>
 <div className="w-full bg-[var(--theme-surface)] rounded-full h-2">
 <div className={`${sev.color} h-2 rounded-full transition-all`} style={{ width: `${pct}%` }}></div>
 </div>
 </div>
 );
 })}
 </div>
 ) : (
 <p className="text-[var(--color-text-muted)] text-center py-6">{t('dashboard.no_issues_display')}</p>
 )}
 </Card>
 </div>

 <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
 <Card className="bg-[var(--theme-surface)] border-[var(--theme-border)] p-6" data-testid="quick-actions-card">
 <h3 className="text-xl font-semibold text-white mb-4">{t('dashboard.quick_actions')}</h3>
 <div className="space-y-3">
 <Button onClick={() => onNavigateTab('diagnosis')} className="w-full justify-start" data-testid="quick-action-diagnosis">
 <MessageSquare className="mr-2" size={18} />{t('diagnosis.title')}
 </Button>
 <Button onClick={() => onNavigateTab('equipment')} variant="outline" className="w-full border-[var(--theme-border)] text-white justify-start hover:bg-white/10" data-testid="quick-action-audit">
 <Upload className="mr-2" size={18} />{t('dashboard.generate_audit')}
 </Button>
 <Button onClick={onLogIssue} variant="outline" className="w-full border-[var(--theme-border)] text-white justify-start hover:bg-white/10" data-testid="quick-action-issue">
 <AlertCircle className="mr-2" size={18} />{t('faults.log_fault')}
 </Button>
 </div>
 </Card>

 <Card className="bg-[var(--theme-surface)] border-[var(--theme-border)] p-6" data-testid="recent-issues-card">
 <h3 className="text-xl font-semibold text-white mb-4">{t('dashboard.recent_issues')}</h3>
 <div className="space-y-3">
 {issues.slice(0, 3).map(issue => (
 <div key={issue.id} className="flex items-center justify-between p-3 bg-[var(--theme-surface)] border border-[var(--theme-border)] rounded-lg cursor-pointer hover:border-[rgb(var(--rgb-brand-blue)/0.5)] transition-colors"
 data-testid={`recent-issue-${issue.id}`} onClick={() => onNavigateTab('issues')}>
 <div className="flex-1">
 <p className="text-white font-medium">{issue.serial_number}</p>
 <p className="text-[var(--color-text-muted)] text-sm">{issue.machine_type}</p>
 </div>
 <Badge className={getStatusColor(issue.status)}>{issue.status}</Badge>
 </div>
 ))}
 {issues.length === 0 && <p className="text-[var(--color-text-muted)] text-center py-4">{t('dashboard.no_issues_yet')}</p>}
 </div>
 </Card>
 </div>
 </>
 );
};

export default OverviewTab;
