import React from 'react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ClipboardCheck } from 'lucide-react';
import RiskAssessmentTab from '../RiskAssessmentTab';
import OperationalReportsTab from '../OperationalReportsTab';
import CapexIntelligenceTab from '../CapexIntelligenceTab';
import KPIPerformanceDashboard from '../KPIPerformanceDashboard';
import AuditDetailPanel from '../AuditDetailPanel';

const ReportsSection = ({
 reportSubTab, onSubTabChange, auditHistory, viewAudit, onViewAudit, user, t
}) => {
 const kpiEnabled = user?.features?.kpi_engine !== false;

 const SubTabBtn = ({ id, label, testId }) => {
 const isActive = reportSubTab === id;
 return (
 <Button
 size="sm"
 variant="outline"
 className={`flex-shrink-0 whitespace-nowrap border ${
 isActive
 ? 'bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] !text-white border-[var(--color-brand-blue)] shadow-sm'
 : 'bg-transparent border-[var(--theme-border)] text-[var(--color-text-muted)] hover:text-[color:var(--theme-text)]'
 }`}
 style={isActive ? { color: '#ffffff' } : undefined}
 onClick={() => onSubTabChange(id)}
 data-testid={testId}
 >{label}</Button>
 );
 };

 return (
 <div className="space-y-8">
 {/* Sub-navigation for report types */}
 <div className="flex items-center gap-2 border-b border-[var(--theme-border)] pb-4 overflow-x-auto scrollbar-hide" style={{ WebkitOverflowScrolling: 'touch' }}>
 {kpiEnabled && <SubTabBtn id="performance" label="Performance KPIs" testId="report-sub-performance" />}
 <SubTabBtn id="operational" label={t('dashboard.operational_reports')} testId="report-sub-operational" />
 <SubTabBtn id="risk" label={t('dashboard.risk_assessments')} testId="report-sub-risk" />
 <SubTabBtn id="audits" label={t('dashboard.machine_audit')} testId="report-sub-audits" />
 {(user?.role === 'owner' || user?.role === 'manager' || user?.is_master_admin) && (
 <SubTabBtn id="capex" label="CAPEX Intelligence" testId="report-sub-capex" />
 )}
 </div>

 {reportSubTab === 'performance' && kpiEnabled && <KPIPerformanceDashboard />}
 {reportSubTab === 'operational' && <OperationalReportsTab />}
 {reportSubTab === 'risk' && <RiskAssessmentTab />}
 {reportSubTab === 'capex' && <CapexIntelligenceTab />}

 {reportSubTab === 'audits' && (
 <div className="space-y-6">
 {auditHistory.length > 0 ? (
 <Card className="bg-[var(--theme-surface)] border-[var(--theme-border)] p-6" data-testid="audit-history-card">
 <h2 className="text-xl font-semibold text-[color:var(--theme-text)] mb-4">{t('dashboard.audit_history_title')}</h2>
 <p className="text-[var(--color-text-muted)] text-sm mb-4">{t('dashboard.audit_history_desc')}</p>
 <div className="space-y-3 max-h-[500px] overflow-y-auto">
 {auditHistory.map(audit => (
 <div key={audit.id} className="p-4 bg-[var(--theme-surface)] border border-[var(--theme-border)] rounded-lg cursor-pointer hover:border-[rgb(var(--rgb-brand-blue)/0.5)] transition-colors"
 data-testid={`audit-${audit.id}`} onClick={() => onViewAudit(audit)}>
 <div className="flex items-start justify-between mb-2">
 <div>
 <p className="text-[color:var(--theme-text)] font-semibold">{audit.equipment_name || audit.equipment_type}</p>
 <p className="text-[var(--color-text-muted)] text-sm">{new Date(audit.created_at).toLocaleDateString()}</p>
 </div>
 <Badge className="bg-[rgb(var(--rgb-brand-blue)/0.2)] text-[var(--color-brand-blue)]">{t('dashboard.view_details')}</Badge>
 </div>
 <p className="text-[var(--color-text-muted)] text-sm">{audit.report?.substring(0, 120)}...</p>
 </div>
 ))}
 </div>
 </Card>
 ) : (
 <Card className="bg-[var(--theme-surface)] border-[var(--theme-border)] p-12 text-center" data-testid="audit-empty">
 <ClipboardCheck size={48} className="mx-auto mb-4 text-[var(--color-text-muted)]" />
 <p className="text-[var(--color-text-muted)]">{t('dashboard.no_audits_yet')}</p>
 </Card>
 )}
 </div>
 )}

 {viewAudit && <AuditDetailPanel audit={viewAudit} onClose={() => onViewAudit(null)} />}
 </div>
 );
};

export default ReportsSection;
