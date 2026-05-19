import { useState, useEffect } from 'react';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Brain, RefreshCw, Lightbulb, TrendingUp, BookOpen, Wrench } from 'lucide-react';
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import axios from 'axios';
import { useAuth } from '@/App';

const AdminAIDiagnosisTab = () => {
  const { API } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const token = localStorage.getItem('token');

  useEffect(() => {
    const load = async () => {
      try {
        const res = await axios.get(`${API}/master-admin/analytics/ai`, { headers: { Authorization: `Bearer ${token}` } });
        setData(res.data);
      } catch { /* ignored */ }
      setLoading(false);
    };
    load();
  }, [API, token]);

  if (loading) return <div className="flex items-center justify-center h-64"><RefreshCw className="animate-spin" style={{ color: 'var(--theme-text-muted)' }} size={24} /></div>;
  if (!data) return <p style={{ color: 'var(--theme-text-muted)' }} className="text-center py-12">Failed to load</p>;

  const { summary } = data;

  const kpis = [
    { label: 'Diagnoses', value: summary.total_diagnoses, icon: Brain, color: 'text-violet-400', bg: 'bg-violet-500/10' },
    { label: 'Audit Reports', value: summary.total_audits, icon: BookOpen, color: 'text-blue-400', bg: 'bg-blue-500/10' },
    { label: 'Fixes Logged', value: summary.total_fixes_logged, icon: Wrench, color: 'text-emerald-400', bg: 'bg-emerald-500/10' },
    { label: 'Knowledge Docs', value: summary.knowledge_documents, icon: BookOpen, color: 'text-amber-400', bg: 'bg-amber-500/10' },
    { label: 'Equipment Types', value: summary.unique_equipment_types_diagnosed, icon: TrendingUp, color: 'text-teal-400', bg: 'bg-teal-500/10' },
    { label: 'Issue Patterns', value: summary.unique_issue_patterns, icon: Lightbulb, color: 'text-pink-400', bg: 'bg-pink-500/10' },
  ];

  return (
    <div className="space-y-6" data-testid="admin-analytics-ai">
      {/* KPIs */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {kpis.map(k => (
          <Card key={k.label} className="p-5" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
            <div className="flex items-center gap-2.5">
              <div className={`w-9 h-9 rounded-lg ${k.bg} flex items-center justify-center flex-shrink-0`}>
                <k.icon size={16} className={k.color} />
              </div>
              <div>
                <p className="text-lg font-bold" style={{ color: 'var(--theme-text)' }}>{k.value}</p>
                <p className="text-[10px] uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{k.label}</p>
              </div>
            </div>
          </Card>
        ))}
      </div>

      {/* Usage Trend */}
      <Card className="p-5" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
        <h3 className="text-sm font-semibold mb-4" style={{ color: 'var(--theme-text)' }}>AI Usage Trend (6 Months)</h3>
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={data.usage_trend}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--theme-border)" />
            <XAxis dataKey="month" tick={{ fontSize: 11, fill: 'var(--theme-text-muted)' }} />
            <YAxis tick={{ fontSize: 11, fill: 'var(--theme-text-muted)' }} width={30} />
            <Tooltip contentStyle={{ background: 'var(--theme-surface)', border: '1px solid var(--theme-border)', borderRadius: 8, color: 'var(--theme-text)', fontSize: 12 }} />
            <Line type="monotone" dataKey="diagnoses" stroke="var(--color-accent-violet)" strokeWidth={2} dot={{ r: 3, fill: 'var(--color-accent-violet)' }} name="Diagnoses" />
            <Line type="monotone" dataKey="audits" stroke="var(--color-info)" strokeWidth={2} dot={{ r: 3, fill: 'var(--color-info)' }} name="Audits" />
          </LineChart>
        </ResponsiveContainer>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Top Diagnosed */}
        <Card className="p-5" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
          <h3 className="text-sm font-semibold mb-4" style={{ color: 'var(--theme-text)' }}>Most Diagnosed Equipment</h3>
          {data.top_diagnosed.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={data.top_diagnosed} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="var(--theme-border)" />
                <XAxis type="number" tick={{ fontSize: 10, fill: 'var(--theme-text-muted)' }} />
                <YAxis dataKey="type" type="category" tick={{ fontSize: 10, fill: 'var(--theme-text-muted)' }} width={100} />
                <Tooltip contentStyle={{ background: 'var(--theme-surface)', border: '1px solid var(--theme-border)', borderRadius: 8, color: 'var(--theme-text)', fontSize: 12 }} />
                <Bar dataKey="count" fill="var(--color-accent-violet)" radius={[0, 4, 4, 0]} name="Diagnoses" />
              </BarChart>
            </ResponsiveContainer>
          ) : <p className="text-sm text-center py-8" style={{ color: 'var(--theme-text-muted)' }}>No diagnosis data yet</p>}
        </Card>

        {/* Top Fixed */}
        <Card className="p-5" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
          <h3 className="text-sm font-semibold mb-4" style={{ color: 'var(--theme-text)' }}>Most Fixed Machine Types</h3>
          {data.top_fixed.length > 0 ? (
            <div className="space-y-2">
              {data.top_fixed.map((f, i) => (
                <div key={i} className="flex items-center justify-between p-2.5 rounded-lg" style={{ background: 'var(--theme-bg)' }}>
                  <span className="text-sm" style={{ color: 'var(--theme-text)' }}>{f.machine_type}</span>
                  <Badge className="bg-emerald-500/15 text-emerald-400">{f.fixes} fixes</Badge>
                </div>
              ))}
            </div>
          ) : <p className="text-sm text-center py-8" style={{ color: 'var(--theme-text-muted)' }}>No fix data yet</p>}
        </Card>
      </div>

      {/* AI Learning Insights */}
      <Card className="p-5" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
        <h3 className="text-sm font-semibold mb-4 flex items-center gap-2" style={{ color: 'var(--theme-text)' }}>
          <Lightbulb size={16} className="text-amber-400" /> AI-Suggested Check Sheet Improvements
        </h3>
        {data.check_improvements.length > 0 ? (
          <div className="space-y-3">
            {data.check_improvements.map((ci, i) => (
              <div key={i} className="p-4 rounded-lg" style={{ background: 'var(--theme-bg)', border: '1px solid var(--theme-border)' }}>
                <div className="flex items-center justify-between mb-2">
                  <span className="font-medium text-sm" style={{ color: 'var(--theme-text)' }}>{ci.machine_type}</span>
                  <Badge className="bg-red-500/15 text-red-400">{ci.high_severity_faults} high-sev faults</Badge>
                </div>
                <p className="text-sm" style={{ color: 'var(--theme-text-muted)' }}>{ci.suggestion}</p>
              </div>
            ))}
          </div>
        ) : (
          <div className="p-4 rounded-lg text-center" style={{ background: 'var(--theme-bg)', border: '1px solid var(--theme-border)' }}>
            <Brain size={32} className="mx-auto mb-2 text-violet-400" />
            <p className="text-sm" style={{ color: 'var(--theme-text-muted)' }}>AI is still learning from your equipment data. Suggestions will appear as more faults are diagnosed and resolved.</p>
          </div>
        )}
      </Card>
    </div>
  );
};

export default AdminAIDiagnosisTab;
