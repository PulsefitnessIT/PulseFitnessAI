import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select';
import axios from 'axios';
import {
  BarChart3, TrendingUp, Wrench, AlertTriangle, CheckCircle,
  PoundSterling, RefreshCw, Shield, Mail, ShieldAlert
} from 'lucide-react';
import MODASERPortal from './MODPortal/MODASERPortal';
import RiskAssessmentTab from './RiskAssessmentTab';
import CapexIntelligenceTab from './CapexIntelligenceTab';
import IncidentsTab from './IncidentsTab';
import KpiTile from '@/components/shared/KpiTile';
import PageHeader from '@/components/shared/PageHeader';

import KPIPerformanceDashboard from './KPIPerformanceDashboard';

const PulseReportsTab = () => {
  const { API, user, activeSite, sites } = useAuth();
  const [resStats, setResStats] = useState(null);
  const [opsReport, setOpsReport] = useState(null);
  const [period, setPeriod] = useState('30d');
  const [loading, setLoading] = useState(true);
  const [subTab, setSubTab] = useState('performance');
  const [aserOpen, setAserOpen] = useState(false);
  const isMOD = ['mod_site', 'mod_branch', 'mod_org'].includes(user?.account_type);
  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  // Iter 216h62 — when the operator has picked a single site via the
  // SiteSwitcher we scope the reports to that site. Owner/manager
  // toggling to "All Operations Sites" (allSitesActive on the parent)
  // clears activeSite, which makes us send no site_id and get the
  // aggregate report back.
  const isMultiSite = (sites?.length || 0) > 1;
  const scopeSiteId = isMultiSite && activeSite?.id ? activeSite.id : null;
  const siteParam = scopeSiteId ? `&site_id=${encodeURIComponent(scopeSiteId)}` : '';
  const siteOnlyParam = scopeSiteId ? `?site_id=${encodeURIComponent(scopeSiteId)}` : '';

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [resRes, opsRes] = await Promise.all([
        axios.get(`${API}/reports/resolution-stats${siteOnlyParam}`, { headers }),
        axios.get(`${API}/reports/operational?period=${period}${siteParam}`, { headers }),
      ]);
      setResStats(resRes.data);
      setOpsReport(opsRes.data);
    } catch (err) {
      console.error('Failed to load reports:', err);
    }
    setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — effect either runs once on mount or re-fires on the listed trigger deps; omitted refs are stable identities or fetcher closures that read live state at call time, so including them would re-fire without changing semantics.
  }, [API, period, scopeSiteId]);

  useEffect(() => { loadData(); }, [loadData]);

  if (loading) return <div className="flex items-center justify-center py-16"><RefreshCw className="animate-spin text-inherit opacity-60" size={24} /></div>;

  const severityEntries = opsReport ? Object.entries(opsReport.severity_counts || {}).filter(([, v]) => v > 0) : [];
  const equipEntries = opsReport ? Object.entries(opsReport.by_equipment || {}).sort((a, b) => b[1] - a[1]).slice(0, 8) : [];
  const maxEquip = equipEntries.length > 0 ? Math.max(...equipEntries.map(([, v]) => v)) : 1;

  return (
    <div className="space-y-5" data-testid="pulse-reports">
      <PageHeader
        title="Reports"
        subtitle="Performance KPIs, operational reports, risk assessments & weekly digests"
        icon={BarChart3}
        testId="pulse-reports-header"
      />

      {/* Iter 288 — ASER launcher moved out of Reports into the sub-menu bar
          (see DashboardTabs). The red card was removed per request. */}

      {/* Iter 216h62 — scope badge tells the operator exactly which
          slice of data they're looking at. Switch via the navbar
          SiteSwitcher → "All Operations Sites" to aggregate. */}
      {isMultiSite && (
        <div className="flex items-center gap-2 text-xs" data-testid="reports-scope-badge">
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)', background: 'var(--theme-surface)' }}>
            {scopeSiteId ? (
              <>
                <span className="opacity-60">Scope:</span>
                <span className="font-semibold">{activeSite?.name}</span>
              </>
            ) : (
              <>
                <span className="opacity-60">Scope:</span>
                <span className="font-semibold">All Operations Sites</span>
                <span className="opacity-60">· aggregate</span>
              </>
            )}
          </span>
        </div>
      )}

      {/* Sub-tab switcher */}
      <div className="subtab-bar mb-2 overflow-x-auto" role="tablist" style={{ WebkitOverflowScrolling: 'touch' }}>
        {[
          { id: 'performance', label: 'Performance KPIs', icon: TrendingUp },
          { id: 'operational', label: 'Operational Reports', icon: BarChart3 },
          { id: 'risk', label: 'Risk Assessments', icon: Shield },
          { id: 'incidents', label: 'H&S Incidents', icon: AlertTriangle },
          ...(isMOD ? [{ id: 'aser', label: 'ASER', icon: ShieldAlert, action: true }] : []),
          ...(['owner', 'manager', 'master_admin'].includes(user?.role) ? [{ id: 'capex', label: 'CAPEX Intelligence', icon: PoundSterling }] : []),
          ...(['owner', 'manager', 'master_admin'].includes(user?.role) ? [{ id: 'weekly-digest', label: 'Weekly Digest', icon: Mail }] : []),
        ].map(tab => {
          const isActive = tab.action ? aserOpen : (subTab === tab.id && !aserOpen);
          return (
            <button
              key={tab.id}
              type="button"
              className={`subtab-pill ${isActive ? 'is-active' : ''}`}
              onClick={() => { if (tab.action) { setAserOpen(true); } else { setAserOpen(false); setSubTab(tab.id); } }}
              data-testid={`pulse-report-sub-${tab.id}`}
            >
              <tab.icon size={14} /> {tab.label}
            </button>
          );
        })}
      </div>

      {aserOpen ? (
        <MODASERPortal onClose={() => setAserOpen(false)} />
      ) : (
      <>
      {subTab === 'performance' && <KPIPerformanceDashboard />}
      {subTab === 'risk' && <RiskAssessmentTab />}
      {subTab === 'incidents' && <IncidentsTab />}
      {subTab === 'capex' && <CapexIntelligenceTab />}
      {subTab === 'weekly-digest' && (
        <div className="space-y-4" data-testid="pulse-weekly-digest">
          <Card className="p-8 text-center rounded-2xl" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
            <Mail size={36} className="text-[var(--pulse-primary-hover)] mx-auto mb-3" />
            <h3 className="font-semibold mb-2" style={{ color: 'var(--theme-text)' }}>Weekly Maintenance Digest</h3>
            <p className="text-sm mb-4" style={{ color: 'var(--theme-text-muted)' }}>
              Automated weekly summary of faults, resolutions, check-sheet completion, and key metrics sent to your inbox.
            </p>
            <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>
              Digest emails are sent every Monday morning.
            </p>
          </Card>
        </div>
      )}

      {subTab === 'operational' && (
      <>
      {/* Period Selector */}
      <div className="flex items-center justify-between">
        <h3 className="font-semibold" style={{ color: 'var(--theme-text)' }}>Operational Reports</h3>
        <div className="flex items-center gap-2">
          <Select value={period} onValueChange={setPeriod}>
            <SelectTrigger className="w-32 h-9 text-sm" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="pulse-report-period">
              <SelectValue />
            </SelectTrigger>
            <SelectContent style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
              <SelectItem value="7d">Last 7 days</SelectItem>
              <SelectItem value="30d">Last 30 days</SelectItem>
              <SelectItem value="90d">Last 90 days</SelectItem>
              <SelectItem value="365d">Last year</SelectItem>
            </SelectContent>
          </Select>
          <Button size="sm" variant="outline" className="h-9" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }} onClick={loadData}><RefreshCw size={13} /></Button>
        </div>
      </div>

      {/* Resolution KPIs */}
      {resStats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: 'Total Faults',      value: resStats.total_issues,                              icon: AlertTriangle,  tone: 'warning' },
            { label: 'Self-Fix Rate',     value: `${resStats.self_fix_rate}%`,                       icon: CheckCircle,    tone: 'success' },
            { label: 'Engineer Callouts', value: resStats.engineer_callouts,                          icon: Wrench,         tone: 'brand'   },
            { label: 'Est. Savings',      value: `£${resStats.estimated_savings.toLocaleString()}`,  icon: PoundSterling,  tone: 'success' },
          ].map(k => (
            <KpiTile
              key={k.label}
              icon={k.icon}
              label={k.label}
              value={k.value}
              tone={k.tone}
              testId={`pulse-report-kpi-${k.label.toLowerCase().replace(/ /g, '-')}`}
            />
          ))}
        </div>
      )}

      {/* Operational Stats */}
      {opsReport && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { label: 'Period Faults',    value: opsReport.total_faults,            tone: 'default' },
              { label: 'Open',             value: opsReport.open_faults,             tone: 'danger'  },
              { label: 'Resolved',         value: opsReport.resolved_faults,         tone: 'success' },
              { label: 'Avg Resolution',   value: `${opsReport.avg_resolution_hours}h`, tone: 'brand' },
            ].map(s => (
              <KpiTile
                key={s.label}
                label={s.label}
                value={s.value}
                tone={s.tone}
                testId={`pulse-report-op-${s.label.toLowerCase().replace(/ /g, '-')}`}
              />
            ))}
          </div>

          {/* Faults by Equipment Type */}
          {equipEntries.length > 0 && (
            <Card className="p-5" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
              <h4 className="font-semibold text-sm mb-4" style={{ color: 'var(--theme-text)' }}>Faults by Equipment Type</h4>
              <div className="space-y-3">
                {equipEntries.map(([type, count]) => (
                  <div key={type} className="flex items-center gap-3">
                    <span className="text-sm w-36 truncate" style={{ color: 'var(--theme-text-muted)' }}>{type}</span>
                    <div className="flex-1 bg-white/10 rounded-full h-5 overflow-hidden dark:bg-zinc-900">
                      <div className="bg-blue-500 h-full rounded-full transition-all" style={{ width: `${(count / maxEquip) * 100}%` }} />
                    </div>
                    <span className="text-sm font-medium w-8 text-right" style={{ color: 'var(--theme-text)' }}>{count}</span>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {/* Severity Breakdown */}
          {severityEntries.length > 0 && (
            <Card className="p-5" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
              <h4 className="font-semibold text-sm mb-3" style={{ color: 'var(--theme-text)' }}>Severity Breakdown</h4>
              <div className="flex flex-wrap gap-3">
                {severityEntries.map(([sev, count]) => {
                  const styles = {
                    operational_minor: 'bg-emerald-50 text-emerald-700 border-emerald-200',
                    operational_fault: 'bg-amber-50 text-amber-700 border-amber-200',
                    limited_use: 'bg-orange-50 text-orange-700 border-orange-200',
                    out_of_order: 'bg-red-50 text-red-700 border-red-200',
                    safety_critical: 'bg-red-100 text-red-800 border-red-300',
                    low: 'bg-emerald-50 text-emerald-700 border-emerald-200',
                    medium: 'bg-amber-50 text-amber-700 border-amber-200',
                    critical: 'bg-red-50 text-red-700 border-red-200',
                  };
                  return (
                    <div key={sev} className={`px-4 py-2 rounded-lg border ${styles[sev] || 'bg-white/5 text-inherit opacity-75 border-[var(--theme-border)]'}`}>
                      <p className="text-lg font-bold">{count}</p>
                      <p className="text-xs capitalize">{sev.replace(/_/g, ' ')}</p>
                    </div>
                  );
                })}
              </div>
            </Card>
          )}

          {/* Recent Self-Fixes */}
          {resStats?.recent_self_fixes?.length > 0 && (
            <Card style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
              <div className="p-4" style={{ borderBottom: '1px solid var(--theme-border)' }}><h4 className="font-semibold text-sm" style={{ color: 'var(--theme-text)' }}>Recent Self-Fixes</h4></div>
              <div className="divide-y" style={{ borderColor: 'var(--theme-border)' }}>
                {resStats.recent_self_fixes.slice(0, 5).map((fix, i) => (
                  <div key={i} className="p-3 flex items-center gap-3">
                    <CheckCircle size={14} className="text-emerald-500 flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium" style={{ color: 'var(--theme-text)' }}>{fix.serial_number}</p>
                      <p className="text-xs truncate" style={{ color: 'var(--theme-text-muted)' }}>{fix.resolution_note || fix.machine_type}</p>
                    </div>
                    <span className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{fix.created_at?.slice(0, 10)}</span>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {/* Purchase Order Summary */}
          {opsReport.po_count > 0 && (
            <Card className="p-5" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
              <h4 className="font-semibold text-sm mb-3" style={{ color: 'var(--theme-text)' }}>Purchase Orders</h4>
              <div className="grid grid-cols-3 gap-3 text-center">
                <div className="p-3 rounded-lg" style={{ background: 'var(--theme-surface-alt, rgba(255,255,255,0.05))' }}><p className="text-lg font-bold" style={{ color: 'var(--theme-text)' }}>{opsReport.po_count}</p><p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>Total POs</p></div>
                <div className="p-3 rounded-lg" style={{ background: 'var(--theme-surface-alt, rgba(255,255,255,0.05))' }}><p className="text-lg font-bold" style={{ color: 'var(--theme-text)' }}>£{opsReport.total_po_value.toLocaleString()}</p><p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>Total Value</p></div>
                <div className="p-3 rounded-lg" style={{ background: 'var(--theme-surface-alt, rgba(255,255,255,0.05))' }}>
                  <div className="flex flex-wrap gap-1 justify-center">
                    {Object.entries(opsReport.po_by_status || {}).map(([st, cnt]) => (
                      <Badge key={st} className="text-xs" style={{ background: 'var(--theme-border)', color: 'var(--theme-text)' }}>{st}: {cnt}</Badge>
                    ))}
                  </div>
                  <p className="text-xs mt-1" style={{ color: 'var(--theme-text-muted)' }}>By Status</p>
                </div>
              </div>
            </Card>
          )}
        </>
      )}
      </>
      )}
      </>
      )}
    </div>
  );
};

export default PulseReportsTab;
