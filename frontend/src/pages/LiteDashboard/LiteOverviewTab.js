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
import { useEffect, useState } from 'react';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Wrench, AlertTriangle, CheckCircle, Clock, AlertCircle,
  TrendingUp, ShieldCheck, Building2, Sparkles,
} from 'lucide-react';
import KpiTile from '../../components/shared/KpiTile';
import PulseScoreCard from '../../components/PulseScoreCard';
import { useAuth } from '@/App';

// Iter 216h192 — Lee's ask: when the score is "Fair" or lower, surface a
// concrete next step per sub-category. Iter 237 — the tips moved into
// PulseScoreCard (the single score surface on the Dashboard tab).

const LiteOverviewTab = ({
  equipment, openFaults, operational, outOfOrder,
  onLogFault, onViewFault,
  getSeverityStyle, getSeverityLabel,
}) => {
  const { API, activeSite, sites } = useAuth();
  const { t } = useTranslation();
  const [health, setHealth] = useState(null);
  const [, setHealthLoading] = useState(true);

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
        <AlertCircle className="mr-2" size={20} /> {t('dashboard.log_fault', 'Log a Fault')}
      </Button>

      {/* Iter 237 — The Pulse · today hero card. Dashboard-tab only
          (was previously duplicated: a hero card above EVERY tab + a
          second "Gym Health Score" panel here). Single source now. */}
      <PulseScoreCard siteId={scopeSiteId} />

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiTile icon={Wrench}        label={t('dashboard.total_machines', 'Total Machines')} value={equipment.length}     tone="brand"   testId="lite-kpi-machines" />
        <KpiTile icon={CheckCircle}   label={t('dashboard.operational', 'Operational')}    value={operational.length}   tone="success" testId="lite-kpi-operational" />
        <KpiTile icon={AlertTriangle} label={t('dashboard.with_faults', 'With Faults')}    value={outOfOrder}           tone="danger"  testId="lite-kpi-faults" />
        <KpiTile icon={Clock}         label={t('dashboard.open_faults', 'Open Faults')}    value={openFaults.length}    tone="warning" testId="lite-kpi-open" />
      </div>

      {/* Secondary KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiTile
          icon={TrendingUp}
          label={t('dashboard.resolved_week', 'Resolved this week')}
          value={resolvedThisWeek}
          tone="brand"
          testId="lite-kpi-resolved-week"
        />
        <KpiTile
          icon={ShieldCheck}
          label={t('dashboard.audits_logged', 'Audits logged')}
          value={health?.stats?.total_audits ?? 0}
          tone="brand"
          testId="lite-kpi-audits"
        />
        <KpiTile
          icon={Sparkles}
          label={t('dashboard.self_fixes', 'Self-fixes')}
          value={health?.stats?.self_fixes ?? 0}
          tone="success"
          testId="lite-kpi-selffix"
        />
        <KpiTile
          icon={Building2}
          label={topSupplier ? `${t('dashboard.top_supplier', 'Top supplier')}: ${topSupplier[0]}` : t('dashboard.top_supplier', 'Top supplier')}
          value={topSupplier ? topSupplier[1] : 0}
          tone="warning"
          testId="lite-kpi-top-supplier"
        />
      </div>

      {/* Recent Faults — Iter 237: theme-var colours (was hardcoded
          text-white, invisible in light mode + leaking in dark). */}
      <Card className="bg-[var(--theme-surface)] border-[var(--theme-border)]">
        <div className="p-4 border-b border-[var(--theme-border)]">
          <h3 className="font-semibold" style={{ color: 'var(--theme-text)' }}>{t('dashboard.recent_faults', 'Recent Faults')}</h3>
        </div>
        <div className="divide-y divide-[var(--theme-border)]/40">
          {openFaults.slice(0, 5).map((f) => (
            <div
              key={f.id}
              className="p-4 flex items-center gap-3 hover:bg-[var(--theme-hover-bg)] transition-colors cursor-pointer"
              onClick={() => onViewFault(f)}
              data-testid={`lite-recent-fault-${f.id}`}
            >
              <div className="flex-1 min-w-0">
                <p className="font-medium text-sm" style={{ color: 'var(--theme-text)' }}>{f.serial_number}</p>
                <p className="text-xs text-[var(--color-text-muted)] truncate">{f.issue_description}</p>
              </div>
              <Badge className={getSeverityStyle(f.severity)}>{getSeverityLabel(f.severity)}</Badge>
              <span className="text-xs text-[var(--color-text-muted)]">
                {f.created_at ? new Date(f.created_at).toLocaleDateString() : ''}
              </span>
            </div>
          ))}
          {openFaults.length === 0 && (
            <p className="p-6 text-center text-[var(--color-text-muted)] text-sm">{t('dashboard.no_open_faults', 'No open faults')}</p>
          )}
        </div>
      </Card>
    </div>
  );
};

export default LiteOverviewTab;
