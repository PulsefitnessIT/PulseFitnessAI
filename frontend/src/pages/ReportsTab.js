import { useState, useEffect } from 'react';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import axios from 'axios';
import { Wrench, Bot, TrendingUp, PoundSterling, BarChart3, CheckCircle, Clock } from 'lucide-react';
import PageHeader from '@/components/shared/PageHeader';
import KpiTile from '@/components/shared/KpiTile';

const ReportsTab = () => {
  const { API, activeSite, sites } = useAuth();
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  // Iter 216h62 — scope reports to the active site when the org has
  // multiple sites and the operator hasn't toggled All-sites mode.
  const isMultiSite = (sites?.length || 0) > 1;
  const scopeSiteId = isMultiSite && activeSite?.id ? activeSite.id : null;

  useEffect(() => {
    const load = async () => {
      const token = localStorage.getItem('token');
      try {
        const q = scopeSiteId ? `?site_id=${encodeURIComponent(scopeSiteId)}` : '';
        const res = await axios.get(`${API}/reports/resolution-stats${q}`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        setStats(res.data);
      } catch (err) {
        console.error('Failed to load stats:', err);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [API, scopeSiteId]);

  if (loading) return <div className="text-[var(--color-text-muted)] text-center py-16">Loading reports...</div>;
  if (!stats) return <div className="text-[var(--color-text-muted)] text-center py-16">No data available</div>;

  const totalResolved = stats.self_fixes + stats.engineer_callouts;
  const selfFixPct = totalResolved > 0 ? Math.round((stats.self_fixes / totalResolved) * 100) : 0;
  const engineerPct = totalResolved > 0 ? 100 - selfFixPct : 0;

  return (
    <div className="space-y-6" data-testid="reports-tab">
      <PageHeader
        title="Resolution Reports"
        subtitle="Track how issues are resolved — Pulse Fitness AI self-fixes vs engineer callouts"
        icon={BarChart3}
        testId="reports-header"
      />

      {/* Hero Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KpiTile icon={BarChart3}     label="Total Issues"        value={stats.total_issues}                                                  tone="brand"   testId="stat-total" />
        <KpiTile icon={Bot}           label="Fixed by Pulse Fitness AI" value={stats.self_fixes}                                                    tone="success" testId="stat-ai-fixes" />
        <KpiTile icon={Wrench}        label="Engineer Callouts"   value={stats.engineer_callouts}                                             tone="warning" testId="stat-engineer" />
        <KpiTile icon={PoundSterling} label="Est. Savings"        value={`£${stats.estimated_savings.toLocaleString()}`}                     tone="success" trend={`@ £${stats.avg_callout_cost}/callout`} testId="stat-savings" />
      </div>

      {/* Fix Rate Visual */}
      <Card className="bg-[var(--theme-surface)] border-white/10 p-6" data-testid="fix-rate-card">
        <h3 className="text-lg font-semibold text-white mb-4">Resolution Breakdown</h3>
        
        <div className="flex items-center gap-6 mb-6">
          {/* Donut chart */}
          <div className="relative w-36 h-36 flex-shrink-0">
            <svg viewBox="0 0 36 36" className="w-36 h-36 -rotate-90">
              <circle cx="18" cy="18" r="14" fill="none" stroke="var(--color-ink-navy)" strokeWidth="3.5" />
              {totalResolved > 0 && (
                <>
                  <circle cx="18" cy="18" r="14" fill="none" stroke="var(--color-success-alt-2)" strokeWidth="3.5" strokeDasharray={`${selfFixPct * 0.88} ${88 - selfFixPct * 0.88}`} strokeDashoffset="0" strokeLinecap="round" />
                  <circle cx="18" cy="18" r="14" fill="none" stroke="var(--color-orange)" strokeWidth="3.5" strokeDasharray={`${engineerPct * 0.88} ${88 - engineerPct * 0.88}`} strokeDashoffset={`${-selfFixPct * 0.88}`} strokeLinecap="round" />
                </>
              )}
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-2xl font-bold text-white">{stats.self_fix_rate}%</span>
              <span className="text-[var(--color-text-muted)] text-xs">Self-fix</span>
            </div>
          </div>
          
          <div className="flex-1 space-y-4">
            <div>
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <span className="w-3 h-3 rounded-full bg-green-500"></span>
                  <span className="text-white text-sm">Fixed by Pulse Fitness AI</span>
                </div>
                <span className="text-green-400 font-bold">{stats.self_fixes}</span>
              </div>
              <div className="w-full bg-[var(--color-ink-alt)] rounded-full h-3">
                <div className="bg-green-500 h-3 rounded-full transition-all" style={{ width: `${selfFixPct}%` }}></div>
              </div>
            </div>
            <div>
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <span className="w-3 h-3 rounded-full bg-orange-500"></span>
                  <span className="text-white text-sm">Service Provider</span>
                </div>
                <span className="text-orange-400 font-bold">{stats.engineer_callouts}</span>
              </div>
              <div className="w-full bg-[var(--color-ink-alt)] rounded-full h-3">
                <div className="bg-orange-500 h-3 rounded-full transition-all" style={{ width: `${engineerPct}%` }}></div>
              </div>
            </div>
            <div>
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <span className="w-3 h-3 rounded-full bg-[var(--color-text-muted)]"></span>
                  <span className="text-white text-sm">Open / Pending</span>
                </div>
                <span className="text-[var(--color-text-muted)] font-bold">{stats.open_issues + stats.in_progress}</span>
              </div>
            </div>
          </div>
        </div>
      </Card>

      {/* By Equipment Type */}
      {Object.keys(stats.by_equipment || {}).length > 0 && (
        <Card className="bg-[var(--theme-surface)] border-white/10 p-6" data-testid="by-equipment-card">
          <h3 className="text-lg font-semibold text-white mb-4">By Equipment Type</h3>
          <div className="space-y-3">
            {Object.entries(stats.by_equipment).map(([type, data]) => (
              <div key={type} className="flex items-center justify-between p-3 bg-[var(--color-ink-alt)] border border-white/10 rounded-lg">
                <div>
                  <p className="text-white font-medium">{type}</p>
                  <p className="text-[var(--color-text-muted)] text-sm">{data.total} total issues</p>
                </div>
                <div className="flex items-center gap-3">
                  {data.self_fix > 0 && (
                    <Badge className="bg-green-500/20 text-green-400">
                      <Bot size={12} className="mr-1" /> {data.self_fix} AI fixed
                    </Badge>
                  )}
                  {data.engineer > 0 && (
                    <Badge className="bg-orange-500/20 text-orange-400">
                      <Wrench size={12} className="mr-1" /> {data.engineer} engineer
                    </Badge>
                  )}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Recent Activity */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Recent AI Fixes */}
        <Card className="bg-[var(--theme-surface)] border-white/10 p-6" data-testid="recent-ai-fixes">
          <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
            <CheckCircle size={18} className="text-green-400" /> Recent AI-Assisted Fixes
          </h3>
          <div className="space-y-2">
            {(stats.recent_self_fixes || []).length > 0 ? stats.recent_self_fixes.map((fix, idx) => (
              <div key={idx} className="p-3 bg-[var(--color-ink-alt)] border border-green-500/20 rounded-lg">
                <div className="flex items-center justify-between">
                  <p className="text-white text-sm font-medium">{fix.serial_number} - {fix.machine_type}</p>
                  <Badge className="bg-green-500/20 text-green-400 text-xs">Self-Fixed</Badge>
                </div>
                {fix.resolution_note && <p className="text-[var(--color-text-muted)] text-xs mt-1">{fix.resolution_note}</p>}
                <p className="text-[var(--color-text-muted)] text-xs mt-1">{fix.created_at ? new Date(fix.created_at).toLocaleDateString() : ''}</p>
              </div>
            )) : (
              <p className="text-[var(--color-text-muted)] text-center py-4 text-sm">No self-fixes recorded yet. Try the AI triage next time you log an issue!</p>
            )}
          </div>
        </Card>

        {/* Recent Engineer Callouts */}
        <Card className="bg-[var(--theme-surface)] border-white/10 p-6" data-testid="recent-engineer-callouts">
          <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
            <Clock size={18} className="text-orange-400" /> Recent Engineer Callouts
          </h3>
          <div className="space-y-2">
            {(stats.recent_engineer_callouts || []).length > 0 ? stats.recent_engineer_callouts.map((callout, idx) => (
              <div key={idx} className="p-3 bg-[var(--color-ink-alt)] border border-orange-500/20 rounded-lg">
                <div className="flex items-center justify-between">
                  <p className="text-white text-sm font-medium">{callout.serial_number} - {callout.machine_type}</p>
                  <Badge className={callout.severity === 'critical' ? 'bg-red-500/20 text-red-400' : 'bg-orange-500/20 text-orange-400'}>
                    {callout.severity}
                  </Badge>
                </div>
                {callout.supplier && <p className="text-[var(--color-text-muted)] text-xs mt-1">Supplier: {callout.supplier}</p>}
                <p className="text-[var(--color-text-muted)] text-xs mt-1">{callout.created_at ? new Date(callout.created_at).toLocaleDateString() : ''}</p>
              </div>
            )) : (
              <p className="text-[var(--color-text-muted)] text-center py-4 text-sm">No engineer callouts recorded yet</p>
            )}
          </div>
        </Card>
      </div>

      {/* Savings Highlight */}
      <Card className="bg-gradient-to-r from-green-500/10 to-emerald-500/10 border-green-500/30 p-6" data-testid="savings-highlight">
        <div className="flex items-center gap-4">
          <div className="w-14 h-14 rounded-full bg-green-500/20 flex items-center justify-center flex-shrink-0">
            <TrendingUp size={28} className="text-green-400" />
          </div>
          <div>
            <h3 className="text-xl font-bold text-white">
              Pulse Fitness AI has saved you an estimated {"\u00A3"}{stats.estimated_savings.toLocaleString()}
            </h3>
            <p className="text-[var(--color-text-muted)] mt-1">
              {stats.self_fixes} issues resolved through AI-guided self-repair at {"\u00A3"}{stats.avg_callout_cost} per avoided engineer callout. 
              Your self-fix rate is <span className="text-green-400 font-semibold">{stats.self_fix_rate}%</span>.
            </p>
          </div>
        </div>
      </Card>
    </div>
  );
};

export default ReportsTab;
