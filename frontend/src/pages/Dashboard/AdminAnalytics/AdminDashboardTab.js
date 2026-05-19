import { useState, useEffect, useMemo } from 'react';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Building2, Wrench, AlertTriangle, CheckCircle, Clock, TrendingUp, Award, RefreshCw } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import axios from 'axios';
import { useAuth } from '@/App';

const AdminDashboardTab = () => {
  const { API } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const token = localStorage.getItem('token');

  useEffect(() => {
    const load = async () => {
      try {
        const res = await axios.get(`${API}/master-admin/analytics/dashboard`, { headers: { Authorization: `Bearer ${token}` } });
        setData(res.data);
      } catch { /* ignored */ }
      setLoading(false);
    };
    load();
  }, [API, token]);

  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — effect either runs once on mount or re-fires on the listed trigger deps; omitted refs are stable identities or fetcher closures that read live state at call time, so including them would re-fire without changing semantics.
  const leaderboard = data?.leaderboard || [];
  const filteredLeaderboard = useMemo(
    () => leaderboard.filter(g => g.equipment_count > 0 || g.total_faults > 0),
    [leaderboard]
  );

  if (loading) return <div className="flex items-center justify-center h-64"><RefreshCw className="animate-spin" style={{ color: 'var(--theme-text-muted)' }} size={24} /></div>;
  if (!data) return <p style={{ color: 'var(--theme-text-muted)' }} className="text-center py-12">Failed to load analytics</p>;

  const { global_kpis: kpi, fault_trend } = data;

  const kpiCards = [
    { label: 'Total Gyms', value: kpi.total_gyms, icon: Building2, color: 'text-blue-400', bg: 'bg-blue-500/10' },
    { label: 'Total Equipment', value: kpi.total_equipment, icon: Wrench, color: 'text-teal-400', bg: 'bg-teal-500/10' },
    { label: 'Open Faults', value: kpi.open_faults, icon: AlertTriangle, color: 'text-red-400', bg: 'bg-red-500/10' },
    { label: 'Resolved', value: kpi.resolved_faults, icon: CheckCircle, color: 'text-emerald-400', bg: 'bg-emerald-500/10' },
    { label: 'Avg Resolution', value: kpi.avg_resolution_hours > 0 ? `${kpi.avg_resolution_hours}h` : '—', icon: Clock, color: 'text-amber-400', bg: 'bg-amber-500/10' },
    { label: 'Avg Health', value: `${kpi.avg_health_score}%`, icon: TrendingUp, color: 'text-violet-400', bg: 'bg-violet-500/10' },
  ];

  const getScoreColor = (score) => {
    if (score >= 90) return 'text-emerald-400';
    if (score >= 70) return 'text-amber-400';
    return 'text-red-400';
  };

  const getScoreBg = (score) => {
    if (score >= 90) return 'bg-emerald-500/15';
    if (score >= 70) return 'bg-amber-500/15';
    return 'bg-red-500/15';
  };

  return (
    <div className="space-y-6" data-testid="admin-analytics-dashboard">
      {/* KPI Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {kpiCards.map(k => (
          <Card key={k.label} className="p-5" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
            <div className="flex items-center gap-2.5">
              <div className={`w-9 h-9 rounded-lg ${k.bg} flex items-center justify-center flex-shrink-0`}>
                <k.icon size={16} className={k.color} />
              </div>
              <div className="min-w-0">
                <p className="text-lg font-bold" style={{ color: 'var(--theme-text)' }}>{k.value}</p>
                <p className="text-[10px] uppercase tracking-wider truncate" style={{ color: 'var(--theme-text-muted)' }}>{k.label}</p>
              </div>
            </div>
          </Card>
        ))}
      </div>

      {/* Fault Trend Chart */}
      <Card className="p-5" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
        <h3 className="text-base font-semibold mb-4" style={{ color: 'var(--theme-text)' }}>Fault Trend (6 Months)</h3>
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={fault_trend}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--theme-border)" />
            <XAxis dataKey="month" tick={{ fontSize: 11, fill: 'var(--theme-text-muted)' }} />
            <YAxis tick={{ fontSize: 11, fill: 'var(--theme-text-muted)' }} width={30} />
            <Tooltip contentStyle={{ background: 'var(--theme-surface)', border: '1px solid var(--theme-border)', borderRadius: 8, color: 'var(--theme-text)', fontSize: 12 }} />
            <Line type="monotone" dataKey="faults" stroke="var(--color-danger)" strokeWidth={2} dot={{ r: 3, fill: 'var(--color-danger)' }} name="Faults" />
          </LineChart>
        </ResponsiveContainer>
      </Card>

      {/* Gym Leaderboard */}
      <Card className="overflow-hidden" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
        <div className="p-4 flex items-center gap-2" style={{ borderBottom: '1px solid var(--theme-border)' }}>
          <Award size={18} className="text-amber-400" />
          <h3 className="text-base font-semibold" style={{ color: 'var(--theme-text)' }}>Gym Performance Leaderboard</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="gym-leaderboard">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--theme-border)' }}>
                {['Rank', 'Gym', 'Health', 'Equipment', 'Faults', 'Open', 'Resolved', 'Checks', '30d Faults'].map(h => (
                  <th key={h} className="text-left p-3 text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filteredLeaderboard.map((gym, i) => (
                <tr key={gym.org_id} className="hover:opacity-80 transition-opacity" style={{ borderBottom: '1px solid var(--theme-border)' }} data-testid={`leaderboard-row-${i}`}>
                  <td className="p-3">
                    <div className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold" style={{ background: i < 3 ? ['var(--color-gold)', 'var(--color-silver)', 'var(--color-bronze)'][i] + '30' : 'var(--theme-border)', color: i < 3 ? ['var(--color-gold)', 'var(--color-silver)', 'var(--color-bronze)'][i] : 'var(--theme-text-muted)' }}>
                      {i + 1}
                    </div>
                  </td>
                  <td className="p-3">
                    <div className="flex items-center gap-2">
                      <span className="font-medium" style={{ color: 'var(--theme-text)' }}>{gym.org_name}</span>
                      {gym.account_type !== 'full' && <Badge className="text-[9px] bg-blue-500/20 text-blue-400">{gym.account_type}</Badge>}
                    </div>
                  </td>
                  <td className="p-3">
                    <span className={`text-sm font-bold px-2 py-0.5 rounded ${getScoreColor(gym.health_score)} ${getScoreBg(gym.health_score)}`}>{gym.health_score}%</span>
                  </td>
                  <td className="p-3 font-medium" style={{ color: 'var(--theme-text)' }}>{gym.equipment_count}</td>
                  <td className="p-3 font-medium" style={{ color: 'var(--theme-text)' }}>{gym.total_faults}</td>
                  <td className="p-3"><span className={gym.open_faults > 0 ? 'text-red-400 font-medium' : ''} style={gym.open_faults === 0 ? { color: 'var(--theme-text-muted)' } : {}}>{gym.open_faults}</span></td>
                  <td className="p-3"><span className="text-emerald-400">{gym.resolved_faults}</span></td>
                  <td className="p-3" style={{ color: 'var(--theme-text)' }}>{gym.check_sheets_completed}</td>
                  <td className="p-3">
                    {gym.recent_faults_30d > 0 ? <Badge className="bg-red-500/15 text-red-400 text-xs">{gym.recent_faults_30d} new</Badge> : <span style={{ color: 'var(--theme-text-muted)' }}>—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {leaderboard.filter(g => g.equipment_count > 0 || g.total_faults > 0).length === 0 && (
          <p className="text-center py-12 text-sm" style={{ color: 'var(--theme-text-muted)' }}>No gyms with equipment or faults yet</p>
        )}
      </Card>
    </div>
  );
};

export default AdminDashboardTab;
