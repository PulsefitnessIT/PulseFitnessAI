import React, { useState, useEffect, useMemo } from 'react';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import axios from 'axios';
import { useAuth } from '@/App';
import TopFailingPartsCard from '../../MasterAdmin/TopFailingPartsCard';

const SEVERITY_COLORS = {
  safety_critical: 'var(--color-danger)', out_of_order: 'var(--color-orange)', limited_use: 'var(--color-warning)',
  operational_fault: 'var(--color-info)', operational_minor: 'var(--color-text-faint-alt)',
};
const SEVERITY_LABELS = {
  safety_critical: 'Safety Critical', out_of_order: 'Out of Order', limited_use: 'Limited Use',
  operational_fault: 'Fault Present', operational_minor: 'Minor Issue',
};

const AdminFaultsTab = () => {
  const { API } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const token = localStorage.getItem('token');

  useEffect(() => {
    const load = async () => {
      try {
        const res = await axios.get(`${API}/master-admin/analytics/faults`, { headers: { Authorization: `Bearer ${token}` } });
        setData(res.data);
      } catch { /* ignored */ }
      setLoading(false);
    };
    load();
  }, [API, token]);

  const sortedSeverity = useMemo(
    () => [...(data?.by_severity || [])].sort((a, b) => b.count - a.count),
    [data?.by_severity]
  );

  if (loading) return <div className="flex items-center justify-center h-64"><RefreshCw className="animate-spin" style={{ color: 'var(--theme-text-muted)' }} size={24} /></div>;
  if (!data) return <p style={{ color: 'var(--theme-text-muted)' }} className="text-center py-12">Failed to load</p>;

  const { status_breakdown: status } = data;

  return (
    <div className="space-y-6" data-testid="admin-analytics-faults">
      {/* Status KPIs */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        {[
          { label: 'Total Faults', value: data.total_faults, color: '' },
          { label: 'Open', value: status.open || 0, color: 'text-red-400' },
          { label: 'In Progress', value: status.in_progress || 0, color: 'text-amber-400' },
          { label: 'Resolved', value: status.resolved || 0, color: 'text-emerald-400' },
          {
            label: 'AI-Tagged',
            value: `${data.coded_fault_count || 0}${data.total_faults > 0 ? ` / ${data.total_faults}` : ''}`,
            color: 'text-sky-400',
          },
        ].map(k => (
          <Card key={k.label} className="p-5" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
            <p className="text-[10px] uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{k.label}</p>
            <p className={`text-2xl font-bold ${k.color}`} style={!k.color ? { color: 'var(--theme-text)' } : {}}>{k.value}</p>
          </Card>
        ))}
      </div>

      {/* Top Failing Parts — fault-code breakdown with category totals */}
      <TopFailingPartsCard API={API} variant="detail" data={data} />

      {/* Problem Machines */}
      <Card className="p-5" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
        <h3 className="text-sm font-semibold mb-4 flex items-center gap-2" style={{ color: 'var(--theme-text)' }}>
          <AlertTriangle size={16} className="text-red-400" /> Most Problematic Machine Types
        </h3>
        {data.problem_machines.length > 0 ? (
          <ResponsiveContainer width="100%" height={Math.max(180, data.problem_machines.length * 30)}>
            <BarChart data={data.problem_machines} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="var(--theme-border)" />
              <XAxis type="number" tick={{ fontSize: 10, fill: 'var(--theme-text-muted)' }} />
              <YAxis dataKey="machine_type" type="category" tick={{ fontSize: 10, fill: 'var(--theme-text-muted)' }} width={120} />
              <Tooltip contentStyle={{ background: 'var(--theme-surface)', border: '1px solid var(--theme-border)', borderRadius: 8, color: 'var(--theme-text)', fontSize: 12 }} />
              <Bar dataKey="fault_count" fill="var(--color-danger)" radius={[0, 4, 4, 0]} name="Faults" />
            </BarChart>
          </ResponsiveContainer>
        ) : <p className="text-sm text-center py-8" style={{ color: 'var(--theme-text-muted)' }}>No fault data yet</p>}
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* By Severity */}
        <Card className="p-5" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
          <h3 className="text-sm font-semibold mb-4" style={{ color: 'var(--theme-text)' }}>Faults by Severity</h3>
          <div className="space-y-2">
            {sortedSeverity.map(s => {
              const pct = data.total_faults > 0 ? Math.round((s.count / data.total_faults) * 100) : 0;
              return (
                <div key={s.severity} className="flex items-center gap-3">
                  <div className="w-24 text-xs truncate" style={{ color: SEVERITY_COLORS[s.severity] || 'var(--theme-text-muted)' }}>
                    {SEVERITY_LABELS[s.severity] || s.severity}
                  </div>
                  <div className="flex-1 h-5 rounded-full overflow-hidden" style={{ background: 'var(--theme-border)' }}>
                    <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, background: SEVERITY_COLORS[s.severity] || 'var(--color-text-faint-alt)' }} />
                  </div>
                  <span className="text-xs font-medium w-10 text-right" style={{ color: 'var(--theme-text)' }}>{s.count}</span>
                </div>
              );
            })}
          </div>
        </Card>

        {/* By Gym */}
        <Card className="p-5" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
          <h3 className="text-sm font-semibold mb-4" style={{ color: 'var(--theme-text)' }}>Faults by Gym</h3>
          {data.by_gym.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={data.by_gym.slice(0, 8)}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--theme-border)" />
                <XAxis dataKey="gym" tick={{ fontSize: 9, fill: 'var(--theme-text-muted)' }} interval={0} angle={-15} textAnchor="end" height={50} />
                <YAxis tick={{ fontSize: 10, fill: 'var(--theme-text-muted)' }} width={30} />
                <Tooltip contentStyle={{ background: 'var(--theme-surface)', border: '1px solid var(--theme-border)', borderRadius: 8, color: 'var(--theme-text)', fontSize: 12 }} />
                <Bar dataKey="count" fill="var(--color-warning)" radius={[4, 4, 0, 0]} name="Faults" />
              </BarChart>
            </ResponsiveContainer>
          ) : <p className="text-sm text-center py-8" style={{ color: 'var(--theme-text-muted)' }}>No data</p>}
        </Card>
      </div>

      {/* Repeat Offenders */}
      <Card className="overflow-hidden" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
        <div className="p-4" style={{ borderBottom: '1px solid var(--theme-border)' }}>
          <h3 className="text-sm font-semibold" style={{ color: 'var(--theme-text)' }}>Repeat Offenders — Machines with 2+ Faults</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="repeat-offenders-table">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--theme-border)' }}>
                {['Serial', 'Type', 'Gym', 'Faults'].map(h => (
                  <th key={h} className="text-left p-3 text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.repeat_offenders.map((r, i) => (
                <tr key={i} style={{ borderBottom: '1px solid var(--theme-border)' }}>
                  <td className="p-3 font-medium" style={{ color: 'var(--theme-text)' }}>{r.serial_number || '—'}</td>
                  <td className="p-3" style={{ color: 'var(--theme-text-muted)' }}>{r.machine_type}</td>
                  <td className="p-3" style={{ color: 'var(--theme-text-muted)' }}>{r.gym}</td>
                  <td className="p-3"><Badge className="bg-red-500/15 text-red-400">{r.fault_count}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {data.repeat_offenders.length === 0 && <p className="text-center py-8 text-sm" style={{ color: 'var(--theme-text-muted)' }}>No repeat offenders found</p>}
      </Card>
    </div>
  );
};

export default AdminFaultsTab;
