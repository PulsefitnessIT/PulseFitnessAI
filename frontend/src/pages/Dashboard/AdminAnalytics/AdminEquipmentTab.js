import { useState, useEffect } from 'react';
import { Card } from '@/components/ui/card';
import { RefreshCw } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import axios from 'axios';
import { useAuth } from '@/App';

const COLORS = ['var(--color-info)', 'var(--color-success)', 'var(--color-warning)', 'var(--color-danger)', 'var(--color-accent-violet)', '#EC4899', 'var(--color-teal-500)', 'var(--color-orange)', '#6366F1'];

const AdminEquipmentTab = () => {
  const { API } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const token = localStorage.getItem('token');

  useEffect(() => {
    const load = async () => {
      try {
        const res = await axios.get(`${API}/master-admin/analytics/equipment`, { headers: { Authorization: `Bearer ${token}` } });
        setData(res.data);
      } catch { /* ignored */ }
      setLoading(false);
    };
    load();
  }, [API, token]);

  if (loading) return <div className="flex items-center justify-center h-64"><RefreshCw className="animate-spin" style={{ color: 'var(--theme-text-muted)' }} size={24} /></div>;
  if (!data) return <p style={{ color: 'var(--theme-text-muted)' }} className="text-center py-12">Failed to load</p>;

  return (
    <div className="space-y-6" data-testid="admin-analytics-equipment">
      {/* Summary Row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Card className="p-5" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
          <p className="text-[10px] uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>Total Fleet</p>
          <p className="text-2xl font-bold" style={{ color: 'var(--theme-text)' }}>{data.total}</p>
        </Card>
        <Card className="p-5" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
          <p className="text-[10px] uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>Manufacturers</p>
          <p className="text-2xl font-bold" style={{ color: 'var(--theme-text)' }}>{data.by_manufacturer.length}</p>
        </Card>
        <Card className="p-5" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
          <p className="text-[10px] uppercase tracking-wider text-emerald-400">Active Warranty</p>
          <p className="text-2xl font-bold text-emerald-400">{data.warranty.active}</p>
        </Card>
        <Card className="p-5" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
          <p className="text-[10px] uppercase tracking-wider text-red-400">Expired Warranty</p>
          <p className="text-2xl font-bold text-red-400">{data.warranty.expired}</p>
        </Card>
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* By Manufacturer */}
        <Card className="p-5" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
          <h3 className="text-sm font-semibold mb-4" style={{ color: 'var(--theme-text)' }}>By Manufacturer</h3>
          {data.by_manufacturer.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={data.by_manufacturer} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="var(--theme-border)" />
                <XAxis type="number" tick={{ fontSize: 10, fill: 'var(--theme-text-muted)' }} />
                <YAxis dataKey="name" type="category" tick={{ fontSize: 10, fill: 'var(--theme-text-muted)' }} width={100} />
                <Tooltip contentStyle={{ background: 'var(--theme-surface)', border: '1px solid var(--theme-border)', borderRadius: 8, color: 'var(--theme-text)', fontSize: 12 }} />
                <Bar dataKey="count" fill="var(--color-info)" radius={[0, 4, 4, 0]} name="Count" />
              </BarChart>
            </ResponsiveContainer>
          ) : <p className="text-sm text-center py-8" style={{ color: 'var(--theme-text-muted)' }}>No manufacturer data</p>}
        </Card>

        {/* By Type */}
        <Card className="p-5" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
          <h3 className="text-sm font-semibold mb-4" style={{ color: 'var(--theme-text)' }}>By Equipment Type</h3>
          {data.by_type.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={data.by_type} cx="50%" cy="50%" innerRadius={50} outerRadius={80} paddingAngle={2} dataKey="count" nameKey="name">
                  {data.by_type.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Pie>
                <Tooltip contentStyle={{ background: 'var(--theme-surface)', border: '1px solid var(--theme-border)', borderRadius: 8, color: 'var(--theme-text)', fontSize: 12 }} />
              </PieChart>
            </ResponsiveContainer>
          ) : <p className="text-sm text-center py-8" style={{ color: 'var(--theme-text-muted)' }}>No type data</p>}
          <div className="grid grid-cols-2 gap-1 mt-2">
            {data.by_type.slice(0, 8).map((t, i) => (
              <div key={t.name} className="flex items-center gap-2 text-xs">
                <div className="w-2.5 h-2.5 rounded-sm flex-shrink-0" style={{ background: COLORS[i % COLORS.length] }} />
                <span className="truncate" style={{ color: 'var(--theme-text-muted)' }}>{t.name}</span>
                <span className="ml-auto font-medium" style={{ color: 'var(--theme-text)' }}>{t.count}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Equipment Per Gym */}
      <Card className="p-5" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
        <h3 className="text-sm font-semibold mb-4" style={{ color: 'var(--theme-text)' }}>Equipment Density Per Gym</h3>
        {data.per_gym.length > 0 ? (
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={data.per_gym}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--theme-border)" />
              <XAxis dataKey="gym" tick={{ fontSize: 9, fill: 'var(--theme-text-muted)' }} interval={0} angle={-15} textAnchor="end" height={50} />
              <YAxis tick={{ fontSize: 10, fill: 'var(--theme-text-muted)' }} width={30} />
              <Tooltip contentStyle={{ background: 'var(--theme-surface)', border: '1px solid var(--theme-border)', borderRadius: 8, color: 'var(--theme-text)', fontSize: 12 }} />
              <Bar dataKey="count" fill="var(--color-teal-500)" radius={[4, 4, 0, 0]} name="Equipment" />
            </BarChart>
          </ResponsiveContainer>
        ) : <p className="text-sm text-center py-8" style={{ color: 'var(--theme-text-muted)' }}>No gym data</p>}
      </Card>

      {/* Age Distribution */}
      <Card className="p-5" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
        <h3 className="text-sm font-semibold mb-4" style={{ color: 'var(--theme-text)' }}>Equipment Age Distribution</h3>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
          {data.age_distribution.map(a => (
            <div key={a.range} className="p-3 rounded-lg text-center" style={{ background: 'var(--theme-bg)', border: '1px solid var(--theme-border)' }}>
              <p className="text-xl font-bold" style={{ color: 'var(--theme-text)' }}>{a.count}</p>
              <p className="text-[10px] uppercase tracking-wider mt-0.5" style={{ color: 'var(--theme-text-muted)' }}>{a.range}</p>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
};

export default AdminEquipmentTab;
