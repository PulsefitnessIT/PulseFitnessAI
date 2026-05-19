import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/App';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select';
import axios from 'axios';
import {
  Activity, Shield, Clock, AlertTriangle, CheckCircle,
  Target, Timer, RefreshCw, Wrench
} from 'lucide-react';

const ratingBadge = (pct) => {
  if (pct >= 95) return { cls: 'bg-emerald-500/20 text-emerald-400', label: 'Excellent', border: 'rgba(16,185,129,0.6)', glow: '0 0 0 1px rgba(16,185,129,0.35), 0 4px 12px rgba(16,185,129,0.1)' };
  if (pct >= 80) return { cls: 'bg-blue-500/20 text-blue-400', label: 'Good', border: 'rgba(59,130,246,0.5)', glow: '0 0 0 1px rgba(59,130,246,0.3), 0 4px 12px rgba(59,130,246,0.08)' };
  if (pct >= 60) return { cls: 'bg-amber-500/20 text-amber-400', label: 'Needs Attention', border: 'rgba(245,158,11,0.6)', glow: '0 0 0 1px rgba(245,158,11,0.35), 0 4px 12px rgba(245,158,11,0.1)' };
  return { cls: 'bg-red-500/20 text-red-400', label: 'Critical', border: 'rgba(239,68,68,0.6)', glow: '0 0 0 1px rgba(239,68,68,0.35), 0 4px 12px rgba(239,68,68,0.12)' };
};

const T = {
  card: { background: 'var(--theme-surface)', border: '1px solid var(--theme-border)', borderRadius: '12px', boxShadow: 'var(--theme-card-shadow)' },
  text: { color: 'var(--theme-text)' },
  muted: { color: 'var(--theme-text-muted)' },
  surface: { background: 'var(--theme-hover-bg)', borderColor: 'var(--theme-border)' },
  border: { borderColor: 'var(--theme-border)' },
  accentBg: { background: 'rgba(59,130,246,0.12)' },
};

const KPICard = ({ title, value, unit, subtitle, icon: Icon, rating, testId }) => {
  const r = rating ? ratingBadge(typeof rating === 'number' ? rating : 0) : null;
  const cardStyle = r
    ? { ...T.card, borderLeft: `3px solid ${r.border}`, boxShadow: r.glow, transition: 'all 0.2s ease' }
    : { ...T.card, transition: 'all 0.2s ease' };
  return (
    <div style={cardStyle} className="p-5 hover:-translate-y-0.5" data-testid={testId}>
      <div className="flex items-start justify-between mb-3">
        <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={T.accentBg}>
          <Icon size={20} className="text-[var(--color-info)]" />
        </div>
        {r && <Badge className={`text-[10px] ${r.cls}`}>{r.label}</Badge>}
      </div>
      <p className="text-2xl font-bold" style={T.text}>{value}<span className="text-sm font-normal ml-1" style={T.muted}>{unit}</span></p>
      <p className="text-xs mt-1 font-semibold" style={T.muted}>{title}</p>
      {subtitle && <p className="text-[11px] mt-1 opacity-70" style={T.muted}>{subtitle}</p>}
    </div>
  );
};

const WorstAssetRow = ({ asset, index }) => (
  <div className="flex items-center justify-between py-2.5 border-b" style={T.border} data-testid={`worst-asset-${index}`}>
    <div>
      <p className="text-sm font-semibold" style={T.text}>{asset.asset_name || asset.asset_id}</p>
      <p className="text-xs" style={T.muted}>{asset.fault_count} faults</p>
    </div>
    <Badge className="bg-red-500/20 text-red-400 text-xs font-semibold">{asset.total_hours}h downtime</Badge>
  </div>
);

