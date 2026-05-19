import { useMemo } from 'react';
import { Card } from '@/components/ui/card';
import { RefreshCw } from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer
} from 'recharts';

const AdminAiUsage = ({ aiUsage }) => {
  const totalCost = useMemo(
    () => aiUsage?.usage?.reduce((s, u) => s + u.estimated_cost, 0).toFixed(2) ?? '0.00',
    [aiUsage?.usage]
  );

  if (!aiUsage) return <div className="flex items-center justify-center h-32"><RefreshCw className="animate-spin text-zinc-400" size={24} /></div>;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-4">
        <Card className="bg-white border-zinc-200 shadow-sm p-5">
          <p className="text-xs font-bold uppercase tracking-wider text-zinc-400">Total AI Calls</p>
          <p className="text-3xl font-semibold text-zinc-900 mt-1">{aiUsage.total_calls}</p>
        </Card>
        <Card className="bg-white border-zinc-200 shadow-sm p-5">
          <p className="text-xs font-bold uppercase tracking-wider text-zinc-400">Est. Total Cost</p>
          <p className="text-3xl font-semibold text-zinc-900 mt-1">£{totalCost}</p>
        </Card>
        <Card className="bg-white border-zinc-200 shadow-sm p-5">
          <p className="text-xs font-bold uppercase tracking-wider text-zinc-400">Active Orgs Using AI</p>
          <p className="text-3xl font-semibold text-zinc-900 mt-1">{aiUsage.usage.length}</p>
        </Card>
      </div>

      {aiUsage.usage.length > 0 && (
        <Card className="bg-white border-zinc-200 shadow-sm p-5">
          <h3 className="font-medium text-zinc-900 mb-4">AI Calls by Organisation</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={aiUsage.usage.slice(0, 10)}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-paper-alt)" />
              <XAxis dataKey="org_name" tick={{ fontSize: 10, fill: 'var(--color-text-faint)' }} interval={0} angle={-20} textAnchor="end" height={60} />
              <YAxis tick={{ fontSize: 11, fill: 'var(--color-text-faint)' }} />
              <Tooltip contentStyle={{ background: 'var(--color-neutral-950-alt)', border: 'none', borderRadius: 6, color: '#fff', fontSize: 12 }} />
              <Bar dataKey="triage_calls" fill="var(--color-blue-600)" name="Triage" radius={[4, 4, 0, 0]} />
              <Bar dataKey="audit_reports" fill="var(--color-success)" name="Audits" radius={[4, 4, 0, 0]} />
              <Bar dataKey="risk_assessments" fill="var(--color-warning)" name="Risk Assessments" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}

      <Card className="bg-white border-zinc-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
        <table className="w-full text-sm min-w-[640px]">
          <thead>
            <tr className="border-b border-zinc-100 bg-zinc-50">
              <th className="text-left p-3 text-xs font-bold uppercase tracking-wider text-zinc-400">Organisation</th>
              <th className="text-center p-3 text-xs font-bold uppercase tracking-wider text-zinc-400">Triage</th>
              <th className="text-center p-3 text-xs font-bold uppercase tracking-wider text-zinc-400">Audits</th>
              <th className="text-center p-3 text-xs font-bold uppercase tracking-wider text-zinc-400">Risk Assess.</th>
              <th className="text-center p-3 text-xs font-bold uppercase tracking-wider text-zinc-400">Total</th>
              <th className="text-right p-3 text-xs font-bold uppercase tracking-wider text-zinc-400">Est. Cost</th>
            </tr>
          </thead>
          <tbody>
            {aiUsage.usage.map(u => (
              <tr key={u.org_id} className="border-b border-zinc-50 hover:bg-zinc-50">
                <td className="p-3 font-medium text-zinc-900">{u.org_name}</td>
                <td className="p-3 text-center text-zinc-600">{u.triage_calls}</td>
                <td className="p-3 text-center text-zinc-600">{u.audit_reports}</td>
                <td className="p-3 text-center text-zinc-600">{u.risk_assessments}</td>
                <td className="p-3 text-center font-medium text-zinc-900">{u.total_calls}</td>
                <td className="p-3 text-right text-zinc-900">£{u.estimated_cost.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      </Card>
    </div>
  );
};

export default AdminAiUsage;
