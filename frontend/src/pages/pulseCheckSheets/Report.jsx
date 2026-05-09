import React from 'react';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Users } from 'lucide-react';

/** Report sub-tab — KPI tiles + per-staff breakdown. */
const Report = ({ report }) => {
  if (!report) {
    return <p className="text-center text-zinc-400 py-8 text-sm">No report data available</p>;
  }

  const stats = [
    { label: 'Total Completions', value: report.total_completions, color: 'text-zinc-900 dark:text-zinc-100' },
    { label: 'Last 7 Days', value: report.last_7_days, color: 'text-blue-600' },
    { label: 'Active Staff', value: report.staff_count, color: 'text-zinc-900 dark:text-zinc-100' },
    {
      label: 'Avg per Staff',
      value: report.staff_count > 0 ? Math.round(report.total_completions / report.staff_count) : 0,
      color: 'text-emerald-600',
    },
  ];

  const byStaff = Object.entries(report.by_staff || {});

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {stats.map(s => (
          <Card key={s.label} className="bg-white border-zinc-200 shadow-sm p-5 text-center dark:bg-zinc-900 dark:border-zinc-800">
            <p className={`text-2xl font-bold ${s.color}`}>{s.value}</p>
            <p className="text-xs text-zinc-400">{s.label}</p>
          </Card>
        ))}
      </div>
      <Card className="bg-white border-zinc-200 shadow-sm p-5 dark:bg-zinc-900 dark:border-zinc-800">
        <h3 className="font-semibold text-zinc-900 text-sm mb-3 flex items-center gap-2 dark:text-zinc-100">
          <Users size={16} className="text-blue-600" /> Staff Breakdown
        </h3>
        {byStaff.map(([name, data]) => (
          <div key={name} className="p-3 bg-zinc-50 rounded-lg border border-zinc-100 mb-2 dark:bg-zinc-900 dark:border-zinc-800">
            <div className="flex items-center justify-between mb-1">
              <span className="font-medium text-zinc-900 text-sm dark:text-zinc-100">{name}</span>
              <Badge className="bg-blue-50 text-blue-700">{data.count} completions</Badge>
            </div>
            <p className="text-xs text-zinc-400">
              Last: {data.last_completed?.slice(0, 10) || 'N/A'}
            </p>
          </div>
        ))}
        {!byStaff.length && (
          <p className="text-sm text-zinc-400 text-center py-4">No data yet</p>
        )}
      </Card>
    </div>
  );
};

export default Report;
