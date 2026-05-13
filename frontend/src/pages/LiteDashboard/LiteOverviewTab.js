/**
 * LiteOverviewTab — Operations Dashboard
 *
 * Iter 216h65 — reinstates the Gym Health Score + extra KPIs that
 * were lost in earlier refactors. Adds site-scope awareness:
 *   • Multi-site tenants see a "Scope:" badge.
 *   • Owners/Managers in All-Operations-Sites mode see aggregate.
 *   • Single sites see ONLY their own metrics (enforced via the
 *     /api/gym-health-score?site_id=… backend filter we just added).
 */
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Wrench, AlertTriangle, CheckCircle, Clock, AlertCircle, Activity,
  TrendingUp, ShieldCheck, Building2, Sparkles,
} from 'lucide-react';
import KpiTile from '../../components/shared/KpiTile';
import { useAuth } from '@/App';

const LiteOverviewTab = ({
  equipment, openFaults, operational, outOfOrder,
  onLogFault, onViewFault,
  getSeverityStyle, getSeverityLabel,
}) => {
  const { API, activeSite, sites } = useAuth();
  const [health, setHealth] = useState(null);
  const [healthLoading, setHealthLoading] = useState(true);

  // Iter 216h62 / 216h65 — scope to the active site for multi-site
  // tenants. All-sites mode clears activeSite and we get the aggregate.
  const isMultiSite = (sites?.length || 0) > 1;
  const scopeSiteId = isMultiSite && activeSite?.id ? activeSite.id : null;

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setHealthLoading(true);
      try {
        const token = localStorage.getItem('token');
        const q = scopeSiteId ? `?site_id=${encodeURIComponent(scopeSiteId)}` : '';
        const r = await axios.get(`${API}/gym-health-score${q}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!cancelled) setHealth(r.data);
      } catch {
        if (!cancelled) setHealth(null);
      }
      if (!cancelled) setHealthLoading(false);
    };
    load();
    return () => { cancelled = true; };
  }, [API, scopeSiteId]);

  // Derived KPI: resolved-this-week
  const weekAgo = new Date(Date.now() - 7 * 86400 * 1000).toISOString();
  const resolvedThisWeek = (equipment || [])
    .map((e) => e) // placeholder; resolution count comes from openFaults inverse
    .length === 0
    ? 0
    : (openFaults || []).filter((f) => f.status === 'resolved' && f.resolved_at >= weekAgo).length;

  // Top supplier by open-fault count (quick at-a-glance signal).
  const supplierCounts = {};
  (openFaults || []).forEach((f) => {
    const s = f.supplier || 'Unassigned';
    supplierCounts[s] = (supplierCounts[s] || 0) + 1;
  });
  const topSupplier = Object.entries(supplierCounts).sort(([, a], [, b]) => b - a)[0];

  return (
    <div className="space-y-6">
      {/* Scope badge — multi-site only */}
      {isMultiSite && (
        <div className="flex items-center gap-2 text-xs" data-testid="overview-scope-badge">
          <span
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border"
            style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)', background: 'var(--theme-surface)' }}
          >
            <Building2 size={11} className="opacity-60" />
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

      {/* Log Fault CTA */}
      <Button
        onClick={onLogFault}
        className="bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white px-6 py-3 text-base"
        data-testid="overview-log-fault-btn"
      >
        <AlertCircle className="mr-2" size={20} /> Log a Fault
      </Button>

      {/* Gym Health Score panel */}
      <Card
        className="bg-[var(--theme-surface)] border-[var(--theme-border)] p-5"
        data-testid="overview-health-score"
      >
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <Activity size={16} className="text-[var(--color-brand-cyan)]" />
              <h3 className="text-base font-semibold text-[var(--theme-text)]">Gym Health Score</h3>
            </div>
            {healthLoading ? (
              <p className="text-xs text-[var(--color-text-muted)]">Calculating…</p>
            ) : health?.not_ready ? (
              <p className="text-xs text-[var(--color-text-muted)]">{health.message}</p>
            ) : health ? (
              <>
                <div className="flex items-baseline gap-3 mt-2">
                  <span
                    className="text-5xl font-extrabold tabular-nums"
                    style={{ color: health.color }}
                    data-testid="overview-health-score-value"
                  >
                    {health.score}
                  </span>
                  <span className="text-sm font-medium" style={{ color: health.color }}>
                    {health.rating}
                  </span>
                </div>
                <p className="text-[10px] text-[var(--color-text-muted)] mt-1">out of 100</p>
              </>
            ) : (
              <p className="text-xs text-[var(--color-text-muted)]">Unavailable</p>
            )}
          </div>
          {health && !health.not_ready && (
            <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px] flex-1 max-w-md">
              {Object.entries(health.breakdown || {}).map(([k, v]) => (
                <div key={k} className="flex justify-between gap-2 border-b border-[var(--theme-border)]/30 py-1" data-testid={`health-breakdown-${k}`}>
                  <span className="text-[var(--color-text-muted)] capitalize truncate">{k.replace(/_/g, ' ')}</span>
                  <span className="font-mono text-[var(--theme-text)] shrink-0">{v.score}<span className="opacity-50">/{v.max}</span></span>
                </div>
              ))}
            </div>
          )}
        </div>
      </Card>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiTile icon={Wrench}        label="Total Machines" value={equipment.length}     tone="brand"   testId="lite-kpi-machines" />
        <KpiTile icon={CheckCircle}   label="Operational"    value={operational.length}   tone="success" testId="lite-kpi-operational" />
        <KpiTile icon={AlertTriangle} label="With Faults"    value={outOfOrder}           tone="danger"  testId="lite-kpi-faults" />
        <KpiTile icon={Clock}         label="Open Faults"    value={openFaults.length}    tone="warning" testId="lite-kpi-open" />
      </div>

      {/* Secondary KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiTile
          icon={TrendingUp}
          label="Resolved this week"
          value={resolvedThisWeek}
          tone="brand"
          testId="lite-kpi-resolved-week"
        />
        <KpiTile
          icon={ShieldCheck}
          label="Audits logged"
          value={health?.stats?.total_audits ?? 0}
          tone="brand"
          testId="lite-kpi-audits"
        />
        <KpiTile
          icon={Sparkles}
          label="Self-fixes"
          value={health?.stats?.self_fixes ?? 0}
          tone="success"
          testId="lite-kpi-selffix"
        />
        <KpiTile
          icon={Building2}
          label={topSupplier ? `Top supplier: ${topSupplier[0]}` : 'Top supplier'}
          value={topSupplier ? topSupplier[1] : 0}
          tone="warning"
          testId="lite-kpi-top-supplier"
        />
      </div>

      {/* Recent Faults */}
      <Card className="bg-[var(--theme-surface)] border-[var(--theme-border)]">
        <div className="p-4 border-b border-[var(--theme-border)]">
          <h3 className="font-semibold text-white">Recent Faults</h3>
        </div>
        <div className="divide-y divide-white/5">
          {openFaults.slice(0, 5).map((f) => (
            <div
              key={f.id}
              className="p-4 flex items-center gap-3 hover:bg-white/[0.02] transition-colors cursor-pointer"
              onClick={() => onViewFault(f)}
              data-testid={`lite-recent-fault-${f.id}`}
            >
              <div className="flex-1 min-w-0">
                <p className="font-medium text-white text-sm">{f.serial_number}</p>
                <p className="text-xs text-[var(--color-text-muted)] truncate">{f.issue_description}</p>
              </div>
              <Badge className={getSeverityStyle(f.severity)}>{getSeverityLabel(f.severity)}</Badge>
              <span className="text-xs text-[var(--color-text-muted)]">
                {f.created_at ? new Date(f.created_at).toLocaleDateString() : ''}
              </span>
            </div>
          ))}
          {openFaults.length === 0 && (
            <p className="p-6 text-center text-[var(--color-text-muted)] text-sm">No open faults</p>
          )}
        </div>
      </Card>
    </div>
  );
};

export default LiteOverviewTab;