const KPIPerformanceDashboard = () => {
  const { API } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState('30d');
  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/reports/kpi-dashboard?period=${period}`, { headers });
      setData(res.data);
    } catch (err) { console.error('KPI load failed:', err); }
    setLoading(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps -- todo: review missing dep(s) 'headers'; pre-existing as of iter 216h226-polish-5.
  }, [API, period]);

  useEffect(() => { loadData(); }, [loadData]);

  if (loading) return <div className="flex items-center justify-center py-16"><RefreshCw className="animate-spin" size={24} style={T.muted} /></div>;
  if (!data) return <div className="text-center py-16" style={T.muted}>No KPI data available</div>;

  const { ppm_compliance: ppm, equipment_downtime: dt, reactive_response: rr, safety_critical: sc, safety_compliance: si, oos_ratio: oos, commissioning: comm } = data;
  const dtRating = dt.avg_downtime_hours < 12 ? 95 : dt.avg_downtime_hours < 24 ? 80 : dt.avg_downtime_hours < 48 ? 60 : 30;

  return (
    <div className="space-y-6" data-testid="kpi-performance-dashboard">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-bold" style={T.text}>Gym Performance KPIs</h2>
        </div>
        <div className="flex gap-2 items-center">
          <Select value={period} onValueChange={setPeriod}>
            <SelectTrigger className="w-28 h-9 text-xs" data-testid="kpi-period-select"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="7d">7 Days</SelectItem>
              <SelectItem value="30d">30 Days</SelectItem>
              <SelectItem value="90d">90 Days</SelectItem>
              <SelectItem value="365d">12 Months</SelectItem>
              <SelectItem value="all">All Time</SelectItem>
            </SelectContent>
          </Select>
          <Button size="sm" variant="outline" onClick={loadData} className="h-9" data-testid="kpi-refresh"><RefreshCw size={14} /></Button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3" data-testid="kpi-summary-cards">
        <KPICard title="PPM Compliance" value={ppm.compliance_pct} unit="%" icon={Target} rating={ppm.compliance_pct} subtitle={`${ppm.total_completed}/${ppm.total_scheduled} services completed`} testId="kpi-ppm" />
        <KPICard title="Avg Machine Downtime" value={dt.avg_downtime_hours} unit="hrs" icon={Clock} rating={dtRating} subtitle={`${dt.total_faults} gym equipment faults`} testId="kpi-downtime" />
        <KPICard title="Safety Response SLA" value={sc.compliance_pct} unit="%" icon={Shield} rating={sc.compliance_pct} subtitle={`${sc.sla_breaches} breaches / ${sc.total_safety_issues} safety issues`} testId="kpi-safety" />
        <KPICard title="Machine Availability" value={(100 - oos.oos_pct).toFixed(1)} unit="%" icon={Activity} rating={100 - oos.oos_pct} subtitle={`${oos.out_of_service} of ${oos.total_equipment} machines out of service`} testId="kpi-availability" />
      </div>

      {/* Detail panels */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* PPM Compliance */}
        <div style={T.card} className="p-5" data-testid="kpi-ppm-detail">
          <div className="flex items-center gap-2 mb-4">
            <Target size={18} className="text-[var(--color-info)]" />
            <h3 className="font-bold" style={T.text}>PPM Compliance</h3>
          </div>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div><p className="text-xs" style={T.muted}>Scheduled</p><p className="text-lg font-bold" style={T.text}>{ppm.total_scheduled}</p></div>
            <div><p className="text-xs" style={T.muted}>Completed</p><p className="text-lg font-bold text-emerald-500">{ppm.total_completed}</p></div>
            <div><p className="text-xs" style={T.muted}>On Time</p><p className="text-lg font-bold text-blue-500">{ppm.completed_on_time}</p></div>
            <div><p className="text-xs" style={T.muted}>Overdue</p><p className="text-lg font-bold text-red-500">{ppm.overdue}</p></div>
          </div>
          {Object.keys(ppm.by_site || {}).length > 0 && (
            <div className="mt-4 pt-3 border-t" style={T.border}>
              <p className="text-xs font-bold mb-2" style={T.muted}>By Site</p>
              {Object.entries(ppm.by_site).map(([id, s]) => (
                <div key={id} className="flex items-center justify-between py-1.5 text-xs">
                  <span className="font-medium" style={T.text}>{s.site_name || id}</span>
                  <Badge className={s.compliance_pct >= 90 ? 'bg-emerald-500/20 text-emerald-400' : s.compliance_pct >= 70 ? 'bg-amber-500/20 text-amber-400' : 'bg-red-500/20 text-red-400'}>{s.compliance_pct}%</Badge>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Response Times */}
        <div style={T.card} className="p-5" data-testid="kpi-response-detail">
          <div className="flex items-center gap-2 mb-4">
            <Timer size={18} className="text-[var(--color-info)]" />
            <h3 className="font-bold" style={T.text}>Reactive Response Times</h3>
          </div>
          <div className="space-y-3">
            <div className="p-3 rounded-lg" style={T.surface}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-semibold" style={T.muted}>Standard Faults</span>
                <Badge className="bg-blue-500/20 text-blue-400 text-[10px]">{rr.standard.count} tracked</Badge>
              </div>
              <p className="text-xl font-bold" style={T.text}>{rr.standard.avg_response_hours ?? 'N/A'}<span className="text-sm font-normal ml-1" style={T.muted}>hrs avg</span></p>
            </div>
            <div className="p-3 rounded-lg bg-red-500/10">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs text-red-500 font-semibold">Safety Critical Faults</span>
                <Badge className="bg-red-500/20 text-red-400 text-[10px]">{rr.safety_critical.count} tracked</Badge>
              </div>
              <p className="text-xl font-bold text-red-500">{rr.safety_critical.avg_response_hours ?? 'N/A'}<span className="text-sm font-normal opacity-60 ml-1">hrs avg</span></p>
            </div>
          </div>
        </div>

        {/* Safety Compliance */}
        <div style={T.card} className="p-5" data-testid="kpi-safety-compliance-detail">
          <div className="flex items-center gap-2 mb-4">
            <CheckCircle size={18} className="text-[var(--color-info)]" />
            <h3 className="font-bold" style={T.text}>Safety & Inspection Compliance</h3>
          </div>
          <div className="grid grid-cols-3 gap-3 text-center">
            <div><p className="text-2xl font-bold text-emerald-500">{si.first_time_pass}</p><p className="text-[10px] font-semibold" style={T.muted}>First-Time Pass</p></div>
            <div><p className="text-2xl font-bold text-red-500">{si.failed}</p><p className="text-[10px] font-semibold" style={T.muted}>Failed</p></div>
            <div><p className="text-2xl font-bold" style={T.text}>{si.first_time_pass_pct}%</p><p className="text-[10px] font-semibold" style={T.muted}>Pass Rate</p></div>
          </div>
          <div className="mt-4 pt-3 border-t" style={T.border}>
            <div className="flex items-center gap-2 mb-2">
              <Wrench size={14} className="text-[var(--color-info)]" />
              <span className="text-xs font-bold" style={T.muted}>Post-Installation Verification</span>
            </div>
            <div className="grid grid-cols-3 gap-3 text-center text-sm">
              <div><p className="font-bold text-emerald-500">{comm.passed}</p><p className="text-[10px]" style={T.muted}>Passed</p></div>
              <div><p className="font-bold text-red-500">{comm.failed}</p><p className="text-[10px]" style={T.muted}>Failed</p></div>
              <div><p className="font-bold" style={T.text}>{comm.pass_rate_pct}%</p><p className="text-[10px]" style={T.muted}>Rate</p></div>
            </div>
          </div>
        </div>

        {/* Worst Performing */}
        <div style={T.card} className="p-5" data-testid="kpi-worst-assets">
          <div className="flex items-center gap-2 mb-4">
            <AlertTriangle size={18} className="text-amber-500" />
            <h3 className="font-bold" style={T.text}>Worst Performing Machines</h3>
          </div>
          {dt.worst_performing_assets?.length > 0 ? (
            <div>{dt.worst_performing_assets.slice(0, 6).map((a, i) => <WorstAssetRow key={i} asset={a} index={i} />)}</div>
          ) : (
            <p className="text-sm text-center py-6" style={T.muted}>No downtime data yet</p>
          )}
        </div>
      </div>
    </div>
  );
};

export default KPIPerformanceDashboard;
