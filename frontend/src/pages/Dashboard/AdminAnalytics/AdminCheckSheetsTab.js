import React, { useState, useEffect } from 'react';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ClipboardCheck, RefreshCw, Lightbulb, Award } from 'lucide-react';
import axios from 'axios';
import { useAuth } from '@/App';

const AdminCheckSheetsTab = () => {
  const { API } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const token = localStorage.getItem('token');

  useEffect(() => {
    const load = async () => {
      try {
        const res = await axios.get(`${API}/master-admin/analytics/checksheets`, { headers: { Authorization: `Bearer ${token}` } });
        setData(res.data);
      } catch { /* ignored */ }
      setLoading(false);
    };
    load();
  }, [API, token]);

  if (loading) return <div className="flex items-center justify-center h-64"><RefreshCw className="animate-spin" style={{ color: 'var(--theme-text-muted)' }} size={24} /></div>;
  if (!data) return <p style={{ color: 'var(--theme-text-muted)' }} className="text-center py-12">Failed to load</p>;

  const getComplianceColor = (score) => {
    if (score >= 80) return 'text-emerald-400';
    if (score >= 50) return 'text-amber-400';
    return 'text-red-400';
  };

  return (
    <div className="space-y-6" data-testid="admin-analytics-checksheets">
      {/* Summary */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <Card className="p-5" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
          <div className="flex items-center gap-2">
            <ClipboardCheck size={16} className="text-blue-400" />
            <div>
              <p className="text-xl font-bold" style={{ color: 'var(--theme-text)' }}>{data.total_checks}</p>
              <p className="text-[10px] uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>Total Checks</p>
            </div>
          </div>
        </Card>
        <Card className="p-5" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
          <p className="text-[10px] uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>Active Gyms</p>
          <p className="text-xl font-bold" style={{ color: 'var(--theme-text)' }}>{data.leaderboard.length}</p>
        </Card>
        <Card className="p-5" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
          <p className="text-[10px] uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>Categories</p>
          <p className="text-xl font-bold" style={{ color: 'var(--theme-text)' }}>{data.by_category.length}</p>
        </Card>
      </div>

      {/* Compliance Leaderboard */}
      <Card className="overflow-hidden" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
        <div className="p-4 flex items-center gap-2" style={{ borderBottom: '1px solid var(--theme-border)' }}>
          <Award size={16} className="text-amber-400" />
          <h3 className="text-sm font-semibold" style={{ color: 'var(--theme-text)' }}>Maintenance Compliance Leaderboard</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="compliance-leaderboard">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--theme-border)' }}>
                {['Rank', 'Gym', 'Compliance', 'Total Checks', '30d Checks', 'Equipment'].map(h => (
                  <th key={h} className="text-left p-3 text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.leaderboard.map((gym, i) => (
                <tr key={gym.org_id} style={{ borderBottom: '1px solid var(--theme-border)' }}>
                  <td className="p-3">
                    <div className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold" style={{ background: i < 3 ? ['var(--color-gold)', 'var(--color-silver)', 'var(--color-bronze)'][i] + '30' : 'var(--theme-border)', color: i < 3 ? ['var(--color-gold)', 'var(--color-silver)', 'var(--color-bronze)'][i] : 'var(--theme-text-muted)' }}>
                      {i + 1}
                    </div>
                  </td>
                  <td className="p-3 font-medium" style={{ color: 'var(--theme-text)' }}>{gym.gym}</td>
                  <td className="p-3">
                    <span className={`font-bold ${getComplianceColor(gym.compliance_score)}`}>{gym.compliance_score}%</span>
                  </td>
                  <td className="p-3" style={{ color: 'var(--theme-text)' }}>{gym.total_checks}</td>
                  <td className="p-3">
                    {gym.recent_checks_30d > 0 ? <Badge className="bg-emerald-500/15 text-emerald-400">{gym.recent_checks_30d}</Badge> : <span style={{ color: 'var(--theme-text-muted)' }}>0</span>}
                  </td>
                  <td className="p-3" style={{ color: 'var(--theme-text-muted)' }}>{gym.equipment_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {data.leaderboard.length === 0 && <p className="text-center py-8 text-sm" style={{ color: 'var(--theme-text-muted)' }}>No check sheet data yet</p>}
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Top Users */}
        <Card className="p-5" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
          <h3 className="text-sm font-semibold mb-4" style={{ color: 'var(--theme-text)' }}>Most Active Staff</h3>
          <div className="space-y-2">
            {data.top_users.map((u, i) => (
              <div key={i} className="flex items-center justify-between p-2 rounded-lg" style={{ background: 'var(--theme-bg)' }}>
                <span className="text-sm" style={{ color: 'var(--theme-text)' }}>{u.user}</span>
                <Badge className="bg-blue-500/15 text-blue-400">{u.count} checks</Badge>
              </div>
            ))}
            {data.top_users.length === 0 && <p className="text-sm text-center py-4" style={{ color: 'var(--theme-text-muted)' }}>No user data</p>}
          </div>
        </Card>

        {/* AI Suggestions */}
        <Card className="p-5" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
          <h3 className="text-sm font-semibold mb-4 flex items-center gap-2" style={{ color: 'var(--theme-text)' }}>
            <Lightbulb size={16} className="text-amber-400" /> AI-Suggested Improvements
          </h3>
          <div className="space-y-3">
            {data.ai_suggestions.map((s, i) => (
              <div key={i} className="p-3 rounded-lg text-sm" style={{ background: 'var(--theme-bg)', border: '1px solid var(--theme-border)', color: 'var(--theme-text)' }}>
                {s}
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
};

export default AdminCheckSheetsTab;
